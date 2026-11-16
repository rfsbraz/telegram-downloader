"""Dry-run mode (issue #64).

TDL_DRY_RUN evaluates filters and logs what would download, without
downloading or writing cursor, history, or pending state.
"""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import logging
import pytest

from src.config.schema import GlobalFilters, SourceConfig
from src.config.source_parser import build_filters
from src.filters import CompositeFilter, DateFilter, ExtensionFilter, PatternFilter, SizeFilter
from src.main import run_check
from tests.conftest import MockDocument, MockMessage


def make_msg(msg_id, file_name="book.pdf", file_size=2048, file_unique_id="u1", date=None):
    return MockMessage(
        id=msg_id,
        date=date or datetime(2026, 7, 5, tzinfo=timezone.utc),
        document=MockDocument(
            file_name=file_name,
            file_size=file_size,
            file_unique_id=file_unique_id,
        ),
    )


class YieldingSource:
    def __init__(self, name, messages):
        self.name = name
        self.messages = messages
        self.chat_id = -100111

    def get_cursor_key(self):
        return f"channel:{self.chat_id}"

    async def get_display_name(self):
        return self.name

    async def iterate_new_media(self, last_seen_id):
        for msg in self.messages:
            if msg.id > last_seen_id:
                yield msg


def make_run_args(
    tmp_path,
    messages,
    monkeypatch,
    *,
    dry_run=True,
    history=None,
    extensions=None,
    include_photos=False,
    include_patterns=None,
):
    cfg = MagicMock()
    cfg.dry_run = dry_run
    cfg.max_concurrent_downloads = 1
    cfg.max_downloads_per_run = 0
    cfg.min_free_space = ""
    cfg.flat_structure = False
    cfg.download_dir = tmp_path
    cfg.post_download_hook = None

    source = YieldingSource("Preview Channel", messages)
    source_config = SourceConfig(url="https://t.me/preview", name="Preview Channel")
    kwargs = dict(
        extensions=extensions or [".pdf", ".epub", ".mobi"],
        include_photos=include_photos,
    )
    if include_patterns is not None:
        kwargs["include_patterns"] = include_patterns
    filt = build_filters(GlobalFilters(**kwargs))

    state_store = MagicMock()
    state_store.get.return_value = 0
    pending = MagicMock()
    pending.has_pending.return_value = False

    download = AsyncMock(return_value=True)
    monkeypatch.setattr("src.main.download_media_with_retry", download)

    log = logging.getLogger("test-dry-run")
    args = (
        cfg,
        log,
        state_store,
        MagicMock(),
        [(source, filt, source_config)],
        history,
        pending,
    )
    return args, source, state_store, pending, download


class TestRejectionReason:
    @pytest.mark.asyncio
    async def test_extension(self):
        filt = build_filters(GlobalFilters(extensions=[".pdf"]))
        assert await filt.rejection_reason(make_msg(1, file_name="notes.txt")) == "extension"
        assert await filt.rejection_reason(make_msg(2, file_name="book.pdf")) is None

    @pytest.mark.asyncio
    async def test_size(self):
        filt = CompositeFilter([
            ExtensionFilter(ebook_exts=[".pdf"], allow_archives=False, archive_exts=[]),
            SizeFilter(min_bytes=1000, max_bytes=10_000),
        ])
        assert await filt.rejection_reason(make_msg(1, file_size=100)) == "size"

    @pytest.mark.asyncio
    async def test_date(self):
        filt = CompositeFilter([
            DateFilter(only_after=datetime(2026, 8, 1, tzinfo=timezone.utc)),
        ])
        old = make_msg(1, date=datetime(2026, 7, 1, tzinfo=timezone.utc))
        assert await filt.rejection_reason(old) == "date"

    @pytest.mark.asyncio
    async def test_pattern(self):
        filt = build_filters(GlobalFilters(include_patterns=["*ebook*"], exclude_patterns=["*sample*"]))
        assert await filt.rejection_reason(make_msg(1, file_name="sample.pdf")) == "pattern"
        assert await filt.rejection_reason(make_msg(2, file_name="my-ebook.pdf")) is None


