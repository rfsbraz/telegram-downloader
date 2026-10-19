"""
Unit tests for HealthMonitor (health status file management).

Tests timezone-aware timestamps, status updates, and heartbeat refresh.
"""
from datetime import datetime, timezone

from src.daemon.health import HealthMonitor


class TestHealthMonitorTimestamps:
    """Timestamp format written to the health file."""

    def test_writes_timezone_aware_utc_timestamp(self, temp_dir):
        """Health file timestamps must be timezone-aware UTC."""
        health_file = temp_dir / "health_status.txt"
        monitor = HealthMonitor(health_file)
        monitor.update_status("healthy")

        lines = health_file.read_text().strip().split("\n")
        assert lines[0] == "healthy"

        timestamp = datetime.fromisoformat(lines[1])
        assert timestamp.tzinfo is not None
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        assert 0 <= age < 60


class TestHealthMonitorHeartbeat:
    """Heartbeat refreshes timestamp without changing status."""

    def test_heartbeat_refreshes_timestamp_keeps_status(self, temp_dir):
        """heartbeat() rewrites the file with the same status."""
        health_file = temp_dir / "health_status.txt"
        monitor = HealthMonitor(health_file)
        monitor.update_status("healthy")

        first_timestamp = health_file.read_text().strip().split("\n")[1]

        monitor.heartbeat()
        lines = health_file.read_text().strip().split("\n")
        assert lines[0] == "healthy"
        # Timestamp refreshed (or at minimum still valid and parseable)
        refreshed = datetime.fromisoformat(lines[1])
        assert refreshed >= datetime.fromisoformat(first_timestamp)

    def test_heartbeat_before_first_status_is_noop(self, temp_dir):
        """heartbeat() before any update_status() must not create the file."""
        health_file = temp_dir / "health_status.txt"
        monitor = HealthMonitor(health_file)
        monitor.heartbeat()
        assert not health_file.exists()

    def test_heartbeat_preserves_error_status(self, temp_dir):
        """heartbeat() must not mask an error status."""
        health_file = temp_dir / "health_status.txt"
        monitor = HealthMonitor(health_file)
        monitor.update_status("error")
        monitor.heartbeat()

        lines = health_file.read_text().strip().split("\n")
        assert lines[0] == "error"
