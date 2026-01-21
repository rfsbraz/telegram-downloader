"""Daemon service orchestration with signal handling and graceful shutdown."""
import asyncio
import signal
import logging
import time
from typing import Callable, Awaitable, Optional
from pathlib import Path

from src.daemon.health import HealthMonitor
from src.notifications.manager import NotificationManager

logger = logging.getLogger(__name__)


class DaemonService:
    """
    Daemon orchestration with periodic execution and graceful shutdown.

    Features:
    - Signal handling for SIGTERM (Docker) and SIGINT (Ctrl+C)
    - Immediate shutdown response (doesn't wait full interval)
    - Startup validation (fail-fast on configuration errors)
    - Health monitoring integration
    - Structured concurrency with proper cleanup

    Usage:
        service = DaemonService(
            check_function=my_async_check,
            check_interval=300,
            health_file=Path("/app/health_status.txt")
        )
        await service.run()

    Startup validation:
        The startup() method is a hook for performing validation before the
        main loop begins. Caller should override or extend this method to
        perform authentication, source validation, etc. Any exceptions raised
        during startup will fail-fast and prevent daemon from starting.
    """

    def __init__(
        self,
        check_function: Callable[[], Awaitable[None]],
        check_interval: int,
        health_file: Path,
        check_timeout: Optional[int] = None,
        notification_manager: Optional[NotificationManager] = None
    ):
        """
        Initialize daemon service.

        Args:
            check_function: Async function to call periodically
            check_interval: Seconds between checks
            health_file: Path to health status file
            check_timeout: Optional timeout for check execution (None = no timeout)
            notification_manager: Optional notification manager for sending alerts
        """
        self.check_function = check_function
        self.check_interval = check_interval
        self.check_timeout = check_timeout
        self.notification_manager = notification_manager
        self.shutdown_event = asyncio.Event()
        self.health = HealthMonitor(health_file)
        self.log = logging.getLogger("daemon")
        self.iteration = 0

    async def startup(self):
        """
        Startup initialization and validation.

        Override this method to perform validation before main loop begins.
        Any exceptions raised here will fail-fast and prevent daemon from starting.
        """
        self.log.info(f"Daemon starting with check_interval={self.check_interval}s")
        self.health.update_status("starting")

        # Send startup notification
        if self.notification_manager:
            await self.notification_manager.notify(
                level="info",
                title="Daemon Started",
                message=f"Telegram Downloader daemon started successfully",
                details={
                    "check_interval": f"{self.check_interval}s",
                    "health_file": str(self.health.health_file)
                }
            )

    async def shutdown(self):
        """
        Graceful shutdown - cleanup resources.

        Sets shutdown event to interrupt sleep and cancels running tasks.
        """
        self.log.info("Shutting down gracefully...")
        self.shutdown_event.set()

        # Send shutdown notification
        if self.notification_manager:
            await self.notification_manager.notify(
                level="info",
                title="Daemon Shutting Down",
                message="Telegram Downloader daemon is shutting down",
                details={
                    "total_iterations": self.iteration
                }
            )

        # Cancel all tasks except current task
        current_task = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current_task]

        if tasks:
            self.log.debug(f"Cancelling {len(tasks)} running tasks...")
            for task in tasks:
                task.cancel()

            # Wait for all tasks to complete cancellation
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                # Log but continue shutdown
                self.log.error(f"Error during task cleanup: {e}")

        self.health.update_status("stopped")
        self.log.info("Shutdown complete")

    async def run_check(self):
        """
        Execute single check iteration.

        Wraps check_function with error handling and health updates.
        Errors are logged but don't crash the daemon.
        """
        self.iteration += 1
        self.log.info(f"Starting periodic check (iteration {self.iteration})")

        start_time = time.time()
        try:
            # Run check with optional timeout
            if self.check_timeout:
                await asyncio.wait_for(
                    self.check_function(),
                    timeout=self.check_timeout
                )
            else:
                await self.check_function()

            # Check successful
            duration = time.time() - start_time
            self.log.info(f"Check complete (took {duration:.1f}s)")
            self.health.update_status("healthy")

            # Send success notification
            if self.notification_manager:
                await self.notification_manager.notify(
                    level="success",
                    title="Download Check Complete",
                    message=f"Iteration {self.iteration} completed successfully",
                    details={
                        "iteration": self.iteration,
                        "duration": f"{duration:.1f}s"
                    }
                )

        except asyncio.TimeoutError:
            self.log.error(
                f"Check iteration {self.iteration} timed out after {self.check_timeout}s. "
                "Will retry at next scheduled check."
            )
            self.health.update_status("error")

            # Send timeout error notification (critical - bypass throttling)
            if self.notification_manager:
                await self.notification_manager.notify(
                    level="error",
                    title="Check Timeout",
                    message=f"Iteration {self.iteration} exceeded {self.check_timeout}s timeout",
                    details={
                        "iteration": self.iteration,
                        "timeout": f"{self.check_timeout}s"
                    },
                    force=True
                )

        except Exception as e:
            # Import FloodWait for circuit breaker check
            try:
                from pyrogram.errors import FloodWait
                is_floodwait = isinstance(e, FloodWait)
            except ImportError:
                is_floodwait = False

            # FloodWait circuit breaker: skip iteration if wait time exceeds threshold
            if is_floodwait and e.value > 60:
                self.log.error(
                    f"FloodWait {e.value}s exceeds threshold (60s). "
                    "Skipping this check iteration to prevent API hammering. "
                    "Will retry at next scheduled check."
                )
                self.health.update_status("error")

                # Send FloodWait notification (critical - bypass throttling)
                if self.notification_manager:
                    await self.notification_manager.notify(
                        level="error",
                        title="Rate Limited by Telegram",
                        message=f"FloodWait {e.value}s exceeded threshold",
                        details={
                            "wait_time": f"{e.value}s",
                            "iteration": self.iteration
                        },
                        force=True
                    )
                return

            # Log error with traceback
            self.log.error(
                f"Check iteration {self.iteration} failed: {e}",
                exc_info=True
            )
            self.log.error("Check iteration failed, will retry at next interval")
            self.health.update_status("error")

            # Send generic error notification (throttled)
            if self.notification_manager:
                await self.notification_manager.notify(
                    level="error",
                    title="Check Failed",
                    message=str(e),
                    details={
                        "iteration": self.iteration,
                        "error_type": type(e).__name__
                    }
                )

    async def periodic_loop(self):
        """
        Main daemon loop with periodic execution.

        Runs first check immediately, then waits check_interval between checks.
        Uses shutdown event for immediate shutdown response.
        """
        # Run initial check immediately
        self.log.info("Running initial check...")
        await self.run_check()

        # Periodic execution loop
        while not self.shutdown_event.is_set():
            try:
                # Wait for next interval OR shutdown event (whichever comes first)
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=self.check_interval
                )
                # If we get here, shutdown was triggered
                break

            except asyncio.TimeoutError:
                # Timeout is normal - means it's time for next check
                if not self.shutdown_event.is_set():
                    await self.run_check()

    def _handle_signal(self, signame: str):
        """
        Signal handler callback.

        Creates shutdown task to trigger graceful shutdown.
        """
        self.log.info(f"Received {signame}, initiating graceful shutdown...")
        asyncio.create_task(self.shutdown())

    def setup_signal_handlers(self, loop):
        """
        Register signal handlers for graceful shutdown.

        Handles SIGTERM (Docker stop) and SIGINT (Ctrl+C).
        """
        try:
            # SIGTERM: Docker stop, systemd stop
            loop.add_signal_handler(
                signal.SIGTERM,
                lambda: self._handle_signal("SIGTERM")
            )

            # SIGINT: Ctrl+C
            loop.add_signal_handler(
                signal.SIGINT,
                lambda: self._handle_signal("SIGINT")
            )

            self.log.debug("Signal handlers registered (SIGTERM, SIGINT)")

        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            self.log.warning("Signal handlers not supported on this platform")

    async def run(self):
        """
        Main entry point for daemon execution.

        Orchestrates startup, periodic loop, and shutdown with proper cleanup.
        """
        # Get running event loop
        loop = asyncio.get_running_loop()

        # Setup signal handlers
        self.setup_signal_handlers(loop)

        try:
            # Startup initialization and validation
            await self.startup()

            # Main periodic loop
            await self.periodic_loop()

        finally:
            # Ensure cleanup happens even if exceptions occur
            if not self.shutdown_event.is_set():
                await self.shutdown()
            else:
                # Shutdown was already initiated, just update final health status
                self.health.update_status("stopped")
                self.log.info("Shutdown complete")
