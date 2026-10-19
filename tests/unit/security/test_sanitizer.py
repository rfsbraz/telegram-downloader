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


class TestSanitizeFilenameUnicode:
    """Non-Latin filenames must be preserved (issue #69)."""

    def test_preserves_cjk(self):
        """Chinese characters should not be replaced with underscores."""
        assert sanitize_filename("中文文件.zip") == "中文文件.zip"

    def test_preserves_japanese_and_korean(self):
        """Japanese and Korean characters should be preserved."""
        assert sanitize_filename("日本語のファイル.pdf") == "日本語のファイル.pdf"
        assert sanitize_filename("한국어.txt") == "한국어.txt"

    def test_preserves_accented_latin(self):
        """Accented Latin letters should be preserved (spaces still become _)."""
        assert sanitize_filename("café résumé.pdf") == "café_résumé.pdf"

    def test_preserves_cyrillic(self):
        """Cyrillic letters should be preserved."""
        assert sanitize_filename("Документ.txt") == "Документ.txt"

    def test_preserves_combining_marks(self):
        """Scripts that rely on combining marks (e.g. Devanagari) stay intact."""
        assert sanitize_filename("हिन्दी.txt") == "हिन्दी.txt"

    def test_normalizes_to_nfc(self):
        """Decomposed input should be normalized to the composed (NFC) form."""
        decomposed = "cafe\u0301.pdf"  # 'e' + COMBINING ACUTE ACCENT
        assert sanitize_filename(decomposed) == "caf\u00e9.pdf"

    def test_preserves_unicode_in_extension(self):
        """Non-Latin characters in the extension should be preserved."""
        assert sanitize_filename("文件.文档") == "文件.文档"

    def test_distinct_non_latin_names_do_not_collide(self):
        """Different non-Latin names must not sanitize to the same value.

        Same name + same size is treated as a duplicate, so collisions caused
        the second file to be skipped.
        """
        first = sanitize_filename("文件一.zip")
        second = sanitize_filename("文件二.zip")
        assert first != second

    def test_distinct_scripts_do_not_collide(self):
        """Names in different scripts with equal length must stay distinct."""
        names = ["中文文件.zip", "Файл.zip", "ملف1.zip", "αρχείο.zip"]
        results = {sanitize_filename(n) for n in names}
        assert len(results) == len(names)

    def test_truncation_keeps_valid_utf8(self):
        """Truncating multi-byte names must stay within the byte limit."""
        result = sanitize_filename("中" * 100 + ".zip")
        assert len(result.encode("utf-8")) <= 255
        assert result.endswith(".zip")
        assert result.startswith("中")


class TestSanitizeFilenameUnsafeCharacters:
    """Characters that are unsafe on common filesystems are still replaced."""

    @pytest.mark.parametrize("char", ["/", "\\", ":", "*", "?", '"', "<", ">", "|"])
    def test_replaces_filesystem_unsafe_chars(self, char):
        """Windows/POSIX reserved characters must not survive sanitization."""
        result = sanitize_filename(f"名前{char}文件.txt")
        assert char not in result
        assert result == "名前_文件.txt"

    @pytest.mark.parametrize("char", ["\x00", "\x01", "\x1f", "\x7f", "\x85"])
    def test_replaces_control_chars(self, char):
        """Control characters must not survive sanitization."""
        result = sanitize_filename(f"Документ{char}.txt")
        assert char not in result

    def test_replaces_invisible_format_chars(self):
        """Bidi overrides / zero-width chars must not survive (spoofing)."""
        result = sanitize_filename("photo\u202egnp.exe")
        assert "\u202e" not in result
        result = sanitize_filename("a\u200bb.txt")
        assert "\u200b" not in result

    def test_replaces_fullwidth_slash(self):
        """Look-alike separators (fullwidth solidus) must not survive."""
        result = sanitize_filename("a\uff0fb.txt")
        assert "\uff0f" not in result

    def test_trims_leading_and_trailing_spaces(self):
        """Leading and trailing whitespace should be trimmed."""
        assert sanitize_filename("  中文文件.zip  ") == "中文文件.zip"

    def test_trims_trailing_dots(self):
        """Trailing dots are invalid on Windows and should be trimmed."""
        assert sanitize_filename("文件...") == "文件"
        assert sanitize_filename("report.pdf.") == "report.pdf"

    def test_trims_trailing_dots_and_spaces_mix(self):
        """A mix of trailing dots and spaces should be trimmed."""
        assert sanitize_filename("Документ . .") == "Документ"


class TestSanitizeFilenameWindowsReservedNames:
    """Windows reserved device names must not be produced."""

    @pytest.mark.parametrize(
        "name",
        ["CON", "PRN", "AUX", "NUL"]
        + [f"COM{i}" for i in range(1, 10)]
        + [f"LPT{i}" for i in range(1, 10)],
    )
    def test_reserved_name_is_escaped(self, name):
        """Bare reserved names should be altered."""
        result = sanitize_filename(name)
        assert result.upper() != name
        assert result == f"_{name}"

    @pytest.mark.parametrize("name", ["con.txt", "Nul.tar.gz", "com1.log", "LPT9.pdf"])
    def test_reserved_name_with_extension_is_escaped(self, name):
        """Reserved names are reserved regardless of case or extension."""
        result = sanitize_filename(name)
        assert result == f"_{name}"

    @pytest.mark.parametrize("name", ["CONSOLE.txt", "COM10.txt", "auxiliary.pdf", "nullable"])
    def test_non_reserved_lookalikes_unchanged(self, name):
        """Names that merely start with a reserved word are left alone."""
        assert sanitize_filename(name) == name


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
