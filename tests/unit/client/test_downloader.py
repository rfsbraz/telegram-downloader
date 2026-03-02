"""Unit tests for download_media_with_retry zero-byte validation."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyrogram.errors import FileReferenceExpired

from src.client.downloader import download_media_with_retry


def make_config(max_retries=3, base_delay=0, max_delay=0):
    """Create a minimal config-like object for testing."""
    cfg = MagicMock()
    cfg.max_retries = max_retries
    cfg.base_delay = base_delay
    cfg.max_delay = max_delay
    return cfg


@pytest.fixture
def dest_path(tmp_path):
    return tmp_path / "test_file.pdf"


@pytest.fixture
def log():
    return logging.getLogger("test_downloader")


@pytest.fixture
def message():
    msg = MagicMock()
    msg.chat.id = -1001234567890
    msg.id = 42
    return msg


@pytest.fixture
def client():
    return AsyncMock()


class TestZeroByteValidation:
    """Tests for zero-byte download detection and retry."""

    @pytest.mark.asyncio
    async def test_zero_byte_download_triggers_retry(
        self, client, message, dest_path, log
    ):
        """A zero-byte download should refresh the message and retry."""
        config = make_config(max_retries=3)
        call_count = 0
        fresh_message = MagicMock()
        fresh_message.chat.id = message.chat.id
        fresh_message.id = message.id
        client.get_messages = AsyncMock(return_value=fresh_message)

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            if call_count < 3:
                # Simulate zero-byte file (pyrogram silent failure)
                p.write_bytes(b"")
            else:
                # Third attempt succeeds
                p.write_bytes(b"real content")

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=12
        )

        assert result is True
        assert call_count == 3
        assert dest_path.exists()
        assert dest_path.read_bytes() == b"real content"
        # Verify get_messages was called to refresh stale file references
        assert client.get_messages.call_count == 2
        client.get_messages.assert_called_with(
            chat_id=message.chat.id,
            message_ids=message.id,
            replies=0,
        )

    @pytest.mark.asyncio
    async def test_zero_byte_exhausts_retries_returns_false(
        self, client, message, dest_path, log, caplog
    ):
        """When all retries produce zero-byte files, return False with error log."""
        config = make_config(max_retries=2)

        async def fake_download(msg, file_name, progress=None):
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"")

        client.download_media = AsyncMock(side_effect=fake_download)

        with caplog.at_level(logging.ERROR):
            result = await download_media_with_retry(
                client, message, dest_path, config, log, expected_size=1024
            )

        assert result is False
        assert not dest_path.exists()
        assert "empty file after 2 retries" in caplog.text

    @pytest.mark.asyncio
    async def test_valid_download_succeeds(
        self, client, message, dest_path, log
    ):
        """A non-zero download should succeed normally on first attempt."""
        config = make_config(max_retries=3)

        async def fake_download(msg, file_name, progress=None):
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"valid file content here")

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=23
        )

        assert result is True
        assert dest_path.exists()
        assert dest_path.read_bytes() == b"valid file content here"
        assert client.download_media.call_count == 1

    @pytest.mark.asyncio
    async def test_refresh_succeeds_and_retry_downloads_with_fresh_message(
        self, client, message, dest_path, log
    ):
        """After re-fetch, the retry uses the fresh message and succeeds."""
        config = make_config(max_retries=2)
        fresh_message = MagicMock()
        fresh_message.chat.id = message.chat.id
        fresh_message.id = message.id
        client.get_messages = AsyncMock(return_value=fresh_message)
        call_count = 0

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            if msg is message:
                # Stale message produces zero-byte file
                p.write_bytes(b"")
            else:
                # Fresh message downloads correctly
                p.write_bytes(b"fresh content")

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=13
        )

        assert result is True
        assert call_count == 2
        assert dest_path.read_bytes() == b"fresh content"
        # Second call should use the fresh message
        second_call_msg = client.download_media.call_args_list[1][0][0]
        assert second_call_msg is fresh_message

    @pytest.mark.asyncio
    async def test_refresh_fails_gracefully_and_continues_retry(
        self, client, message, dest_path, log, caplog
    ):
        """If get_messages fails, retry continues with the original message."""
        config = make_config(max_retries=2)
        client.get_messages = AsyncMock(side_effect=Exception("network error"))
        call_count = 0

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            if call_count < 2:
                p.write_bytes(b"")
            else:
                p.write_bytes(b"recovered content")

        client.download_media = AsyncMock(side_effect=fake_download)

        with caplog.at_level(logging.WARNING):
            result = await download_media_with_retry(
                client, message, dest_path, config, log, expected_size=17
            )

        assert result is True
        assert call_count == 2
        assert dest_path.read_bytes() == b"recovered content"
        assert "Failed to refresh message reference" in caplog.text


class TestFileReferenceExpiredHandling:
    """Tests for explicit FileReferenceExpired exception handling."""

    @pytest.mark.asyncio
    async def test_file_reference_expired_refreshes_and_retries(
        self, client, message, dest_path, log, caplog
    ):
        """FileReferenceExpired should refresh the message and retry."""
        config = make_config(max_retries=2)
        fresh_message = MagicMock()
        fresh_message.chat.id = message.chat.id
        fresh_message.id = message.id
        client.get_messages = AsyncMock(return_value=fresh_message)
        call_count = 0

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            if msg is message:
                raise FileReferenceExpired()
            # Fresh message succeeds
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"fresh download")

        client.download_media = AsyncMock(side_effect=fake_download)

        with caplog.at_level(logging.WARNING):
            result = await download_media_with_retry(
                client, message, dest_path, config, log, expected_size=14
            )

        assert result is True
        assert call_count == 2
        assert dest_path.read_bytes() == b"fresh download"
        assert "Stale file reference" in caplog.text
        client.get_messages.assert_called_once_with(
            chat_id=message.chat.id,
            message_ids=message.id,
            replies=0,
        )

    @pytest.mark.asyncio
    async def test_file_reference_expired_exhausts_retries(
        self, client, message, dest_path, log, caplog
    ):
        """FileReferenceExpired on all attempts should return False."""
        config = make_config(max_retries=2)
        client.get_messages = AsyncMock(return_value=message)

        client.download_media = AsyncMock(
            side_effect=FileReferenceExpired()
        )

        with caplog.at_level(logging.ERROR):
            result = await download_media_with_retry(
                client, message, dest_path, config, log
            )

        assert result is False
        assert "stale file reference" in caplog.text

    @pytest.mark.asyncio
    async def test_file_reference_expired_refresh_fails_continues_retry(
        self, client, message, dest_path, log, caplog
    ):
        """If refresh fails during FileReferenceExpired, retry still continues."""
        config = make_config(max_retries=2)
        client.get_messages = AsyncMock(side_effect=Exception("network down"))
        call_count = 0

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FileReferenceExpired()
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"recovered")

        client.download_media = AsyncMock(side_effect=fake_download)

        with caplog.at_level(logging.WARNING):
            result = await download_media_with_retry(
                client, message, dest_path, config, log
            )

        assert result is True
        assert call_count == 2
        assert dest_path.read_bytes() == b"recovered"
        assert "Failed to refresh message reference" in caplog.text


class TestSizeValidation:
    """Tests for truncated download detection via size validation."""

    @pytest.mark.asyncio
    async def test_truncated_file_triggers_retry_and_succeeds(
        self, client, message, dest_path, log
    ):
        """A truncated file should retry and succeed on full download."""
        config = make_config(max_retries=3)
        call_count = 0
        fresh_message = MagicMock()
        fresh_message.chat.id = message.chat.id
        fresh_message.id = message.id
        client.get_messages = AsyncMock(return_value=fresh_message)

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            if call_count < 2:
                # Simulate truncated file (51 bytes instead of 100)
                p.write_bytes(b"x" * 51)
            else:
                # Full download
                p.write_bytes(b"x" * 100)

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=100
        )

        assert result is True
        assert call_count == 2
        assert dest_path.exists()
        assert dest_path.stat().st_size == 100

    @pytest.mark.asyncio
    async def test_truncated_file_exhausts_retries_returns_false(
        self, client, message, dest_path, log, caplog
    ):
        """Truncated file on all attempts should return False."""
        config = make_config(max_retries=2)

        async def fake_download(msg, file_name, progress=None):
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            # Always truncated (50 bytes instead of 100)
            p.write_bytes(b"x" * 50)

        client.download_media = AsyncMock(side_effect=fake_download)
        client.get_messages = AsyncMock(return_value=message)

        with caplog.at_level(logging.ERROR):
            result = await download_media_with_retry(
                client, message, dest_path, config, log, expected_size=100
            )

        assert result is False
        assert not dest_path.exists()
        assert "Download incomplete after 2 retries" in caplog.text
        assert "50/100 bytes" in caplog.text

    @pytest.mark.asyncio
    async def test_file_within_tolerance_passes(
        self, client, message, dest_path, log
    ):
        """A file within 1% tolerance should pass validation."""
        config = make_config(max_retries=3)

        async def fake_download(msg, file_name, progress=None):
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            # 99.5% of expected size — within 1% tolerance
            p.write_bytes(b"x" * 995)

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=1000
        )

        assert result is True
        assert dest_path.exists()
        assert dest_path.stat().st_size == 995
        assert client.download_media.call_count == 1

    @pytest.mark.asyncio
    async def test_no_expected_size_skips_validation(
        self, client, message, dest_path, log
    ):
        """When expected_size is 0, size validation is skipped entirely."""
        config = make_config(max_retries=3)

        async def fake_download(msg, file_name, progress=None):
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            # Small file with no expected size — should pass
            p.write_bytes(b"x" * 10)

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=0
        )

        assert result is True
        assert dest_path.exists()
        assert client.download_media.call_count == 1

    @pytest.mark.asyncio
    async def test_size_mismatch_refreshes_message_reference(
        self, client, message, dest_path, log
    ):
        """Size mismatch should attempt to refresh the message reference."""
        config = make_config(max_retries=2)
        fresh_message = MagicMock()
        fresh_message.chat.id = message.chat.id
        fresh_message.id = message.id
        client.get_messages = AsyncMock(return_value=fresh_message)
        call_count = 0

        async def fake_download(msg, file_name, progress=None):
            nonlocal call_count
            call_count += 1
            p = Path(file_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            if call_count < 2:
                p.write_bytes(b"x" * 50)  # Truncated
            else:
                p.write_bytes(b"x" * 100)  # Full

        client.download_media = AsyncMock(side_effect=fake_download)

        result = await download_media_with_retry(
            client, message, dest_path, config, log, expected_size=100
        )

        assert result is True
        assert call_count == 2
        # Verify get_messages was called to refresh
        client.get_messages.assert_called_once_with(
            chat_id=message.chat.id,
            message_ids=message.id,
            replies=0,
        )
        # Second download call should use the fresh message
        second_call_msg = client.download_media.call_args_list[1][0][0]
        assert second_call_msg is fresh_message
