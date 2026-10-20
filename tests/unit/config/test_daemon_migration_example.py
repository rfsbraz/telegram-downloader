"""
The "after" compose file in the telegram-download-daemon migration guide
must load into the settings the guide says it maps to.
"""
import os
from pathlib import Path

import pytest
import yaml

from src.config.loader import load_config
from src.config.source_parser import build_filters
from src.config.url_parser import parse_telegram_url
from src.filters import ExtensionFilter

EXAMPLE = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "migrate-from-telegram-download-daemon.yml"
)

PLACEHOLDERS = {
    "TDL_API_ID": "12345678",
    "TDL_API_HASH": "0123456789abcdef0123456789abcdef",
    "TDL_PHONE_NUMBER": "+351900000000",
}


@pytest.fixture
def example_env(monkeypatch):
    service = yaml.safe_load(EXAMPLE.read_text())["services"]["telegram-downloader"]
    env = dict(item.split("=", 1) for item in service["environment"])
    env.update({k: v for k, v in PLACEHOLDERS.items() if k in env})
    for key in list(os.environ):
        if key.startswith("TDL_"):
            monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return service, env


def test_example_maps_daemon_settings(example_env):
    service, _ = example_env
    cfg = load_config()

    # TELEGRAM_DAEMON_API_ID / TELEGRAM_DAEMON_API_HASH
    assert cfg.api_id == 12345678
    assert cfg.api_hash == PLACEHOLDERS["TDL_API_HASH"]
    # TELEGRAM_DAEMON_DEST, with one folder like the daemon
    assert cfg.download_dir == Path("/downloads")
    assert cfg.flat_structure is True
    # TELEGRAM_DAEMON_SESSION_PATH
    assert cfg.session_dir == Path("/app/.sessions")
    assert "./sessions:/app/.sessions" in service["volumes"]
    # TELEGRAM_DAEMON_WORKERS
    assert cfg.max_concurrent_downloads == 2
    # Keeps running instead of a single pass
    assert cfg.daemon.enabled is True


def test_example_channel_uses_daemon_channel_id(example_env):
    cfg = load_config()

    # TELEGRAM_DAEMON_CHANNEL=1234567890 becomes the t.me/c/ link
    assert len(cfg.sources) == 1
    chat_id, topic_id = parse_telegram_url(cfg.sources[0].url)
    assert chat_id == "-1001234567890"
    assert topic_id is None


def test_example_downloads_every_file_type(example_env):
    cfg = load_config()

    # The daemon has no extension filter, so the example turns ours off
    assert cfg.global_filters.extensions == []
    composite = build_filters(cfg.global_filters)
    assert not any(isinstance(f, ExtensionFilter) for f in composite.filters)
