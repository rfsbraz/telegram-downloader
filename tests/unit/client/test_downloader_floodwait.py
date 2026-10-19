"""Unit tests for FloodWait handling in download_media_with_retry (issue #83)."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyrogram.errors import FloodWait

from src.client import downloader
from src.client.downloader import FLOOD_WAIT_MARGIN, download_media_with_retry


def make_config(max_retries=2):
    cfg = MagicMock()
    cfg.max_retries = max_retries
    cfg.base_delay = 0
    cfg.max_delay = 0
    return cfg


@pytest.fixture(autouse=True)
def reset_cooldown():
    downloader._cooldown_until = 0.0
    yield
    downloader._cooldown_until = 0.0


@pytest.fixture
def message():
    msg = MagicMock()
    msg.chat.id = -1001234567890
    msg.id = 42
    return msg


@pytest.fixture
def log():
    return logging.getLogger("test_downloader_floodwait")


def swallowed_flood_wait(seconds):
    """Mimic pyrogram 2.0.106 Client.get_file: log the FloodWait, write 0 bytes."""
    try:
        raise FloodWait(value=seconds)
    except FloodWait as e:
        logging.getLogger("pyrogram.client").exception(e)


def writer(path_holder, outcomes):
    """download_media side effect that plays each outcome in turn."""
    async def _download(message, file_name, progress=None):
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "swallowed":
            swallowed_flood_wait(120)
            open(file_name, "wb").close()
            return file_name
        with open(file_name, "wb") as f:
            f.write(b"data")
        return file_name
    return _download


class TestSwallowedFloodWait:
    async def test_waits_requested_time_and_retries_without_spending_attempt(
        self, tmp_path, message, log
    ):
        dest = tmp_path / "file.bin"
        client = AsyncMock()
        client.download_media = AsyncMock(
            side_effect=writer(None, ["swallowed", "swallowed", "ok"])
        )
        sleep = AsyncMock()
        with patch.object(downloader.asyncio, "sleep", sleep):
            ok = await download_media_with_retry(
                client, message, dest, make_config(max_retries=1), log
            )
        assert ok is True
        assert dest.read_bytes() == b"data"
        assert client.download_media.await_count == 3
        waits = [c.args[0] for c in sleep.await_args_list]
        assert waits.count(pytest.approx(120 + FLOOD_WAIT_MARGIN, abs=1)) == 2
        client.get_messages.assert_not_awaited()

    async def test_cooldown_holds_other_downloads(self, tmp_path, message, log):
        client = AsyncMock()
        client.download_media = AsyncMock(side_effect=writer(None, ["swallowed", "ok"]))
        sleep = AsyncMock()
        with patch.object(downloader.asyncio, "sleep", sleep):
            await download_media_with_retry(
                client, message, tmp_path / "a.bin", make_config(), log
            )
            sleep.reset_mock()
            # Cooldown is still active (sleep was mocked), so a new download waits first
            client.download_media = AsyncMock(side_effect=writer(None, ["ok"]))
            await download_media_with_retry(
                client, message, tmp_path / "b.bin", make_config(), log
            )
        assert sleep.await_count == 1
        assert sleep.await_args.args[0] > 100

    async def test_other_pyrogram_errors_still_use_stale_reference_path(
        self, tmp_path, message, log
    ):
        client = AsyncMock()
        outcomes = ["empty_other", "ok"]

        async def _download(message, file_name, progress=None):
            if outcomes.pop(0) == "empty_other":
                try:
                    raise RuntimeError("boom")
                except RuntimeError as e:
                    logging.getLogger("pyrogram.client").exception(e)
                open(file_name, "wb").close()
            else:
                with open(file_name, "wb") as f:
                    f.write(b"data")

        client.download_media = AsyncMock(side_effect=_download)
        with patch.object(downloader.asyncio, "sleep", AsyncMock()):
            ok = await download_media_with_retry(
                client, message, tmp_path / "c.bin", make_config(), log
            )
        assert ok is True
        client.get_messages.assert_awaited_once()


class TestRaisedFloodWait:
    async def test_raised_flood_wait_does_not_consume_attempts(
        self, tmp_path, message, log
    ):
        dest = tmp_path / "file.bin"
        client = AsyncMock()
        client.download_media = AsyncMock(
            side_effect=writer(None, [FloodWait(value=5), FloodWait(value=5), FloodWait(value=5), "ok"])
        )
        sleep = AsyncMock()
        with patch.object(downloader.asyncio, "sleep", sleep):
            ok = await download_media_with_retry(
                client, message, dest, make_config(max_retries=1), log
            )
        assert ok is True
        assert client.download_media.await_count == 4
        assert pytest.approx(5 + FLOOD_WAIT_MARGIN, abs=1) in [c.args[0] for c in sleep.await_args_list]

    async def test_transient_errors_still_limited(self, tmp_path, message, log):
        client = AsyncMock()
        client.download_media = AsyncMock(side_effect=OSError("net"))
        with patch.object(downloader.asyncio, "sleep", AsyncMock()):
            ok = await download_media_with_retry(
                client, message, tmp_path / "d.bin", make_config(max_retries=3), log
            )
        assert ok is False
        assert client.download_media.await_count == 3