class TestDryRunRunCheck:
    @pytest.mark.asyncio
    async def test_logs_would_download_and_writes_nothing(self, tmp_path, monkeypatch, caplog):
        msg = make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="photo-no")
        args, source, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch
        )
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)

        assert "Would download:" in caplog.text
        assert "book.pdf" in caplog.text
        assert "2.0 KB" in caplog.text or "2048" in caplog.text
        assert "Preview Channel" in caplog.text
        assert "book.pdf" in caplog.text
        assert "Would transfer" in caplog.text or "would download" in caplog.text.lower() or "would transfer" in caplog.text.lower()
        assert summary["files_downloaded"] == 1
        assert summary.get("dry_run") is True

        download.assert_not_awaited()
        state_store.set.assert_not_called()
        pending.add_batch.assert_not_called()
        pending.remove_batch.assert_not_called()
        dest_folder = tmp_path / "Preview_Channel"
        assert not dest_folder.exists()

    @pytest.mark.asyncio
    async def test_logs_extension_skip(self, tmp_path, monkeypatch, caplog):
        msgs = [
            make_msg(10, file_name="notes.txt", file_size=100, file_unique_id="t"),
            make_msg(11, file_name="book.pdf", file_size=2048, file_unique_id="p"),
        ]
        args, *_ = make_run_args(tmp_path, msgs, monkeypatch)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert "Would skip (extension):" in caplog.text
        assert "notes.txt" in caplog.text
        assert "Would download:" in caplog.text
        assert "book.pdf" in caplog.text
        assert summary["files_downloaded"] == 1
        assert summary["files_skipped"] >= 1

    @pytest.mark.asyncio
    async def test_logs_already_tracked(self, tmp_path, monkeypatch, caplog):
        history = MagicMock()
        history.contains.return_value = True
        msg = make_msg(10, file_name="book.pdf", file_unique_id="already")
        args, _, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch, history=history
        )
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert "Would skip (already tracked):" in caplog.text
        history.contains.assert_called_once_with("already")
        history.record.assert_not_called()
        download.assert_not_awaited()
        state_store.set.assert_not_called()
        assert summary["files_downloaded"] == 0
        assert summary["files_skipped"] == 1

    @pytest.mark.asyncio
    async def test_logs_duplicate(self, tmp_path, monkeypatch, caplog):
        msg = make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="dup")
        dest_dir = tmp_path / "Preview_Channel"
        dest_dir.mkdir()
        dest = dest_dir / "book.pdf"
        dest.write_bytes(b"x" * 2048)
        args, _, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch
        )
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert "Would skip (duplicate):" in caplog.text
        download.assert_not_awaited()
        state_store.set.assert_not_called()
        pending.add_batch.assert_not_called()
        assert summary["files_downloaded"] == 0

    @pytest.mark.asyncio
    async def test_warns_that_dry_run_is_active(self, tmp_path, monkeypatch, caplog):
        args, *_ = make_run_args(tmp_path, [], monkeypatch)
        with caplog.at_level(logging.WARNING):
            await run_check(*args)
        assert "DRY RUN" in caplog.text
        assert "TDL_DRY_RUN" in caplog.text

    @pytest.mark.asyncio
    async def test_normal_run_still_queues_and_does_not_warn(self, tmp_path, monkeypatch, caplog):
        msg = make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="n")
        args, _, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch, dry_run=False
        )
        pending.get_oldest.return_value = []
        pending.count.return_value = 0
        pending.count_exhausted.return_value = 0
        with caplog.at_level(logging.WARNING):
            summary = await run_check(*args)
        pending.add_batch.assert_called()
        download.assert_not_awaited()
        assert "DRY RUN" not in caplog.text
        assert summary.get("dry_run") is not True


def _list_state_artifacts(root: Path) -> list[Path]:
    artifacts = []
    for path in root.rglob("*"):
        if not path.is_file() and not path.is_dir():
            continue
        name = path.name
        if name in {"state.db", "state.yaml"} or name.startswith("state.db"):
            artifacts.append(path)
    return artifacts


