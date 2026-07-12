"""Health status monitoring for daemon process."""
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

    def __init__(self, health_file: Path):
        """
        Initialize health monitor.

        Args:
            health_file: Path to health status file (e.g., /app/health_status.txt)
        """
        self.health_file = health_file
        self._last_status: Optional[str] = None

    def update_status(self, status: str) -> None:
        """
        Update health status file with current status.

        Args:
            status: Current daemon status ("starting", "healthy", "error", "stopped")
        """
        try:
            self._write_health_file(status)
            self._last_status = status
            logger.info(f"Health status: {status}")
        except Exception as e:
            # Log error but don't crash - health check failure is better than daemon crash
            logger.error(f"Failed to write health status: {e}")

    def heartbeat(self) -> None:
        """
        Refresh the health file timestamp without changing status.

        Keeps the health file fresh during long check iterations and idle
        periods between checks, so staleness detection only fires when the
        daemon is genuinely stuck.
        """
        if self._last_status is None:
            return
        try:
            self._write_health_file(self._last_status)
            logger.debug(f"Health heartbeat: {self._last_status}")
        except Exception as e:
            logger.error(f"Failed to write health heartbeat: {e}")

    def _write_health_file(self, status: str) -> None:
        """
        Atomically write health status to file.

        Uses temp file + rename for atomic operation to prevent partial reads
        during Docker HEALTHCHECK.

        Args:
            status: Status string to write

        Format:
            Line 1: status
            Line 2: ISO timestamp
        """
        # Ensure parent directory exists
        self.health_file.parent.mkdir(parents=True, exist_ok=True)

        # Prepare content with timezone-aware UTC timestamp
        timestamp = datetime.now(timezone.utc).isoformat()
        content = f"{status}\n{timestamp}\n"

        # Atomic write: temp file + rename
        temp_file = self.health_file.with_suffix('.tmp')
        temp_file.write_text(content)
        temp_file.replace(self.health_file)
