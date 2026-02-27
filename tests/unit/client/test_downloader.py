"""Unit tests for download_media_with_retry zero-byte validation."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    return MagicMock()


@pytest.fixture
def client():
    return AsyncMock()


class TestZeroByteValidation:
    """Tests for zero-byte download detection and retry."""

    @pytest.mark.asyncio
    async def test_zero_byte_download_triggers_retry(
        self, client, message, dest_path, log
    ):
        """A zero-byte download should be retried, not accepted."""
        config = make_config(max_retries=3)
        call_count = 0

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