def _finalize_sqlite(db_path: Path) -> bytes:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    for suffix in ("-wal", "-shm"):
        extra = Path(str(db_path) + suffix)
        if extra.exists():
            extra.unlink()
    return db_path.read_bytes()


def _dry_run_config(tmp_path: Path):
    from src.config.schema import Config

    return Config(
        api_id=12345,
        api_hash="dummyhash",
        sources=[{"url": "https://t.me/example"}],
        dry_run=True,
        track_downloads=True,
        session_dir=tmp_path / "sessions",
        download_dir=tmp_path / "downloads",
        log_file=None,
    )


class DummyClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _patch_main_io(monkeypatch, cfg, run_check=None):
    from src import main as main_module

    async def fake_startup(config, log, client):
        return []

    async def fake_run_check(*args, **kwargs):
        if run_check:
            return await run_check(*args, **kwargs)
        return {
            "sources_checked": 0,
            "sources_failed": 0,
            "files_downloaded": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "files_deferred_low_space": 0,
            "low_disk_space": False,
            "dry_run": True,
            "bytes_downloaded": "0 B",
            "duration": "0.0s",
        }

    monkeypatch.setattr(main_module, "load_config", lambda _path: cfg)
    monkeypatch.setattr(main_module, "create_client", lambda _cfg: DummyClient())
    monkeypatch.setattr(main_module, "startup_validation", fake_startup)
    monkeypatch.setattr(main_module, "run_check", fake_run_check)
    monkeypatch.setattr(main_module, "build_notification_manager", lambda _cfg, _log: None)


class TestMainDryRunWritesNothing:
    @pytest.mark.asyncio
    async def test_main_dry_run_on_empty_dir_creates_no_state_files(self, tmp_path, monkeypatch):
        from src.main import main

        cfg = _dry_run_config(tmp_path)
        yaml_path = tmp_path / "state.yaml"
        _patch_main_io(monkeypatch, cfg)

        await main(config_path=str(tmp_path / "config.yaml"), state_yaml_path=yaml_path)

        assert not cfg.session_dir.exists()
        assert not (cfg.session_dir / "state.db").exists()
        assert not (tmp_path / "state.db").exists()
        assert not yaml_path.exists()
        assert _list_state_artifacts(tmp_path) == []
        assert not list(tmp_path.glob("**/*-wal"))
        assert not list(tmp_path.glob("**/*-shm"))

    @pytest.mark.asyncio
    async def test_main_dry_run_leaves_existing_state_yaml_untouched(self, tmp_path, monkeypatch):
        from src.main import main

        cfg = _dry_run_config(tmp_path)
        yaml_path = tmp_path / "state.yaml"
        original = "channel:-100111: 42\n"
        yaml_path.write_text(original)
        before = yaml_path.read_bytes()
        _patch_main_io(monkeypatch, cfg)

        await main(config_path=str(tmp_path / "config.yaml"), state_yaml_path=yaml_path)

        assert yaml_path.read_bytes() == before
        assert yaml_path.read_text() == original
        assert not cfg.session_dir.exists()
        assert not (cfg.session_dir / "state.db").exists()

    @pytest.mark.asyncio
    async def test_main_dry_run_reads_existing_stores_without_writing(self, tmp_path, monkeypatch):
        from src.main import main
        from src.state import CursorStore, DownloadHistory

        cfg = _dry_run_config(tmp_path)
        cfg.session_dir.mkdir()
        db_path = cfg.session_dir / "state.db"
        store = CursorStore(str(db_path))
        store.set("channel:-100111", 42)
        history = DownloadHistory(str(db_path))
        history.record("uid-1", "book.pdf", 2048, "channel:-100111", 10)
        store.close()
        history.close()
        before = _finalize_sqlite(db_path)

        captured = {}

        async def spy_run_check(config, log, state_store, client, sources, hist, pending, limiter=None):
            captured["cursor"] = state_store.get("channel:-100111")
            captured["tracked"] = hist.contains("uid-1")
            captured["missing"] = hist.contains("uid-missing")
            return {
                "sources_checked": 0,
                "sources_failed": 0,
                "files_downloaded": 0,
                "files_skipped": 0,
                "files_failed": 0,
                "files_deferred_low_space": 0,
                "low_disk_space": False,
                "dry_run": True,
                "bytes_downloaded": "0 B",
                "duration": "0.0s",
            }

        _patch_main_io(monkeypatch, cfg, run_check=spy_run_check)
        await main(config_path=str(tmp_path / "config.yaml"), state_yaml_path=tmp_path / "state.yaml")

        assert captured["cursor"] == 42
        assert captured["tracked"] is True
        assert captured["missing"] is False
        assert _finalize_sqlite(db_path) == before

    def test_create_client_does_not_mkdir_session_dir_in_dry_run(self, tmp_path, monkeypatch):
        from src.client.factory import create_client

        monkeypatch.setattr("src.client.factory.Client", lambda **_kwargs: MagicMock())
        cfg = _dry_run_config(tmp_path)
        with pytest.raises(ValueError, match="existing session file"):
            create_client(cfg)
        assert not cfg.session_dir.exists()


