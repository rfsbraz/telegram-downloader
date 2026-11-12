"""
Unit tests for the disk-full guard (issue #61).

A download that does not fit in the free space minus the reserve is
deferred (kept pending, cursor untouched) instead of failing through the
retry loop, a volume already below the reserve skips the whole check with
one error, and the daemon sends a forced notification.
"""
import errno
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.client import diskspace
from src.client.downloader import DiskFullError, download_media_with_retry
from src.config.schema import Config
from src.daemon.service import DaemonService
from src import main as main_module
from src.main import download_batch, run_check

GB = 1024 ** 3


def set_free(monkeypatch, free):
    monkeypatch.setattr(diskspace, "free_bytes", lambda path: free)


def make_msg(msg_id=7, size=2 * GB):
    msg = MagicMock()
    msg.id = msg_id
    msg.document.file_name = "book.pdf"
    msg.document.file_size = size
    msg.document.file_unique_id = f"u{msg_id}"
    return msg


def make_cfg(reserve="1GB"):
    cfg = MagicMock()
    cfg.min_free_space = reserve
    cfg.flat_structure = True
    cfg.post_download_hook = None
    cfg.max_retries = 3
    cfg.base_delay = 0
    cfg.max_delay = 0
    return cfg


async def run_batch(tmp_path, monkeypatch, msgs, cfg):
    import asyncio

    async def fake_dest(download_dir, source, fname, source_config, flat):
        return download_dir / fname

    monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
    retry = AsyncMock(return_value=True)
    monkeypatch.setattr(main_module, "download_media_with_retry", retry)
    cursor = MagicMock()
    result = await download_batch(
        msgs,
        asyncio.Semaphore(1),
        MagicMock(),
        tmp_path,
        cursor,
        "key",
        cfg,
        logging.getLogger("test-disk"),
        MagicMock(),
        MagicMock(),
    )
    return result, retry, cursor


class TestPerFileCheck:

    async def test_file_that_does_not_fit_is_deferred(self, tmp_path, monkeypatch, caplog):
        set_free(monkeypatch, 2 * GB)
        with caplog.at_level(logging.ERROR):
            (stats, failed, deferred), retry, cursor = await run_batch(
                tmp_path, monkeypatch, [make_msg(size=2 * GB)], make_cfg("1GB")
            )
        retry.assert_not_awaited()
        cursor.set.assert_not_called()
        assert failed == set()
        assert deferred == {7}
        assert stats["deferred_low_space"] == 1
        assert "Not enough free space" in caplog.text

    async def test_file_that_fits_is_downloaded(self, tmp_path, monkeypatch):
        set_free(monkeypatch, 4 * GB)
        (stats, failed, deferred), retry, _ = await run_batch(
            tmp_path, monkeypatch, [make_msg(size=2 * GB)], make_cfg("1GB")
        )
        retry.assert_awaited_once()
        assert deferred == set()
        assert stats["downloaded"] == 1

    async def test_disk_full_during_download_is_deferred(self, tmp_path, monkeypatch):
        set_free(monkeypatch, 10 * GB)

        async def fake_dest(download_dir, source, fname, source_config, flat):
            return download_dir / fname

        monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
        monkeypatch.setattr(
            main_module, "download_media_with_retry", AsyncMock(side_effect=DiskFullError("full"))
        )
        import asyncio

        stats, failed, deferred = await download_batch(
            [make_msg()], asyncio.Semaphore(1), MagicMock(), tmp_path, MagicMock(), "key",
            make_cfg(), logging.getLogger("t"), MagicMock(), MagicMock(),
        )
        assert failed == set()
        assert deferred == {7}


class TestDownloaderEnospc:

    async def test_enospc_stops_retrying_and_removes_the_partial(self, tmp_path):
        client = AsyncMock()
        calls = []

        async def fake_download(msg, file_name, progress=None):
            calls.append(file_name)
            Path(file_name).write_bytes(b"x")
            raise OSError(errno.ENOSPC, "No space left on device")

        client.download_media.side_effect = fake_download
        msg = MagicMock()
        msg.id = 42
        with pytest.raises(DiskFullError):
            await download_media_with_retry(
                client, msg, tmp_path / "f.pdf", make_cfg(), logging.getLogger("t")
            )
        assert len(calls) == 1
        assert list(tmp_path.iterdir()) == []


