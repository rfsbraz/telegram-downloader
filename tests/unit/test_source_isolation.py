"""
Unit tests for per-source error isolation in run_check (issue #57).

One source raising mid-check must not skip the sources after it, the run
summary must count it, and account-wide errors (FloodWait, auth) must still
reach the daemon instead of being swallowed per source.
"""
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from pyrogram.errors import AuthKeyUnregistered, FloodWait

from src.daemon.service import DaemonService
from src.main import run_check


class FakeSource:
    """Source with no new media, or one that raises while scanning."""

    def __init__(self, name, error=None):
        self.name = name
        self.error = error
        self.scanned = False

    def get_cursor_key(self):
        return f"{self.name}:"

    async def get_display_name(self):
        return self.name

    async def iterate_new_media(self, last_seen_id):
        self.scanned = True
        if self.error:
            raise self.error
        return
        yield  # pragma: no cover - makes this an async generator


def make_sources(*sources):
    return [(s, MagicMock(), MagicMock()) for s in sources]


def make_args(sources):
    cfg = MagicMock()
    cfg.max_concurrent_downloads = 1
    cfg.max_downloads_per_run = 0
    state_store = MagicMock()
    state_store.get.return_value = 0
    pending = MagicMock()
    pending.has_pending.return_value = False
    log = logging.getLogger("test-isolation")
    return cfg, log, state_store, MagicMock(), make_sources(*sources), None, pending


class TestPerSourceIsolation:

    async def test_failing_source_does_not_skip_the_rest(self):
        first = FakeSource("first")
        broken = FakeSource("broken", RuntimeError("CHANNEL_INVALID"))
        last = FakeSource("last")

        summary = await run_check(*make_args([first, broken, last]))

        assert first.scanned and broken.scanned and last.scanned
        assert summary["sources_checked"] == 3
        assert summary["sources_failed"] == 1

    async def test_clean_run_reports_zero_failures(self):
        summary = await run_check(*make_args([FakeSource("a"), FakeSource("b")]))

        assert summary["sources_failed"] == 0

    async def test_auth_error_is_not_swallowed(self):
        broken = FakeSource("broken", AuthKeyUnregistered())

        with pytest.raises(AuthKeyUnregistered):
            await run_check(*make_args([broken, FakeSource("last")]))


class TestFloodWaitStillTripsBreaker:

    async def test_floodwait_propagates_out_of_run_check(self):
        broken = FakeSource("broken", FloodWait(value=120))

        with pytest.raises(FloodWait):
            await run_check(*make_args([broken, FakeSource("last")]))

    async def test_floodwait_reaches_daemon_circuit_breaker(self, tmp_path):
        args = make_args([FakeSource("broken", FloodWait(value=120)), FakeSource("last")])
        manager = MagicMock()
        manager.notify = AsyncMock()
        service = DaemonService(
            check_function=lambda: run_check(*args),
            check_interval=300,
            health_file=tmp_path / "health.txt",
            notification_manager=manager,
        )

        await service.run_check()

        assert (tmp_path / "health.txt").read_text().splitlines()[0] == "error"
        manager.notify.assert_awaited_once()
        kwargs = manager.notify.await_args.kwargs
        assert kwargs["title"] == "Rate Limited by Telegram"
        assert kwargs["force"] is True
