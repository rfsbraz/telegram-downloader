"""
Unit tests for SizeFilter.

Tests size range filtering, optional bounds, edge cases.
"""
import pytest

from src.filters.size import SizeFilter
from tests.conftest import MockMessage


class TestSizeFilterBasics:
    """Basic SizeFilter functionality."""

    @pytest.mark.asyncio
    async def test_within_range(self, mock_message):
        """Files within size range should match."""
        filter = SizeFilter(min_bytes=1000, max_bytes=10000)

        msg = mock_message(file_size=5000)
        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_too_small(self, mock_message):
        """Files below minimum should not match."""
        filter = SizeFilter(min_bytes=1000, max_bytes=10000)

        msg = mock_message(file_size=500)
        assert await filter.matches(msg) is False

    @pytest.mark.asyncio
    async def test_too_large(self, mock_message):
        """Files above maximum should not match."""
        filter = SizeFilter(min_bytes=1000, max_bytes=10000)

        msg = mock_message(file_size=50000)
        assert await filter.matches(msg) is False

    @pytest.mark.asyncio
    async def test_at_minimum_boundary(self, mock_message):
        """Files at exact minimum should match (inclusive)."""
        filter = SizeFilter(min_bytes=1000, max_bytes=10000)

        msg = mock_message(file_size=1000)
        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_at_maximum_boundary(self, mock_message):
        """Files at exact maximum should match (inclusive)."""
        filter = SizeFilter(min_bytes=1000, max_bytes=10000)

        msg = mock_message(file_size=10000)
        assert await filter.matches(msg) is True


class TestSizeFilterOptionalBounds:
    """Optional min/max bounds."""

    @pytest.mark.asyncio
    async def test_no_minimum(self, mock_message):
        """Without min_bytes, any small file should match."""
        filter = SizeFilter(min_bytes=None, max_bytes=10000)

        msg = mock_message(file_size=1)
        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_no_maximum(self, mock_message):
        """Without max_bytes, any large file should match."""
        filter = SizeFilter(min_bytes=1000, max_bytes=None)

        # 1GB file
        msg = mock_message(file_size=1024 * 1024 * 1024)
        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_no_bounds(self, mock_message):
        """Without any bounds, all files should match."""
        filter = SizeFilter(min_bytes=None, max_bytes=None)

        msg = mock_message(file_size=1)
        assert await filter.matches(msg) is True

        msg = mock_message(file_size=1024 * 1024 * 1024)
        assert await filter.matches(msg) is True


class TestSizeFilterNoMedia:
    """Handling messages without media."""

    @pytest.mark.asyncio
    async def test_no_media_returns_false(self, message_without_media):
        """Messages without media should return False."""
        filter = SizeFilter(min_bytes=1000, max_bytes=10000)

        assert await filter.matches(message_without_media) is False
