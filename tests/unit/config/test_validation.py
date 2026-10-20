"""
Config validation: archive fallback, retry minimum, log level check,
and the unused notification detail level.
"""
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.loader import ConfigError, load_config
from src.config.schema import Config
from src.config.source_parser import parse_sources
from src.filters import ExtensionFilter


@pytest.fixture
def env(clean_env, monkeypatch):
    monkeypatch.setenv("TDL_API_ID", "12345")
    monkeypatch.setenv("TDL_API_HASH", "abc123")
    return monkeypatch


def make_chat(chat_id: int):
    from pyrogram.enums import ChatType

    chat = MagicMock()
    chat.id = chat_id
    chat.type = ChatType.CHANNEL
    return chat


async def source_allows_archives(config: Config) -> bool:
    client = MagicMock()
    client.get_chat = AsyncMock(return_value=make_chat(-100111))
    (_, composite, _), = await parse_sources(config, client)
    ext = next(f for f in composite.filters if isinstance(f, ExtensionFilter))
    return ext.allow_archives


class TestAllowArchivesFallback:
    async def test_source_filters_without_allow_archives_use_global(self, env):
        env.setenv("TDL_GLOBAL_FILTERS_ALLOW_ARCHIVES", "true")
        env.setenv("TDL_SOURCES_0_URL", "https://t.me/channel")
        env.setenv("TDL_SOURCES_0_FILTERS_EXTENSIONS", ".pdf")

        assert await source_allows_archives(load_config("/nonexistent.yaml")) is True

    async def test_source_value_still_overrides_global(self, env):
        env.setenv("TDL_GLOBAL_FILTERS_ALLOW_ARCHIVES", "true")
        env.setenv("TDL_SOURCES_0_URL", "https://t.me/channel")
        env.setenv("TDL_SOURCES_0_FILTERS_ALLOW_ARCHIVES", "false")

        assert await source_allows_archives(load_config("/nonexistent.yaml")) is False


class TestMaxRetries:
    def test_zero_is_rejected(self, env):
        env.setenv("TDL_MAX_RETRIES", "0")

        with pytest.raises(ConfigError):
            load_config("/nonexistent.yaml")

    def test_one_is_accepted(self, env):
        env.setenv("TDL_MAX_RETRIES", "1")

        assert load_config("/nonexistent.yaml").max_retries == 1


class TestDaemonLogLevel:
    def test_bad_value_is_a_config_error(self, env):
        env.setenv("TDL_DAEMON_LOG_LEVEL", "LOUD")

        with pytest.raises(ConfigError, match="log_level"):
            load_config("/nonexistent.yaml")

    def test_value_is_case_insensitive(self, env):
        env.setenv("TDL_DAEMON_LOG_LEVEL", "debug")

        assert load_config("/nonexistent.yaml").daemon.log_level == "DEBUG"


class TestDetailLevelWarning:
    def test_warns_when_set(self, env, caplog):
        from src.main import warn_ignored_settings

        env.setenv("TDL_NOTIFICATIONS_DETAIL_LEVEL", "minimal")
        cfg = load_config("/nonexistent.yaml")

        with caplog.at_level(logging.WARNING):
            warn_ignored_settings(cfg, logging.getLogger("test"))

        assert "TDL_NOTIFICATIONS_DETAIL_LEVEL" in caplog.text

    def test_silent_when_not_set(self, env, caplog):
        from src.main import warn_ignored_settings

        cfg = load_config("/nonexistent.yaml")

        with caplog.at_level(logging.WARNING):
            warn_ignored_settings(cfg, logging.getLogger("test"))

        assert caplog.text == ""
