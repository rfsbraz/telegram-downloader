"""
Integration tests for filter chain pipeline.

Tests the complete filter chain with multiple filter types.
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.filters.extension import ExtensionFilter
from src.filters.size import SizeFilter
from src.filters.composite import CompositeFilter
from tests.conftest import MockDocument, MockMessage


class TestFilterPipelineBasics:
    """Basic filter pipeline tests."""

    @pytest.mark.asyncio
    async def test_extension_and_size_both_pass(self, mock_message):
        """Both extension and size conditions must be met."""
        pipeline = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf", ".epub", ".mobi"],
                allow_archives=False,
                archive_exts=[".zip"]
            ),
            SizeFilter(
                min_bytes=100 * 1024,      # 100KB min
                max_bytes=100 * 1024 * 1024  # 100MB max
            ),
        ])

        # PDF, 5MB - should pass
        msg = mock_message(file_name="book.pdf", file_size=5 * 1024 * 1024)
        assert await pipeline.matches(msg) is True

        # EPUB, 2MB - should pass
        msg = mock_message(file_name="novel.epub", file_size=2 * 1024 * 1024)
        assert await pipeline.matches(msg) is True

    @pytest.mark.asyncio
    async def test_extension_pass_size_fail(self, mock_message):
        """Correct extension but wrong size should fail."""
        pipeline = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf"],
                allow_archives=False,
                archive_exts=[]
            ),
            SizeFilter(
                min_bytes=1024 * 1024,  # 1MB min
                max_bytes=None
            ),
        ])

        # PDF but only 100KB - too small
        msg = mock_message(file_name="small.pdf", file_size=100 * 1024)
        assert await pipeline.matches(msg) is False

    @pytest.mark.asyncio
    async def test_size_pass_extension_fail(self, mock_message):
        """Correct size but wrong extension should fail."""
        pipeline = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf"],
                allow_archives=False,
                archive_exts=[]
            ),
            SizeFilter(
                min_bytes=1024,
                max_bytes=100 * 1024 * 1024
            ),
        ])

        # Text file, good size
        msg = mock_message(file_name="document.txt", file_size=5 * 1024 * 1024)
        assert await pipeline.matches(msg) is False


class TestFilterPipelineArchives:
    """Archive filtering in pipeline."""

    @pytest.mark.asyncio
    async def test_archive_with_size_filter(self, mock_message):
        """Archives should pass through size filter when enabled."""
        pipeline = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf"],
                allow_archives=True,
                archive_exts=[".zip", ".rar"]
            ),
            SizeFilter(
                min_bytes=1024,
                max_bytes=100 * 1024 * 1024
            ),
        ])

        # ZIP file, good size
        msg = mock_message(file_name="books.zip", file_size=50 * 1024 * 1024)
        assert await pipeline.matches(msg) is True

        # ZIP file, too large
        msg = mock_message(file_name="huge.zip", file_size=200 * 1024 * 1024)
        assert await pipeline.matches(msg) is False


class TestFilterPipelineEdgeCases:
    """Edge cases in filter pipeline."""

    @pytest.mark.asyncio
    async def test_empty_pipeline(self, mock_message):
        """Empty pipeline should pass everything."""
        pipeline = CompositeFilter([])

        msg = mock_message(file_name="anything.xyz", file_size=1)
        assert await pipeline.matches(msg) is True

    @pytest.mark.asyncio
    async def test_single_filter_pipeline(self, mock_message):
        """Single filter pipeline should work correctly."""
        pipeline = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf"],
                allow_archives=False,
                archive_exts=[]
            ),
        ])

        msg = mock_message(file_name="book.pdf")
        assert await pipeline.matches(msg) is True

        msg = mock_message(file_name="book.txt")
        assert await pipeline.matches(msg) is False

    @pytest.mark.asyncio
    async def test_message_without_media(self, message_without_media):
        """Messages without media should fail pipeline."""
        pipeline = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf"],
                allow_archives=False,
                archive_exts=[]
            ),
            SizeFilter(min_bytes=1024, max_bytes=None),
        ])

        assert await pipeline.matches(message_without_media) is False
