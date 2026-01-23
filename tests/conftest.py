"""
Shared test fixtures for telegram-downloader test suite.

Provides:
- Mock Pyrogram objects (Message, Document, etc.)
- Filesystem fixtures (temp_dir, temp_file)
- Database fixtures (memory_db for SQLite testing)
- Configuration fixtures (minimal_config_dict, env_config)
"""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ============================================================================
# Mock Pyrogram Objects
# ============================================================================

class MockDocument:
    """Mock Pyrogram Document object for testing."""

    def __init__(
        self,
        file_name: str = "test.pdf",
        file_size: int = 1024000,
        mime_type: str = "application/pdf",
        file_id: str = "abc123",
    ):
        self.file_name = file_name
        self.file_size = file_size
        self.mime_type = mime_type
        self.file_id = file_id


class MockMessage:
    """Mock Pyrogram Message object for testing."""

    def __init__(
        self,
        id: int = 1,
        document: MockDocument | None = None,
        audio: Any = None,
        video: Any = None,
        animation: Any = None,
        voice: Any = None,
        video_note: Any = None,
        date: datetime | None = None,
        text: str | None = None,
    ):
        self.id = id
        self.document = document
        self.audio = audio
        self.video = video
        self.animation = animation
        self.voice = voice
        self.video_note = video_note
        self.date = date or datetime.now()
        self.text = text


@pytest.fixture
def mock_document():
    """Factory for creating mock Document objects."""
    def _create(
        file_name: str = "test.pdf",
        file_size: int = 1024000,
        mime_type: str = "application/pdf",
        file_id: str = "abc123",
    ) -> MockDocument:
        return MockDocument(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            file_id=file_id,
        )
    return _create


@pytest.fixture
def mock_message(mock_document):
    """Factory for creating mock Message objects with documents."""
    def _create(
        id: int = 1,
        file_name: str = "test.pdf",
        file_size: int = 1024000,
        mime_type: str = "application/pdf",
        date: datetime | None = None,
        has_document: bool = True,
        document: MockDocument | None = None,
    ) -> MockMessage:
        doc = document
        if has_document and doc is None:
            doc = mock_document(
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
            )
        return MockMessage(
            id=id,
            document=doc,
            date=date,
        )
    return _create


@pytest.fixture
def message_without_media():
    """Create a message with no media attached."""
    return MockMessage(id=1, document=None, text="Just a text message")


# ============================================================================
# Filesystem Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory that is cleaned up after test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_file(temp_dir):
    """Factory for creating temporary files."""
    def _create(name: str = "test.txt", content: str = "") -> Path:
        file_path = temp_dir / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path
    return _create


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture
def memory_db(temp_dir):
    """Create a temporary SQLite database file path.

    Note: Using temp file instead of :memory: because CursorStore
    needs a file path for WAL mode and parent directory creation.
    """
    return str(temp_dir / "test_cursor.db")


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def minimal_config_dict():
    """Minimal valid configuration dictionary."""
    return {
        "api_id": 12345,
        "api_hash": "abc123def456789012345678901234ab",
    }


@pytest.fixture
def full_config_dict(minimal_config_dict, temp_dir):
    """Complete configuration dictionary with all options."""
    return {
        **minimal_config_dict,
        "phone_number": "+1234567890",
        "download_dir": str(temp_dir / "downloads"),
        "session_dir": str(temp_dir / "sessions"),
        "verbosity": "normal",
        "max_concurrent_downloads": 3,
        "sources": [
            {
                "url": "https://t.me/test_channel",
                "name": "Test Channel",
            }
        ],
        "global_filters": {
            "extensions": [".pdf", ".epub"],
            "min_size": "1KB",
            "max_size": "100MB",
        },
        "daemon": {
            "enabled": False,
            "check_interval": 300,
        },
    }


@pytest.fixture
def env_config(monkeypatch):
    """Set up environment variables for config testing.

    Returns a function to set TDL_ prefixed env vars.
    """
    def _set_env(**kwargs):
        for key, value in kwargs.items():
            env_key = f"TDL_{key.upper()}"
            monkeypatch.setenv(env_key, str(value))
    return _set_env


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all TDL_ environment variables."""
    # Get list of TDL_ vars first to avoid dict size change during iteration
    tdl_vars = [k for k in os.environ.keys() if k.startswith("TDL_")]
    for var in tdl_vars:
        monkeypatch.delenv(var, raising=False)
    # Also remove legacy vars
    for var in ["API_ID", "API_HASH", "DOWNLOAD_DIR"]:
        monkeypatch.delenv(var, raising=False)


# ============================================================================
# YAML Configuration Fixtures
# ============================================================================

@pytest.fixture
def yaml_config_file(temp_file):
    """Factory for creating YAML config files."""
    def _create(content: str) -> Path:
        return temp_file("config.yaml", content)
    return _create


@pytest.fixture
def minimal_yaml_config(yaml_config_file):
    """Create minimal valid YAML config file."""
    content = """
api_id: 12345
api_hash: abc123def456789012345678901234ab
"""
    return yaml_config_file(content)


# ============================================================================
# Health Check Fixtures
# ============================================================================

@pytest.fixture
def health_file(temp_file):
    """Factory for creating health status files."""
    def _create(status: str = "healthy", timestamp: datetime | None = None) -> Path:
        ts = timestamp or datetime.now()
        content = f"{status}\n{ts.isoformat()}"
        return temp_file("health_status.txt", content)
    return _create