class FakeSource:
    def __init__(self):
        self.scanned = False

    def get_cursor_key(self):
        return "s:"

    async def get_display_name(self):
        return "s"

    async def iterate_new_media(self, last_seen_id):
        self.scanned = True
        return
        yield  # pragma: no cover


class TestVolumeBelowReserve:

    async def test_check_is_skipped_with_one_error(self, tmp_path, monkeypatch, caplog):
        set_free(monkeypatch, GB // 2)
        cfg = make_cfg("1GB")
        cfg.download_dir = tmp_path
        source = FakeSource()
        pending = MagicMock()
        with caplog.at_level(logging.ERROR):
            summary = await run_check(
                cfg, logging.getLogger("t"), MagicMock(), MagicMock(),
                [(source, MagicMock(), MagicMock())], None, pending,
            )
        assert not source.scanned
        assert summary["low_disk_space"]
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errors) == 1
        assert "below the reserve" in errors[0].getMessage()


class TestDaemonNotification:

    async def test_low_disk_space_sends_a_forced_error(self, tmp_path):
        manager = AsyncMock()
        check = AsyncMock(return_value={"low_disk_space": True, "free_space": "512.0 MB"})
        service = DaemonService(
            check_function=check,
            check_interval=300,
            health_file=tmp_path / "health.txt",
            notification_manager=manager,
        )
        await service.run_check()
        levels = [(c.kwargs["level"], c.kwargs.get("force")) for c in manager.notify.await_args_list]
        assert ("error", True) in levels


class TestConfig:

    def test_default_reserve_is_1gb(self):
        cfg = Config(api_id=1, api_hash="x")
        from src.config.source_parser import parse_size

        assert diskspace.reserve_bytes(cfg) == parse_size("1GB")

    def test_env_var_sets_the_reserve(self, monkeypatch):
        from src.config.loader import _load_from_env

        monkeypatch.setenv("TDL_MIN_FREE_SPACE", "5GB")
        assert _load_from_env()["min_free_space"] == "5GB"

    def test_invalid_reserve_is_rejected(self):
        with pytest.raises(ValueError):
            Config(api_id=1, api_hash="x", min_free_space="lots")


class TestDeferredStayPending:

    async def test_deferred_download_stays_pending_and_ends_the_source(
        self, tmp_path, monkeypatch
    ):
        set_free(monkeypatch, 2 * GB)

        async def fake_dest(download_dir, source, fname, source_config, flat):
            return download_dir / fname

        monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
        retry = AsyncMock(return_value=True)
        monkeypatch.setattr(main_module, "download_media_with_retry", retry)

        cfg = make_cfg("1GB")
        cfg.download_dir = tmp_path
        cfg.max_concurrent_downloads = 1
        cfg.max_downloads_per_run = 0
        cfg.max_download_attempts = 5
        source = FakeSource()
        source.chat_id = 1
        pending = MagicMock()
        pending.has_pending.return_value = True
        pending.get_max_message_id.return_value = 7
        pending.get_oldest.return_value = [7]  # the same item every time
        pending.count.return_value = 1
        pending.count_exhausted.return_value = 0
        client = MagicMock()
        client.get_messages = AsyncMock(return_value=[make_msg(size=2 * GB)])
        state = MagicMock()
        state.get.return_value = 0

        summary = await run_check(
            cfg, logging.getLogger("t"), state, client,
            [(source, MagicMock(), MagicMock())], None, pending,
        )

        retry.assert_not_awaited()
        removed = [i for c in pending.remove_batch.call_args_list for i in c.args[1]]
        assert 7 not in removed
        pending.increment_attempts.assert_not_called()
        assert summary["files_deferred_low_space"] == 1
        assert summary["low_disk_space"] is True

    def test_zero_turns_the_check_off(self, monkeypatch):
        # Without humanfriendly, parse_size needs a unit; "0" is the documented off switch.
        import builtins

        real_import = builtins.__import__

        def no_humanfriendly(name, *args, **kwargs):
            if name == "humanfriendly":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_humanfriendly)
        cfg = Config(api_id=1, api_hash="x", min_free_space="0")
        assert diskspace.reserve_bytes(cfg) == 0