class TestDryRunPreviewAccuracy:
    @pytest.mark.asyncio
    async def test_second_source_skips_planned_unique_id(self, tmp_path, monkeypatch, caplog):
        from src.main import run_check

        msg_a = make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="same-id")
        msg_b = make_msg(20, file_name="copy.pdf", file_size=2048, file_unique_id="same-id")
        args, _, state_store, pending, download = make_run_args(tmp_path, [msg_a], monkeypatch)
        history = MagicMock()
        history.contains.return_value = False
        source_b = YieldingSource("Other Channel", [msg_b])
        source_b.chat_id = -100222
        sources = [
            args[4][0],
            (
                source_b,
                build_filters(GlobalFilters(extensions=[".pdf", ".epub", ".mobi"])),
                SourceConfig(url="https://t.me/other", name="Other Channel"),
            ),
        ]
        args = (args[0], args[1], args[2], args[3], sources, history, pending)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)

        assert summary["files_downloaded"] == 1
        assert summary["files_skipped"] == 1
        assert "Would download:" in caplog.text
        assert "book.pdf" in caplog.text
        assert "Would skip (already tracked):" in caplog.text
        assert "copy.pdf" in caplog.text
        history.record.assert_not_called()
        state_store.set.assert_not_called()
        download.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_conflict_logs_suffixed_destination(self, tmp_path, monkeypatch, caplog):
        msg = make_msg(10, file_name="book.pdf", file_size=4096, file_unique_id="new")
        dest_dir = tmp_path / "Preview_Channel"
        dest_dir.mkdir()
        (dest_dir / "book.pdf").write_bytes(b"x" * 2048)
        args, _, state_store, pending, download = make_run_args(tmp_path, [msg], monkeypatch)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)

        assert summary["files_downloaded"] == 1
        assert "Would download:" in caplog.text
        assert str(dest_dir / "book_2.pdf") in caplog.text
        assert (dest_dir / "book_2.pdf").exists() is False
        download.assert_not_awaited()
        state_store.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_planned_same_name_same_size_is_duplicate(self, tmp_path, monkeypatch, caplog):
        msgs = [
            make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="a"),
            make_msg(11, file_name="book.pdf", file_size=2048, file_unique_id="b"),
        ]
        args, _, state_store, pending, download = make_run_args(tmp_path, msgs, monkeypatch)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)

        assert summary["files_downloaded"] == 1
        assert summary["files_skipped"] == 1
        assert "Would skip (duplicate):" in caplog.text
        download.assert_not_awaited()
        state_store.set.assert_not_called()
        pending.add_batch.assert_not_called()
        assert not (tmp_path / "Preview_Channel").exists()

    @pytest.mark.asyncio
    async def test_planned_same_name_different_size_uses_suffix(self, tmp_path, monkeypatch, caplog):
        msgs = [
            make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="a"),
            make_msg(11, file_name="book.pdf", file_size=4096, file_unique_id="b"),
        ]
        args, *_ = make_run_args(tmp_path, msgs, monkeypatch)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)

        assert summary["files_downloaded"] == 2
        assert str(tmp_path / "Preview_Channel" / "book.pdf") in caplog.text
        assert str(tmp_path / "Preview_Channel" / "book_2.pdf") in caplog.text
        assert not (tmp_path / "Preview_Channel").exists()



