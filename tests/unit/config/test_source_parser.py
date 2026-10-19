"""
Unit tests for source parsing and access validation.

Covers the skip-instead-of-crash behavior for unresolvable sources
(issue #40): one dead channel must not abort the remaining sources.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.loader import ConfigError
from src.config.schema import Config
from src.config.source_parser import parse_sources, validate_source_access


def make_config(sources: list[dict]) -> Config:
    """Build a minimal valid Config with the given sources."""
    return Config.model_validate({
        "api_id": 12345,
        "api_hash": "abc123",
        "sources": sources,
    })


def make_chat(chat_id: int):
    """Mock Chat object resolved by client.get_chat."""
    from pyrogram.enums import ChatType

    chat = MagicMock()
    chat.id = chat_id
    chat.type = ChatType.CHANNEL
    return chat


class TestParseSources:
    """Tests for parse_sources resolution behavior."""

    async def test_all_sources_resolve(self):
        config = make_config([
            {"url": "https://t.me/channel_one"},
            {"url": "https://t.me/channel_two"},
        ])
        client = MagicMock()
        client.get_chat = AsyncMock(side_effect=[make_chat(-100111), make_chat(-100222)])

        results = await parse_sources(config, client)

        assert len(results) == 2
        # Tuples carry the matching source config (no index misalignment)
        assert results[0][2] is config.sources[0]
        assert results[1][2] is config.sources[1]

    async def test_dead_source_is_skipped_not_fatal(self):
        """A username that no longer exists must not abort the other sources."""
        config = make_config([
            {"url": "https://t.me/alive_channel"},
            {"url": "https://t.me/dead_channel"},
            {"url": "https://t.me/another_alive"},
        ])
        client = MagicMock()
        client.get_chat = AsyncMock(side_effect=[
            make_chat(-100111),
            Exception("[400 USERNAME_NOT_OCCUPIED] - The username is not occupied by anyone"),
            make_chat(-100333),
        ])

        results = await parse_sources(config, client)

        assert len(results) == 2
        assert results[0][2] is config.sources[0]
        assert results[1][2] is config.sources[2]

    async def test_missing_url_and_chat_id_still_fails_fast(self):
        """A structurally invalid source is a config error, not a skip."""
        config = make_config([{"name": "no url or chat_id"}])
        client = MagicMock()
        client.get_chat = AsyncMock()

        with pytest.raises(ConfigError, match="url or chat_id"):
            await parse_sources(config, client)


class TestValidateSourceAccess:
    """Tests for validate_source_access filtering behavior."""

    def _entry(self, chat_id: int):
        source = MagicMock()
        source.chat_id = chat_id
        return (source, MagicMock(), MagicMock())

    async def test_all_accessible(self):
        entries = [self._entry(-100111), self._entry(-100222)]
        client = MagicMock()
        client.get_chat = AsyncMock(side_effect=[make_chat(-100111), make_chat(-100222)])

        accessible = await validate_source_access(entries, client)

        assert accessible == entries

    async def test_inaccessible_source_is_filtered_out(self):
        entries = [self._entry(-100111), self._entry(-100222), self._entry(-100333)]
        client = MagicMock()
        client.get_chat = AsyncMock(side_effect=[
            make_chat(-100111),
            Exception("CHAT_FORBIDDEN"),
            make_chat(-100333),
        ])

        accessible = await validate_source_access(entries, client)

        assert accessible == [entries[0], entries[2]]
