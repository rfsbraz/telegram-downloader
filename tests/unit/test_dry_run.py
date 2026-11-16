"""Dry-run mode (issue #64).

TDL_DRY_RUN evaluates filters and logs what would download, without
downloading or writing cursor, history, or pending state.
"""
from datetime import datetime, timezone
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


def make_run_args(tmp_path, messages, monkeypatch, *, dry_run=True, history=None, extensions=None):
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
    filt = build_filters(GlobalFilters(extensions=extensions or [".pdf", ".epub", ".mobi"]))

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
        # Construct PatternFilter directly: build_filters still uses the
        # wrong kwargs on main (tracked in #123).
        filt = CompositeFilter([
            PatternFilter(include=["*ebook*"], exclude=["*sample*"]),
        ])
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