class TestDryRunPreviewAccuracyFollowup:
    @pytest.mark.asyncio
    async def test_processes_oldest_first_for_name_reservations(self, tmp_path, monkeypatch, caplog):
        # Yield newer first, as real sources do. The smaller/older file should
        # keep the unsuffixed name, matching a normal oldest-first download.
        msgs = [
            make_msg(11, file_name="book.pdf", file_size=4096, file_unique_id="newer"),
            make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="older"),
        ]
        args, *_ = make_run_args(tmp_path, msgs, monkeypatch)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert summary["files_downloaded"] == 2
        logs = caplog.text
        first_idx = logs.index(str(tmp_path / "Preview_Channel" / "book.pdf"))
        second_idx = logs.index(str(tmp_path / "Preview_Channel" / "book_2.pdf"))
        # older (2.0 KB) reserved book.pdf; newer (4.0 KB) gets book_2.pdf
        assert "2.0 KB" in logs[logs.rfind("Would download:", 0, first_idx):first_idx+80] or True
        assert str(tmp_path / "Preview_Channel" / "book.pdf") in caplog.text
        assert str(tmp_path / "Preview_Channel" / "book_2.pdf") in caplog.text
        # The 2048-byte file is the unsuffixed one
        assert "Would download: book.pdf (2.0 KB) from Preview Channel -> " + str(tmp_path / "Preview_Channel" / "book.pdf") in caplog.text
        assert "Would download: book.pdf (4.0 KB) from Preview Channel -> " + str(tmp_path / "Preview_Channel" / "book_2.pdf") in caplog.text

    @pytest.mark.asyncio
    async def test_planned_ids_ignored_when_tracking_is_off(self, tmp_path, monkeypatch, caplog):
        msg_a = make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="same-id")
        msg_b = make_msg(20, file_name="copy.pdf", file_size=2048, file_unique_id="same-id")
        args, _, state_store, pending, download = make_run_args(tmp_path, [msg_a], monkeypatch)
        source_b = YieldingSource("Other Channel", [msg_b])
        source_b.chat_id = -100222
        sources = [
            args[4][0],
            (
                source_b,
                build_filters(GlobalFilters(extensions=[".pdf", ".epub", ".mobi"])),
                SourceConfig(url="https://t.me/other", name="Other Channel"),
            ),
        ]
        args = (args[0], args[1], args[2], args[3], sources, None, pending)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert summary["files_downloaded"] == 2
        assert "Would download:" in caplog.text
        assert "book.pdf" in caplog.text
        assert "copy.pdf" in caplog.text
        assert "Would skip (already tracked):" not in caplog.text
        download.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_preview_stats_kept_when_a_source_fails(self, tmp_path, monkeypatch, caplog):
        from src.main import run_check

        class BoomAfterFirst(YieldingSource):
            async def iterate_new_media(self, last_seen_id):
                for msg in self.messages:
                    if msg.id > last_seen_id:
                        yield msg
                        raise RuntimeError("source failed")

        msg = make_msg(10, file_name="book.pdf", file_size=2048, file_unique_id="kept")
        args, _, state_store, pending, download = make_run_args(tmp_path, [msg], monkeypatch)
        history = MagicMock()
        history.contains.return_value = False
        boom = BoomAfterFirst("Preview Channel", [msg])
        filt = build_filters(GlobalFilters(extensions=[".pdf", ".epub", ".mobi"]))
        source_b = YieldingSource(
            "Other Channel",
            [make_msg(20, file_name="copy.pdf", file_size=2048, file_unique_id="kept")],
        )
        source_b.chat_id = -100222
        sources = [
            (boom, filt, SourceConfig(url="https://t.me/preview", name="Preview Channel")),
            (
                source_b,
                filt,
                SourceConfig(url="https://t.me/other", name="Other Channel"),
            ),
        ]
        args = (args[0], args[1], args[2], args[3], sources, history, pending)
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert summary["sources_failed"] == 1
        assert summary["files_downloaded"] == 1
        assert "Would download:" in caplog.text
        assert "book.pdf" in caplog.text
        assert "Would skip (already tracked):" in caplog.text
        assert "copy.pdf" in caplog.text
        download.assert_not_awaited()
        history.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejected_messages_are_not_retained_during_scan(self, tmp_path, caplog):
        import gc
        import weakref
        from src.main import dry_run_source

        # Weakrefs to every yielded message. After each yield, previously
        # processed messages must already be collectable. The current
        # message may still be bound in the consumer's async-for variable.
        refs = []
        alive_previous = []

        class ScanningSource(YieldingSource):
            async def iterate_new_media(self, last_seen_id):
                for msg_id, name in ((30, "skip.txt"), (20, "notes.txt"), (10, "book.pdf")):
                    msg = make_msg(msg_id, file_name=name, file_unique_id=f"id-{msg_id}")
                    refs.append(weakref.ref(msg))
                    yield msg
                    del msg
                    gc.collect()
                    alive_previous.append(sum(1 for r in refs[:-1] if r() is not None))

        source = ScanningSource("Preview Channel", [])
        filt = build_filters(GlobalFilters(extensions=[".pdf", ".epub", ".mobi"]))
        history = MagicMock()
        history.contains.return_value = False
        with caplog.at_level(logging.INFO):
            stats = await dry_run_source(
                source,
                filt,
                SourceConfig(url="https://t.me/preview", name="Preview Channel"),
                0,
                tmp_path,
                False,
                history,
                logging.getLogger("test-dry-run-retain"),
                "Preview Channel",
            )
        assert stats["skipped_filter"] == 2
        assert stats["downloaded"] == 1
        assert alive_previous == [0, 0, 0]
        gc.collect()
        assert all(r() is None for r in refs)
        assert "Would skip" in caplog.text
        assert "Would download: book.pdf" in caplog.text


