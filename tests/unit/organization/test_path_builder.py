"""
Unit tests for destination path construction.

Tests both default (subfolder per source) and flat structure modes.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.config.schema import SourceConfig
from src.organization.path_builder import build_destination_path


class MockSource:
    """Mock source for testing path builder."""

    def __init__(self, display_name: str = "Test Channel", cursor_key: str = "channel:-100123456"):
        self._display_name = display_name
        self._cursor_key = cursor_key

    async def get_display_name(self) -> str:
        return self._display_name

    def get_cursor_key(self) -> str:
        return self._cursor_key


class TestBuildDestinationPathDefault:
    """Tests for default subfolder structure (flat_structure=False)."""

    @pytest.mark.asyncio
    async def test_uses_config_name_for_folder(self, temp_dir):
        """Should use source_config.name for folder when provided."""
        source = MockSource(display_name="Telegram Name")
        config = SourceConfig(url="https://t.me/test", name="Custom Name")

        result = await build_destination_path(
            temp_dir, source, "book.epub", config, flat_structure=False
        )

        assert result.parent.name == "Custom_Name"
        assert result.name == "book.epub"

    @pytest.mark.asyncio
    async def test_uses_display_name_when_no_config_name(self, temp_dir):
        """Should use source display name when config.name is not set."""
        source = MockSource(display_name="Book Club Channel")
        config = SourceConfig(url="https://t.me/test")

        result = await build_destination_path(
            temp_dir, source, "document.pdf", config, flat_structure=False
        )

        assert result.parent.name == "Book_Club_Channel"
        assert result.name == "document.pdf"

    @pytest.mark.asyncio
    async def test_creates_subfolder(self, temp_dir):
        """Should create the source subfolder."""
        source = MockSource(display_name="Test Channel")
        config = SourceConfig(url="https://t.me/test", name="Downloads")

        result = await build_destination_path(
            temp_dir, source, "file.txt", config, flat_structure=False
        )

        assert result.parent.exists()
        assert result.parent.name == "Downloads"

    @pytest.mark.asyncio
    async def test_path_structure_with_subfolder(self, temp_dir):
        """Should create path as base_dir/folder/filename."""
        source = MockSource()
        config = SourceConfig(url="https://t.me/test", name="MyFolder")

        result = await build_destination_path(
            temp_dir, source, "test.pdf", config, flat_structure=False
        )

        # Path should be base_dir / folder / filename
        # Use resolve() to handle Windows short path format differences
        expected = (temp_dir / "MyFolder" / "test.pdf").resolve()
        assert result == expected


class TestBuildDestinationPathFlat:
    """Tests for flat structure mode (flat_structure=True)."""

    @pytest.mark.asyncio
    async def test_flat_structure_no_subfolder(self, temp_dir):
        """Should place files directly in base_dir when flat_structure=True."""
        source = MockSource(display_name="Test Channel")
        config = SourceConfig(url="https://t.me/test", name="Would Be Folder")

        result = await build_destination_path(
            temp_dir, source, "book.epub", config, flat_structure=True
        )

        # File should be directly in base_dir, not in a subfolder
        # Use resolve() to handle Windows short path format differences
        assert result.parent == temp_dir.resolve()
        assert result == (temp_dir / "book.epub").resolve()

    @pytest.mark.asyncio
    async def test_flat_structure_ignores_config_name(self, temp_dir):
        """Flat structure should ignore source name for path construction."""
        source = MockSource(display_name="Ignored Name")
        config = SourceConfig(url="https://t.me/test", name="Also Ignored")

        result = await build_destination_path(
            temp_dir, source, "document.pdf", config, flat_structure=True
        )

        # No subfolder with any of the names
        assert "Ignored" not in str(result)
        assert result == (temp_dir / "document.pdf").resolve()

    @pytest.mark.asyncio
    async def test_flat_structure_creates_base_dir(self, temp_dir):
        """Should create base directory when flat_structure=True."""
        base = temp_dir / "nested" / "downloads"
        source = MockSource()
        config = SourceConfig(url="https://t.me/test")

        result = await build_destination_path(
            base, source, "file.txt", config, flat_structure=True
        )

        assert result.parent.exists()
        assert result.parent == base.resolve()

    @pytest.mark.asyncio
    async def test_flat_structure_sanitizes_filename(self, temp_dir):
        """Should sanitize filename even in flat mode."""
        source = MockSource()
        config = SourceConfig(url="https://t.me/test")

        result = await build_destination_path(
            temp_dir, source, "../../../etc/passwd", config, flat_structure=True
        )

        # Path traversal should be neutralized - slashes removed, file in base dir
        assert result.parent == temp_dir.resolve()
        assert "/" not in result.name
        assert "\\" not in result.name  # No path separators


class TestBuildDestinationPathDefaults:
    """Tests for default parameter behavior."""

    @pytest.mark.asyncio
    async def test_default_is_subfolder_mode(self, temp_dir):
        """Default should be subfolder mode (flat_structure=False)."""
        source = MockSource(display_name="Default Test")
        config = SourceConfig(url="https://t.me/test")

        # Call without flat_structure parameter
        result = await build_destination_path(
            temp_dir, source, "test.pdf", config
        )

        # Should have subfolder
        assert result.parent.name == "Default_Test"
        assert result != (temp_dir / "test.pdf").resolve()


class TestBuildDestinationPathSecurity:
    """Security tests for both modes."""

    @pytest.mark.asyncio
    async def test_path_traversal_blocked_subfolder_mode(self, temp_dir):
        """Path traversal should be blocked in subfolder mode."""
        source = MockSource()
        config = SourceConfig(url="https://t.me/test", name="../../escape")

        result = await build_destination_path(
            temp_dir, source, "file.txt", config, flat_structure=False
        )

        # Should not escape base_dir - use resolved path for comparison
        resolved_temp = temp_dir.resolve()
        assert str(resolved_temp) in str(result)

    @pytest.mark.asyncio
    async def test_path_traversal_blocked_flat_mode(self, temp_dir):
        """Path traversal should be blocked in flat mode."""
        source = MockSource()
        config = SourceConfig(url="https://t.me/test")

        result = await build_destination_path(
            temp_dir, source, "../../etc/passwd", config, flat_structure=True
        )

        # Should not escape base_dir - use resolved path for comparison
        resolved_temp = temp_dir.resolve()
        assert str(resolved_temp) in str(result)
        assert result.parent == resolved_temp
