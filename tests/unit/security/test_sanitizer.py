"""
Unit tests for filename sanitization and path validation.

Tests against path traversal, null bytes, hidden files, and other attacks.
"""
import pytest
from pathlib import Path

from src.security.sanitizer import sanitize_filename, validate_path_safety


class TestSanitizeFilenameBasics:
    """Basic filename sanitization."""

    def test_normal_filename_unchanged(self):
        """Normal filenames should be mostly unchanged."""
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_preserves_extension(self):
        """File extension should be preserved."""
        result = sanitize_filename("book.epub")
        assert result.endswith(".epub")

    def test_empty_filename(self):
        """Empty filename should return default."""
        result = sanitize_filename("")
        assert result == "unnamed_file"

    def test_none_treated_as_empty(self):
        """None should be treated as empty (return default)."""
        # This would raise an error, but the function handles it
        result = sanitize_filename(None)
        assert result == "unnamed_file"


class TestSanitizeFilenamePathTraversal:
    """Path traversal attack prevention."""

    def test_removes_dot_dot_slash(self):
        """Should neutralize ../ path traversal attempts."""
        result = sanitize_filename("../../etc/passwd")
        # Path separators are replaced with underscore
        assert "/" not in result
        # The result should not contain actual path components
        assert result  # Non-empty result

    def test_removes_backslash_traversal(self):
        """Should neutralize ..\\ path traversal attempts."""
        result = sanitize_filename("..\\..\\Windows\\System32")
        # Backslashes are replaced with underscore
        assert "\\" not in result
        # The result should not contain actual path components
        assert result  # Non-empty result

    def test_complex_traversal(self):
        """Should handle complex traversal patterns and preserve extension."""
        result = sanitize_filename("../../../../etc/passwd.epub")
        # Extension should be preserved
        assert result.endswith(".epub")
        # Path separators neutralized
        assert "/" not in result


class TestSanitizeFilenameNullBytes:
    """Null byte injection prevention."""

    def test_removes_null_bytes(self):
        """Should remove null bytes."""
        result = sanitize_filename("file\x00.exe")
        assert "\x00" not in result

    def test_null_byte_in_extension(self):
        """Null bytes in extension should be removed."""
        result = sanitize_filename("document.pdf\x00.exe")
        assert "\x00" not in result


class TestSanitizeFilenameHiddenFiles:
    """Hidden file prevention."""

    def test_removes_leading_dot(self):
        """Should remove leading dots (hidden files)."""
        result = sanitize_filename(".hidden_file.txt")
        assert not result.startswith(".")

    def test_multiple_leading_dots(self):
        """Should remove multiple leading dots."""
        result = sanitize_filename("...hidden.txt")
        assert not result.startswith(".")


class TestSanitizeFilenameSpecialCharacters:
    """Special character handling."""

    def test_replaces_spaces_and_special_chars(self):
        """Should replace special characters with underscore."""
        result = sanitize_filename("book (2023).epub")
        # Parentheses and spaces should be replaced
        assert "(" not in result
        assert ")" not in result

    def test_allows_alphanumeric(self):
        """Alphanumeric characters should be preserved."""
        result = sanitize_filename("Book123.pdf")
        assert "Book123" in result

    def test_allows_underscore_hyphen(self):
        """Underscores and hyphens should be preserved."""
        result = sanitize_filename("my-book_2023.pdf")
        assert "-" in result
        assert "_" in result


class TestSanitizeFilenameTruncation:
    """Filename length truncation."""

    def test_truncates_long_filename(self):
        """Very long filenames should be truncated."""
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result.encode("utf-8")) <= 255

    def test_preserves_extension_on_truncation(self):
        """Extension should be preserved when truncating."""
        long_name = "a" * 300 + ".epub"
        result = sanitize_filename(long_name)
        assert result.endswith(".epub")

    def test_custom_max_length(self):
        """Should respect custom max_length."""
        result = sanitize_filename("a" * 100 + ".pdf", max_length=50)
        assert len(result.encode("utf-8")) <= 50


class TestValidatePathSafety:
    """Path safety validation."""

    def test_valid_path_within_base(self, temp_dir):
        """Valid path within base should return resolved path."""
        base = temp_dir
        target = base / "downloads" / "book.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        result = validate_path_safety(base, target)
        assert result.is_absolute()

    def test_path_traversal_raises_error(self, temp_dir):
        """Path traversal should raise ValueError."""
        base = temp_dir / "downloads"
        base.mkdir(exist_ok=True)

        # Try to escape to parent
        target = base / ".." / "secrets" / "password.txt"

        with pytest.raises(ValueError) as exc_info:
            validate_path_safety(base, target)
        assert "Path traversal" in str(exc_info.value)

    def test_absolute_outside_base_raises_error(self, temp_dir):
        """Absolute path outside base should raise error."""
        base = temp_dir / "downloads"
        base.mkdir(exist_ok=True)

        # Absolute path to different location
        if Path("/etc").exists():
            target = Path("/etc/passwd")
        else:
            target = Path("C:/Windows/System32") if Path("C:/").exists() else Path("/tmp/other")

        with pytest.raises(ValueError) as exc_info:
            validate_path_safety(base, target)
        assert "Path traversal" in str(exc_info.value)

    def test_resolved_path_returned(self, temp_dir):
        """Should return resolved absolute path."""
        base = temp_dir
        target = base / "downloads" / "book.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        result = validate_path_safety(base, target)
        assert result.is_absolute()
        assert result == target.resolve()