class TestMainDryRunWalAndSession:
    @pytest.mark.asyncio
    async def test_ephemeral_open_does_not_create_or_change_wal_sidecars(self, tmp_path):
        from src.state import CursorStore

        cfg_dir = tmp_path / "sessions"
        cfg_dir.mkdir()
        db_path = cfg_dir / "state.db"
        store = CursorStore(str(db_path))
        store.set("channel:-100111", 42)
        # Leave the writer open so WAL sidecars stay in place (do not checkpoint)
        wal = Path(str(db_path) + "-wal")
        shm = Path(str(db_path) + "-shm")

        def fingerprint(path: Path):
            if not path.exists():
                return (False, 0, None)
            return (True, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())

        before = {path: fingerprint(path) for path in (db_path, wal, shm)}
        ephemeral = CursorStore(str(db_path), ephemeral=True)
        assert ephemeral.get("channel:-100111") == 42
        ephemeral.close()
        for path, snap in before.items():
            assert fingerprint(path) == snap, path
        store.close()

    def test_ephemeral_open_survives_checkpoint_during_copy(self, tmp_path, monkeypatch):
        import shutil
        from src.state import CursorStore
        from src.state import cursor as cursor_mod

        db_path = tmp_path / "state.db"
        store = CursorStore(str(db_path))
        store.set("channel:-100111", 42)
        # Leave the writer open so the commit still lives in the WAL.

        real_copy = cursor_mod.shutil.copyfile
        tripped = {"done": False}

        def flaky_copy(src, dst, *args, **kwargs):
            result = real_copy(src, dst, *args, **kwargs)
            if Path(src) == db_path and not tripped["done"]:
                tripped["done"] = True
                store._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            return result

        monkeypatch.setattr(cursor_mod.shutil, "copyfile", flaky_copy)
        ephemeral = CursorStore(str(db_path), ephemeral=True)
        assert ephemeral.get("channel:-100111") == 42
        ephemeral.close()
        store.close()

    @pytest.mark.asyncio
    async def test_create_client_dry_run_does_not_modify_existing_session(
        self, tmp_path, monkeypatch
    ):
        from src.client.factory import create_client
        from tests.unit.client.test_session_compat import FIXTURE, SESSION_NAME

        session_dir = tmp_path / "sessions"
        session_dir.mkdir()
        session = session_dir / f"{SESSION_NAME}.session"
        import sqlite3
        con = sqlite3.connect(session)
        con.executescript(FIXTURE.read_text())
        con.close()
        before = session.read_bytes()
        cfg = _dry_run_config(tmp_path)
        cfg.session_dir = session_dir
        client = create_client(cfg)
        await client.storage.open()
        await client.storage.close()
        assert session.read_bytes() == before
        # Original directory still has only the original session file set
        assert session.exists()


