"""
Integration tests for healthcheck.py.

Tests health file parsing, status validation, and exit codes.
"""
import subprocess
import sys
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path


# Get the project root directory
# __file__ = tests/integration/test_healthcheck.py
# parent = tests/integration
# parent.parent = tests
# parent.parent.parent = project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
HEALTHCHECK_SCRIPT = PROJECT_ROOT / "healthcheck.py"


class TestHealthcheckExitCodes:
    """Health check exit code behavior."""

    def test_healthy_status_exits_zero(self, temp_dir, monkeypatch):
        """Healthy status should exit with code 0."""
        health_file = temp_dir / "health_status.txt"
        health_file.write_text(f"healthy\n{datetime.now().isoformat()}")

        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(health_file)

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "healthy" in result.stdout.lower()

    def test_starting_status_exits_zero(self, temp_dir, monkeypatch):
        """Starting status should also exit with code 0."""
        health_file = temp_dir / "health_status.txt"
        health_file.write_text(f"starting\n{datetime.now().isoformat()}")

        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(health_file)

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0

    def test_error_status_exits_one(self, temp_dir, monkeypatch):
        """Error status should exit with code 1."""
        health_file = temp_dir / "health_status.txt"
        health_file.write_text(f"error\n{datetime.now().isoformat()}")

        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(health_file)

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 1

    def test_missing_file_exits_one(self, temp_dir, monkeypatch):
        """Missing health file should exit with code 1."""
        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(temp_dir / "nonexistent.txt")

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 1
        assert "not found" in result.stderr.lower()


class TestHealthcheckStaleness:
    """Health file staleness detection."""

    def test_stale_file_exits_one(self, temp_dir, monkeypatch):
        """Stale health file (>10 minutes old) should exit with code 1."""
        health_file = temp_dir / "health_status.txt"

        # Timestamp more than 10 minutes ago
        old_timestamp = datetime.now() - timedelta(minutes=15)
        health_file.write_text(f"healthy\n{old_timestamp.isoformat()}")

        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(health_file)

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 1
        assert "stale" in result.stderr.lower()


class TestHealthcheckFileFormat:
    """Health file format validation."""

    def test_invalid_format_exits_one(self, temp_dir, monkeypatch):
        """Invalid file format should exit with code 1."""
        health_file = temp_dir / "health_status.txt"
        health_file.write_text("single line only")

        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(health_file)

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 1

    def test_invalid_timestamp_exits_one(self, temp_dir, monkeypatch):
        """Invalid timestamp should exit with code 1."""
        health_file = temp_dir / "health_status.txt"
        health_file.write_text("healthy\nnot-a-valid-timestamp")

        env = os.environ.copy()
        env["TDL_DAEMON_HEALTH_FILE"] = str(health_file)

        result = subprocess.run(
            [sys.executable, str(HEALTHCHECK_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 1
        assert "timestamp" in result.stderr.lower()
