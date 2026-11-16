"""Opt-in Telegram photo downloads (issue #59).

Photos are ignored by default. When include_photos is on, the largest
size is selected, a photo_<date>_<id>.jpg name is generated, and
file_unique_id still feeds history-based dedup.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import asyncio
import logging

import pytest

from src.config.schema import GlobalFilters
from src.config.source_parser import build_filters
from src.filters.extension import ExtensionFilter
from src.filters.pattern import PatternFilter
from src.filters.size import SizeFilter
from src.media import (
    collect_matching_ids,
    get_media,
    is_photo_only,
    largest_photo,
    media_filename,
    photo_filename,
)
from src.sources.channel import ChannelSource
from src.sources.forum_topic import ForumTopicSource
from tests.conftest import MockDocument, MockMessage, MockPhoto


PHOTO_DATE = datetime(2026, 7, 5)
PHOTO_ID = 12345
PHOTO_NAME = "photo_2026-07-05_12345.jpg"


def photo_msg(
    msg_id: int = PHOTO_ID,
    date: datetime = PHOTO_DATE,
    photo: MockPhoto | None = None,
    **photo_kwargs,
) -> MockMessage:
    return MockMessage(
        id=msg_id,
        date=date,
        document=None,
        photo=photo if photo is not None else MockPhoto(**photo_kwargs),
    )


def document_msg(msg_id: int = 1, file_name: str = "book.pdf", file_size: int = 2048) -> MockMessage:
    return MockMessage(
        id=msg_id,
        date=PHOTO_DATE,
        document=MockDocument(file_name=file_name, file_size=file_size),
    )


class TestPhotoHelpers:
    def test_is_photo_only(self):
        assert is_photo_only(photo_msg()) is True
        assert is_photo_only(document_msg()) is False
        assert is_photo_only(MockMessage(id=1, document=None, photo=None)) is False

    def test_document_takes_precedence_over_photo(self):
        msg = document_msg()
        msg.photo = MockPhoto()
        assert is_photo_only(msg) is False
        media = get_media(msg, include_photos=True)
        assert media is msg.document

    def test_get_media_skips_photos_by_default(self):
        assert get_media(photo_msg()) is None
        assert get_media(photo_msg(), include_photos=False) is None

    def test_get_media_returns_photo_when_enabled(self):
        msg = photo_msg()
        assert get_media(msg, include_photos=True) is msg.photo

    def test_largest_photo_is_the_kurigram_photo(self):
        photo = MockPhoto(file_size=80000, width=1280, height=720)
        assert largest_photo(photo_msg(photo=photo)) is photo

    def test_largest_photo_picks_the_biggest_size(self):
        small = SimpleNamespace(width=90, height=90, file_size=1200, file_unique_id="s")
        large = SimpleNamespace(width=2000, height=1500, file_size=91000, file_unique_id="l")
        photo = MockPhoto(sizes=[small, large], file_size=1200, width=90, height=90)
        assert largest_photo(photo_msg(photo=photo)) is large

    def test_photo_filename_uses_message_date_and_id(self):
        assert photo_filename(photo_msg()) == PHOTO_NAME

    def test_media_filename_generates_jpg_for_photos(self):
        msg = photo_msg()
        assert media_filename(msg, msg.photo) == PHOTO_NAME

    def test_media_filename_keeps_document_names(self):
        msg = document_msg(file_name="paper.epub")
        assert media_filename(msg, msg.document) == "paper.epub"


class TestExtensionFilterPhotos:
    def _filter(self, **kwargs):
        defaults = dict(ebook_exts=[".pdf", ".epub", ".mobi"], allow_archives=False, archive_exts=[".zip"])
        defaults.update(kwargs)
        return ExtensionFilter(**defaults)

    @pytest.mark.asyncio
    async def test_generated_name_is_treated_as_jpg(self):
        filt = self._filter(ebook_exts=[".jpg"])
        assert await filt.matches(photo_msg()) is True

    @pytest.mark.asyncio
    async def test_photo_rejected_when_jpg_is_not_allowed_and_photos_are_off(self):
        assert await self._filter().matches(photo_msg()) is False

    @pytest.mark.asyncio
    async def test_photo_accepted_when_include_photos_is_on(self):
        filt = self._filter(include_photos=True)
        assert await filt.matches(photo_msg()) is True

    @pytest.mark.asyncio
    async def test_documents_still_match_when_photos_are_on(self):
        filt = self._filter(include_photos=True)
        assert await filt.matches(document_msg()) is True
        assert await filt.matches(document_msg(file_name="notes.txt")) is False


class TestSizeAndPatternFilters:
    @pytest.mark.asyncio
    async def test_size_filter_uses_largest_photo_size(self):
        small = SimpleNamespace(width=90, height=90, file_size=100, file_unique_id="s")
        large = SimpleNamespace(width=2000, height=1500, file_size=50000, file_unique_id="l")
        msg = photo_msg(photo=MockPhoto(sizes=[small, large], file_size=100, width=90, height=90))
        assert await SizeFilter(min_bytes=10000, max_bytes=100000).matches(msg) is True
        assert await SizeFilter(min_bytes=60000).matches(msg) is False

    @pytest.mark.asyncio
    async def test_pattern_filter_uses_generated_filename(self):
        msg = photo_msg()
        assert await PatternFilter(include=["photo_*.jpg"]).matches(msg) is True
        assert await PatternFilter(include=["*.pdf"]).matches(msg) is False
        assert await PatternFilter(exclude=["photo_*"]).matches(msg) is False


class TestBuildFilters:
    @pytest.mark.asyncio
    async def test_default_filters_reject_photos(self):
        filt = build_filters(GlobalFilters())
        assert filt.include_photos is False
        assert await filt.matches(photo_msg()) is False
        assert await filt.matches(document_msg()) is True

    @pytest.mark.asyncio
    async def test_include_photos_accepts_photos_with_default_extensions(self):
        filt = build_filters(GlobalFilters(include_photos=True))
        assert filt.include_photos is True
        assert await filt.matches(photo_msg()) is True
        assert await filt.matches(document_msg()) is True


class TestSourceYieldsPhotos:
    @pytest.mark.asyncio
    async def test_channel_yields_photos_and_documents(self):
        messages = [
            photo_msg(msg_id=30),
            document_msg(msg_id=20),
            MockMessage(id=10, document=None, photo=None, text="no media"),
        ]

        async def history(_chat_id):
            for msg in messages:
                yield msg

        source = ChannelSource(MagicMock(), -100111)
        source.client.get_chat_history = history
        ids = [m.id async for m in source.iterate_new_media(0)]
        assert ids == [30, 20]

    @pytest.mark.asyncio
    async def test_forum_topic_yields_photos(self):
        photo = photo_msg(msg_id=8)
        photo.reply_to_top_message_id = 5
        photo.reply_to_message_id = 5

        async def history(_chat_id):
            yield photo

        source = ForumTopicSource(MagicMock(), -100111, 5)
        source.client.get_chat_history = history
        ids = [m.id async for m in source.iterate_new_media(0)]
        assert ids == [8]


class TestCollectMatchingIds:
    @pytest.mark.asyncio
    async def test_skips_photos_by_default_and_logs_debug(self, caplog):
        messages = [photo_msg(msg_id=30), document_msg(msg_id=20), photo_msg(msg_id=10)]

        async def history(_chat_id):
            for msg in messages:
                yield msg

        source = ChannelSource(MagicMock(), -100111)
        source.client.get_chat_history = history
        filt = build_filters(GlobalFilters())
        log = logging.getLogger("test-photos")
        with caplog.at_level(logging.DEBUG, logger="test-photos"):
            ids = await collect_matching_ids(source, 0, filt, log)
        assert ids == [20]
        assert "2 photo" in caplog.text
        assert "INCLUDE_PHOTOS" in caplog.text

    @pytest.mark.asyncio
    async def test_queues_photos_when_enabled(self, caplog):
        messages = [photo_msg(msg_id=30), document_msg(msg_id=20)]

        async def history(_chat_id):
            for msg in messages:
                yield msg

        source = ChannelSource(MagicMock(), -100111)
        source.client.get_chat_history = history
        filt = build_filters(GlobalFilters(include_photos=True))
        log = logging.getLogger("test-photos-on")
        with caplog.at_level(logging.DEBUG, logger="test-photos-on"):
            ids = await collect_matching_ids(source, 0, filt, log)
        assert ids == [30, 20]
        assert "INCLUDE_PHOTOS" not in caplog.text


class TestDownloadBatchPhotos:
    @pytest.mark.asyncio
    async def test_uses_generated_name_and_records_unique_id(self, tmp_path, monkeypatch):
        from src import main as main_module
        from src.main import download_batch

        async def fake_dest(download_dir, source, fname, source_config, flat):
            return download_dir / fname

        monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
        retry = AsyncMock(return_value=True)
        monkeypatch.setattr(main_module, "download_media_with_retry", retry)

        cfg = MagicMock()
        cfg.min_free_space = ""
        cfg.flat_structure = True
        cfg.post_download_hook = None
        cfg.max_retries = 2
        cfg.base_delay = 0
        cfg.max_delay = 0

        history = MagicMock()
        history.contains.return_value = False
        cursor = MagicMock()
        msg = photo_msg(file_unique_id="photo_unique_abc")

        stats, failed, deferred = await download_batch(
            [msg],
            asyncio.Semaphore(1),
            MagicMock(),
            tmp_path,
            cursor,
            "channel:-100111",
            cfg,
            logging.getLogger("test-photo-download"),
            MagicMock(),
            MagicMock(),
            history,
        )

        retry.assert_awaited_once()
        dest = retry.await_args.args[2]
        assert dest.name == PHOTO_NAME
        assert stats["downloaded"] == 1
        assert failed == set()
        assert deferred == set()
        history.record.assert_called_once()
        recorded = history.record.call_args.args
        assert recorded[0] == "photo_unique_abc"
        assert recorded[1] == PHOTO_NAME

    @pytest.mark.asyncio
    async def test_history_dedup_uses_photo_unique_id(self, tmp_path, monkeypatch):
        from src import main as main_module
        from src.main import download_batch

        monkeypatch.setattr(main_module, "download_media_with_retry", AsyncMock(return_value=True))

        cfg = MagicMock()
        cfg.min_free_space = ""
        cfg.flat_structure = True
        cfg.post_download_hook = None

        history = MagicMock()
        history.contains.return_value = True
        cursor = MagicMock()
        msg = photo_msg(file_unique_id="already")

        stats, failed, deferred = await download_batch(
            [msg],
            asyncio.Semaphore(1),
            MagicMock(),
            tmp_path,
            cursor,
            "channel:-100111",
            cfg,
            logging.getLogger("test-photo-dedup"),
            MagicMock(),
            MagicMock(),
            history,
        )

        history.contains.assert_called_once_with("already")
        history.record.assert_not_called()
        assert stats["skipped_tracked"] == 1
        assert failed == set()


class TestBuildFiltersWithSizeAndPattern:
    @pytest.mark.asyncio
    async def test_size_limits_apply_to_photos_through_build_filters(self):
        accepted = build_filters(
            GlobalFilters(include_photos=True, min_size="10KB", max_size="200KB")
        )
        too_small = build_filters(GlobalFilters(include_photos=True, min_size="100KB"))
        msg = photo_msg()  # default 80KB
        assert await accepted.matches(msg) is True
        assert await too_small.matches(msg) is False

    @pytest.mark.asyncio
    async def test_patterns_apply_to_generated_photo_names_through_build_filters(self):
        accepted = build_filters(
            GlobalFilters(include_photos=True, include_patterns=["photo_*.jpg"])
        )
        rejected = build_filters(
            GlobalFilters(include_photos=True, include_patterns=["*.pdf"])
        )
        msg = photo_msg()
        assert await accepted.matches(msg) is True
        assert await rejected.matches(msg) is False
        assert await accepted.matches(document_msg()) is False


class TestPendingPhotosHonourIncludeFlag:
    @pytest.mark.asyncio
    async def test_download_batch_skips_photos_when_include_photos_is_off(
        self, tmp_path, monkeypatch
    ):
        from src import main as main_module
        from src.main import download_batch

        retry = AsyncMock(return_value=True)
        monkeypatch.setattr(main_module, "download_media_with_retry", retry)

        cfg = MagicMock()
        cfg.min_free_space = ""
        cfg.flat_structure = True
        cfg.post_download_hook = None

        history = MagicMock()
        history.contains.return_value = False
        cursor = MagicMock()
        msg = photo_msg(msg_id=30, file_unique_id="queued-photo")

        stats, failed, deferred = await download_batch(
            [msg],
            asyncio.Semaphore(1),
            MagicMock(),
            tmp_path,
            cursor,
            "channel:-100111",
            cfg,
            logging.getLogger("test-photo-pending-off"),
            MagicMock(),
            MagicMock(),
            history,
            include_photos=False,
        )

        retry.assert_not_awaited()
        history.record.assert_not_called()
        assert stats["downloaded"] == 0
        assert failed == set()
        assert deferred == set()
        cursor.set.assert_called()

    @pytest.mark.asyncio
    async def test_run_check_removes_pending_photos_when_flag_is_off(
        self, tmp_path, monkeypatch
    ):
        from src.config.schema import SourceConfig
        from src.main import run_check
        from src.sources.channel import ChannelSource

        msg = photo_msg(msg_id=30, file_unique_id="queued-photo")
        retry = AsyncMock(return_value=True)
        monkeypatch.setattr("src.main.download_media_with_retry", retry)

        cfg = MagicMock()
        cfg.max_concurrent_downloads = 1
        cfg.max_downloads_per_run = 0
        cfg.min_free_space = ""
        cfg.flat_structure = True
        cfg.download_dir = tmp_path
        cfg.post_download_hook = None
        cfg.max_download_attempts = 5

        client = MagicMock()
        client.get_messages = AsyncMock(return_value=[msg])
        source = ChannelSource(client, -100111)
        filt = build_filters(GlobalFilters(include_photos=False))
        source_config = SourceConfig(url="https://t.me/preview", name="Preview Channel")

        state_store = MagicMock()
        state_store.get.return_value = 40
        pending = MagicMock()
        pending.has_pending.return_value = True
        pending.get_max_message_id.return_value = 40
        pending.get_oldest.side_effect = [[30], []]
        pending.count.return_value = 0
        pending.count_exhausted.return_value = 0

        history = MagicMock()
        history.contains.return_value = False

        log = logging.getLogger("test-pending-photos-off")
        summary = await run_check(
            cfg,
            log,
            state_store,
            client,
            [(source, filt, source_config)],
            history,
            pending,
        )

        retry.assert_not_awaited()
        history.record.assert_not_called()
        pending.remove_batch.assert_called()
        removed = []
        for call in pending.remove_batch.call_args_list:
            removed.extend(call.args[1])
        assert 30 in removed
        pending.increment_attempts.assert_not_called()
        assert summary["files_downloaded"] == 0