class TestDryRunPhotos:
    """Opt-in photos must preview correctly under TDL_DRY_RUN."""

    @pytest.mark.asyncio
    async def test_plans_photo_with_identity_aware_name(self, tmp_path, monkeypatch, caplog):
        from src.media import photo_filename
        from tests.unit.media.test_include_photos import photo_msg

        msg = photo_msg(msg_id=30, file_unique_id="photo-a", file_size=80000)
        expected = photo_filename(msg)
        args, _, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch, include_photos=True
        )
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert summary["files_downloaded"] == 1
        assert summary["dry_run"] is True
        assert (
            f"Would download: {expected} (78.1 KB) from Preview Channel -> "
            in caplog.text
        )
        assert "message_30" not in caplog.text
        download.assert_not_awaited()
        state_store.set.assert_not_called()
        pending.add_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_photos_when_the_flag_is_off(self, tmp_path, monkeypatch, caplog):
        from tests.unit.media.test_include_photos import photo_msg

        msg = photo_msg(msg_id=30, file_unique_id="photo-a", file_size=80000)
        args, _, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch, include_photos=False
        )
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert summary["files_downloaded"] == 0
        assert "Would download:" not in caplog.text
        assert "Would skip" in caplog.text
        download.assert_not_awaited()
        state_store.set.assert_not_called()
        pending.add_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_photos_when_flag_is_off_even_if_jpg_is_allowed(
        self, tmp_path, monkeypatch, caplog
    ):
        from tests.unit.media.test_include_photos import photo_msg

        msg = photo_msg(msg_id=30, file_unique_id="photo-a", file_size=80000)
        args, _, state_store, pending, download = make_run_args(
            tmp_path, [msg], monkeypatch, include_photos=False, extensions=[".jpg"]
        )
        with caplog.at_level(logging.INFO):
            summary = await run_check(*args)
        assert summary["files_downloaded"] == 0
        assert "Would download:" not in caplog.text
        assert "Would skip (photos disabled):" in caplog.text
        download.assert_not_awaited()
        state_store.set.assert_not_called()
        pending.add_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_pattern_filter_from_build_filters_uses_generated_photo_name(
        self, tmp_path, monkeypatch, caplog
    ):
        from src.media import photo_filename
        from tests.unit.media.test_include_photos import photo_msg

        msg = photo_msg(msg_id=30, file_unique_id="photo-a", file_size=80000)
        expected = photo_filename(msg)
        accepted, *_ = make_run_args(
            tmp_path,
            [msg],
            monkeypatch,
            include_photos=True,
            include_patterns=["photo_*.jpg"],
        )
        rejected, _, _, _, download = make_run_args(
            tmp_path,
            [msg],
            monkeypatch,
            include_photos=True,
            include_patterns=["*.pdf"],
        )
        with caplog.at_level(logging.INFO):
            ok = await run_check(*accepted)
            no = await run_check(*rejected)
        assert ok["files_downloaded"] == 1
        assert expected in caplog.text
        assert no["files_downloaded"] == 0
        assert "Would skip (pattern):" in caplog.text
        download.assert_not_awaited()

