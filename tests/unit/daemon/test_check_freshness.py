"""A live heartbeat cannot stand in for a completed download check."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.config.loader import load_config
from src.config.schema import DaemonConfig
from src.daemon.health import HealthMonitor
from src.daemon.service import DaemonService

ROOT = Path(__file__).resolve().parents[3]


def metadata(path):
    return json.loads(path.read_text().splitlines()[3])


def probe(path):
    return subprocess.run(
        [sys.executable, str(ROOT / "healthcheck.py")],
        env={**os.environ, "TDL_DAEMON_HEALTH_FILE": str(path)},
        capture_output=True,
        text=True,
        timeout=10,
    )


async def test_timed_out_check_is_cancelled_and_next_check_can_recover(tmp_path):
    cancelled = asyncio.Event()

    async def hung():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    path = tmp_path / "health.txt"
    service = DaemonService(hung, 300, path, check_timeout=0.01)
    service.health.update_status("healthy")
    previous_success = metadata(path)["last_success"]
    await asyncio.wait_for(service.run_check(), timeout=1)
    assert cancelled.is_set()
    assert path.read_text().splitlines()[0] == "error"
    assert "timed out" in path.read_text()
    service.health.heartbeat()
    assert "timed out" in path.read_text()
    assert metadata(path)["last_success"] == previous_success

    service.check_function = AsyncMock()
    await service.run_check()
    assert path.read_text().splitlines()[0] == "healthy"
    assert metadata(path)["last_success"] > previous_success


def test_default_timeout_tracks_interval_and_explicit_timeout_wins(tmp_path):
    assert DaemonService(AsyncMock(), 900, tmp_path / "a").check_timeout == 1800
    assert DaemonService(AsyncMock(), 900, tmp_path / "b", 42).check_timeout == 42


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(value, tmp_path):
    with pytest.raises(ValueError):
        DaemonConfig(check_timeout=value)
    with pytest.raises(ValueError):
        DaemonService(AsyncMock(), 300, tmp_path / "health", value)


def test_configured_timeout_loads_from_yaml_and_environment(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "api_id: 12345\napi_hash: " + "x" * 32 + "\ndaemon:\n  check_timeout: 1800\n"
    )
    assert load_config(str(path)).daemon.check_timeout == 1800
    monkeypatch.setenv("TDL_DAEMON_CHECK_TIMEOUT", "3600")
    assert load_config(str(path)).daemon.check_timeout == 3600


def test_heartbeat_does_not_hide_stale_check_progress(tmp_path):
    path = tmp_path / "health.txt"
    monitor = HealthMonitor(path, max_check_age=900)
    monitor.update_status("healthy")
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    monitor._last_success = monitor._last_progress = old
    monitor.heartbeat()
    data = metadata(path)
    assert data["last_success"] == old.isoformat()
    assert data["updated_at"] != old.isoformat()
    result = probe(path)
    assert result.returncode == 1
    assert "check progress stale" in result.stderr


def test_first_check_cannot_remain_starting_forever(tmp_path):
    path = tmp_path / "health.txt"
    monitor = HealthMonitor(path, max_check_age=900)
    monitor.update_status("starting")
    monitor._started_at -= timedelta(hours=1)
    monitor.heartbeat()
    assert probe(path).returncode == 1


async def test_schedule_skip_is_progress_but_not_a_successful_download_check(
    tmp_path, monkeypatch
):
    path = tmp_path / "health.txt"
    check = AsyncMock()
    service = DaemonService(check, 300, path, active_hours="02:00-03:00")
    service.health.update_status("healthy")
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    service.health._last_success = service.health._last_progress = old
    monkeypatch.setattr("src.daemon.service.is_within_active_hours", lambda _: False)
    await service.run_check()
    check.assert_not_awaited()
    assert metadata(path)["last_success"] == old.isoformat()
    assert metadata(path)["last_progress"] != old.isoformat()
    assert probe(path).returncode == 0


def test_long_configured_interval_does_not_use_the_heartbeat_age_limit(tmp_path):
    path = tmp_path / "health.txt"
    service = DaemonService(AsyncMock(), 7200, path)
    service.health.update_status("healthy")
    service.health._last_success = service.health._last_progress = datetime.now(
        timezone.utc
    ) - timedelta(hours=1)
    service.health.heartbeat()
    assert probe(path).returncode == 0


@pytest.mark.parametrize(
    "payload", ["not-json", '{"version":2}', '{"version":1,"max_check_age":-1}']
)
def test_invalid_progress_metadata_is_unhealthy(payload, tmp_path):
    path = tmp_path / "health.txt"
    path.write_text(f"healthy\n{datetime.now(timezone.utc).isoformat()}\n\n{payload}\n")
    assert probe(path).returncode == 1