class TestConcurrentDownloads:

    async def test_in_flight_downloads_count_against_the_free_space(self, tmp_path, monkeypatch):
        # 4 GB free, 1 GB reserve: two 2 GB files can't both start (Copilot on #115).
        import asyncio

        set_free(monkeypatch, 4 * GB)

        async def fake_dest(download_dir, source, fname, source_config, flat):
            return download_dir / fname

        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_download(*args, **kwargs):
            started.set()
            await release.wait()
            return True

        monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
        monkeypatch.setattr(main_module, "download_media_with_retry", AsyncMock(side_effect=slow_download))
        a, b = make_msg(1, 2 * GB), make_msg(2, 2 * GB)
        b.document.file_name = "other.pdf"
        batch = asyncio.create_task(download_batch(
            [a, b], asyncio.Semaphore(2), MagicMock(), tmp_path, MagicMock(), "key",
            make_cfg("1GB"), logging.getLogger("t"), MagicMock(), MagicMock(),
        ))
        await started.wait()
        await asyncio.sleep(0)
        release.set()
        stats, failed, deferred = await batch
        assert stats["downloaded"] == 1
        assert deferred == {2}


    async def test_bytes_already_written_are_not_counted_twice(self, tmp_path, monkeypatch):
        # free_bytes already reflects what a running transfer wrote; only its unwritten
        # rest is reserved (Copilot on #115). 4 GB free, 1 GB reserve, the first 2 GB file
        # has written 1.5 GB: 0.5 GB still reserved, so a 2 GB file fits.
        import asyncio

        set_free(monkeypatch, 4 * GB)
        # The client streams into "<partial>.temp" until it finishes. Sparse: 1.5 GB by
        # size, nothing on disk.
        with open(tmp_path / "book.pdf.1.partial.temp", "wb") as partial:
            partial.truncate(GB + GB // 2)

        async def fake_dest(download_dir, source, fname, source_config, flat):
            return download_dir / fname

        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_download(*args, **kwargs):
            started.set()
            await release.wait()
            return True

        monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
        monkeypatch.setattr(main_module, "download_media_with_retry", AsyncMock(side_effect=slow_download))
        a, b = make_msg(1, 2 * GB), make_msg(2, 2 * GB)
        b.document.file_name = "other.pdf"
        batch = asyncio.create_task(download_batch(
            [a, b], asyncio.Semaphore(2), MagicMock(), tmp_path, MagicMock(), "key",
            make_cfg("1GB"), logging.getLogger("t"), MagicMock(), MagicMock(),
        ))
        await started.wait()
        await asyncio.sleep(0)
        release.set()
        stats, failed, deferred = await batch
        assert stats["downloaded"] == 2
        assert deferred == set()


class TestEnospcOutsideTheTransfer:

    async def test_enospc_creating_the_destination_is_deferred(self, tmp_path, monkeypatch):
        import asyncio

        set_free(monkeypatch, 10 * GB)

        async def full_dest(download_dir, source, fname, source_config, flat):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(main_module, "build_destination_path", full_dest)
        cursor = MagicMock()
        stats, failed, deferred = await download_batch(
            [make_msg()], asyncio.Semaphore(1), MagicMock(), tmp_path, cursor, "key",
            make_cfg(), logging.getLogger("t"), MagicMock(), MagicMock(),
        )
        assert deferred == {7} and failed == set()
        cursor.set.assert_not_called()

    async def test_enospc_creating_the_folder_in_the_downloader_is_disk_full(self, tmp_path, monkeypatch):
        def full_mkdir(self, *args, **kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(Path, "mkdir", full_mkdir)
        msg = MagicMock()
        msg.id = 42
        with pytest.raises(DiskFullError):
            await download_media_with_retry(
                AsyncMock(), msg, tmp_path / "new" / "f.pdf", make_cfg(), logging.getLogger("t")
            )

    async def test_empty_file_with_no_space_left_is_disk_full_not_a_retry(self, tmp_path, monkeypatch):
        # The client can log ENOSPC and hand back an empty file; then the disk is the cause.
        set_free(monkeypatch, 0)
        client = AsyncMock()
        calls = []

        async def empty_download(msg, file_name, progress=None):
            calls.append(file_name)
            Path(file_name).write_bytes(b"")
            return file_name

        client.download_media.side_effect = empty_download
        msg = MagicMock()
        msg.id = 42
        with pytest.raises(DiskFullError):
            await download_media_with_retry(
                client, msg, tmp_path / "f.pdf", make_cfg(), logging.getLogger("t"), expected_size=2 * GB
            )
        assert len(calls) == 1
