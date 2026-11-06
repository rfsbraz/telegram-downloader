"""Health status monitoring for daemon process."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Manages health status file for Docker HEALTHCHECK.

    Uses atomic file writes (temp file + rename) to prevent partial reads
    during concurrent health checks.

    Status values:
        - "starting": Daemon is initializing
        - "healthy": Daemon is running normally
        - "error": Daemon encountered an error
        - "stopped": Daemon is shutting down
    """

    def __init__(self, health_file: Path, max_check_age: Optional[float] = None):
        """
        Initialize health monitor.

        Args:
            health_file: Path to health status file (e.g., /app/health_status.txt)
        """
        self.health_file = health_file
        self._last_status: Optional[str] = None
        self._last_reason: Optional[str] = None
        self._started_at = datetime.now(timezone.utc)
        self._last_success: Optional[datetime] = None
        self._last_progress: Optional[datetime] = None
        self.max_check_age = max_check_age

    def update_status(
        self,
        status: str,
        reason: Optional[str] = None,
        *,
        successful_check: bool = True,
    ) -> None:
        """
        Update health status file with current status.

        Args:
            status: Current daemon status ("starting", "healthy", "error", "stopped")
            reason: Optional human-readable reason, written as line 3
        """
        try:
            if status == "healthy":
                self._last_progress = datetime.now(timezone.utc)
                if successful_check:
                    self._last_success = self._last_progress
            self._write_health_file(status, reason)
            self._last_status = status
            self._last_reason = reason
            logger.info(f"Health status: {status}")
        except Exception as e:
            # Log error but don't crash - health check failure is better than daemon crash
            logger.error(f"Failed to write health status: {e}")

    def heartbeat(self) -> None:
        """
        Refresh the health file timestamp without changing status.

        Refreshes liveness only. Successful-check and scheduling progress
        timestamps do not advance, so a live heartbeat cannot hide a hung check.
        """
        if self._last_status is None:
            return
        try:
            self._write_health_file(self._last_status, self._last_reason)
            logger.debug(f"Health heartbeat: {self._last_status}")
        except Exception as e:
            logger.error(f"Failed to write health heartbeat: {e}")

    def _write_health_file(self, status: str, reason: Optional[str] = None) -> None:
        """
        Atomically write health status to file.

        Uses temp file + rename for atomic operation to prevent partial reads
        during Docker HEALTHCHECK.

        Args:
            status: Status string to write
            reason: Optional reason string

        Format:
            Line 1: status
            Line 2: ISO timestamp
            Line 3: reason (optional)
        """
        # Ensure parent directory exists
        self.health_file.parent.mkdir(parents=True, exist_ok=True)

        # Prepare content with timezone-aware UTC timestamp
        timestamp = datetime.now(timezone.utc).isoformat()
        content = f"{status}\n{timestamp}\n"
        # Keep status, timestamp and reason at their legacy positions. Reserve
        # line 3 even without a reason so metadata always starts on line 4.
        content += (reason or "").replace("\n", " ").replace("\r", " ") + "\n"
        content += (
            json.dumps(
                {
                    "version": 1,
                    "updated_at": timestamp,
                    "started_at": self._started_at.isoformat(),
                    "last_success": (
                        self._last_success.isoformat() if self._last_success else None
                    ),
                    "last_progress": (
                        self._last_progress.isoformat() if self._last_progress else None
                    ),
                    "max_check_age": self.max_check_age,
                }
            )
            + "\n"
        )

        # Atomic write: temp file + rename
        temp_file = self.health_file.with_suffix(".tmp")
        temp_file.write_text(content)
        temp_file.replace(self.health_file)
