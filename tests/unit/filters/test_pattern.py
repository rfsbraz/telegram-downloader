"""Filename pattern filters, including wiring through build_filters."""

import pytest

from src.config.schema import GlobalFilters
from src.config.source_parser import build_filters
from tests.conftest import MockDocument, MockMessage


def _msg(name: str) -> MockMessage:
    return MockMessage(document=MockDocument(file_name=name))


class TestBuildFiltersPatterns:
    """PatternFilter must accept the include/exclude fields that build_filters passes."""

    @pytest.mark.asyncio
    async def test_include_and_exclude_patterns_are_applied(self):
        filt = build_filters(
            GlobalFilters(
                include_patterns=["*book*"],
                exclude_patterns=["*draft*"],
            )
        )

        assert await filt.matches(_msg("mybook.pdf"))
        assert not await filt.matches(_msg("draft-book.pdf"))
        assert not await filt.matches(_msg("notes.txt"))

    @pytest.mark.asyncio
    async def test_exclude_only_patterns_are_applied(self):
        filt = build_filters(GlobalFilters(exclude_patterns=["*tmp*"]))

        assert await filt.matches(_msg("book.pdf"))
        assert not await filt.matches(_msg("book.tmp.pdf"))
