"""
Unit tests for CompositeFilter.

Tests AND logic, short-circuit evaluation, empty filters.
"""
import pytest

from src.filters.composite import CompositeFilter
from src.filters.extension import ExtensionFilter
from src.filters.size import SizeFilter
from tests.conftest import MockMessage


class MockPassFilter:
    """Filter that always passes."""
    async def matches(self, message):
        return True


class MockFailFilter:
    """Filter that always fails."""
    async def matches(self, message):
        return False


class MockTrackingFilter:
    """Filter that tracks whether it was called."""
    def __init__(self, result: bool):
        self.result = result
        self.was_called = False

    async def matches(self, message):
        self.was_called = True
        return self.result


class TestCompositeFilterBasics:
    """Basic CompositeFilter functionality."""

    @pytest.mark.asyncio
    async def test_all_pass(self, mock_message):
        """All filters passing should return True."""
        filter = CompositeFilter([
            MockPassFilter(),
            MockPassFilter(),
            MockPassFilter(),
        ])

        msg = mock_message()
        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_one_fails(self, mock_message):
        """One failing filter should return False."""
        filter = CompositeFilter([
            MockPassFilter(),
            MockFailFilter(),
            MockPassFilter(),
        ])

        msg = mock_message()
        assert await filter.matches(msg) is False

    @pytest.mark.asyncio
    async def test_empty_filters_returns_true(self, mock_message):
        """Empty filter list should return True (vacuous truth)."""
        filter = CompositeFilter([])

        msg = mock_message()
        assert await filter.matches(msg) is True


class TestCompositeFilterShortCircuit:
    """Short-circuit evaluation."""

    @pytest.mark.asyncio
    async def test_short_circuits_on_failure(self, mock_message):
        """Should not call filters after first failure."""
        tracking_filter = MockTrackingFilter(result=True)

        filter = CompositeFilter([
            MockFailFilter(),  # First filter fails
            tracking_filter,   # This should NOT be called
        ])

        msg = mock_message()
        await filter.matches(msg)

        assert tracking_filter.was_called is False


class TestCompositeFilterRealFilters:
    """Integration with real filter types."""

    @pytest.mark.asyncio
    async def test_extension_and_size(self, mock_message):
        """Combine extension and size filters."""
        filter = CompositeFilter([
            ExtensionFilter(
                ebook_exts=[".pdf", ".epub"],
                allow_archives=False,
                archive_exts=[]
            ),
            SizeFilter(min_bytes=1000, max_bytes=10_000_000),
        ])

        # PDF within size range - should match
        msg = mock_message(file_name="book.pdf", file_size=5_000_000)
        assert await filter.matches(msg) is True

        # PDF too small - should not match
        msg = mock_message(file_name="book.pdf", file_size=500)
        assert await filter.matches(msg) is False

        # Wrong extension - should not match
        msg = mock_message(file_name="book.txt", file_size=5_000_000)
        assert await filter.matches(msg) is False

    @pytest.mark.asyncio
    async def test_nested_composite(self, mock_message):
        """CompositeFilter can contain other CompositeFilters."""
        inner = CompositeFilter([
            MockPassFilter(),
            MockPassFilter(),
        ])

        outer = CompositeFilter([
            inner,
            MockPassFilter(),
        ])

        msg = mock_message()
        assert await outer.matches(msg) is True

    @pytest.mark.asyncio
    async def test_nested_composite_with_failure(self, mock_message):
        """Nested failure should propagate."""
        inner = CompositeFilter([
            MockPassFilter(),
            MockFailFilter(),  # Inner fails
        ])

        outer = CompositeFilter([
            inner,
            MockPassFilter(),
        ])

        msg = mock_message()
        assert await outer.matches(msg) is False
