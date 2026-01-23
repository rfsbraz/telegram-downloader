"""
Unit tests for ExtensionFilter.

Tests extension matching, case insensitivity, archive handling, MIME fallback.
"""
import pytest

from src.filters.extension import ExtensionFilter, _endswith_any
from tests.conftest import MockDocument, MockMessage


class TestEndsWithAny:
    """Tests for _endswith_any helper function."""

    def test_matches_extension(self):
        """Should match when filename ends with extension."""
        assert _endswith_any("document.pdf", [".pdf", ".epub"]) is True

    def test_no_match(self):
        """Should not match when extension doesn't match."""
        assert _endswith_any("document.txt", [".pdf", ".epub"]) is False

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        assert _endswith_any("DOCUMENT.PDF", [".pdf"]) is True
        assert _endswith_any("document.pdf", [".PDF"]) is True

    def test_empty_extensions(self):
        """Empty extension list should never match."""
        assert _endswith_any("document.pdf", []) is False


class TestExtensionFilterBasics:
    """Basic ExtensionFilter functionality."""

    @pytest.mark.asyncio
    async def test_matches_ebook_extension(self, mock_message):
        """Should match configured ebook extensions."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf", ".epub"],
            allow_archives=False,
            archive_exts=[".zip"]
        )

        msg = mock_message(file_name="book.pdf")
        assert await filter.matches(msg) is True

        msg = mock_message(file_name="book.epub")
        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_rejects_non_matching_extension(self, mock_message):
        """Should reject files with non-matching extensions."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf", ".epub"],
            allow_archives=False,
            archive_exts=[".zip"]
        )

        msg = mock_message(file_name="document.txt")
        assert await filter.matches(msg) is False

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, mock_message):
        """Extension matching should be case-insensitive."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf"],
            allow_archives=False,
            archive_exts=[]
        )

        msg = mock_message(file_name="BOOK.PDF")
        assert await filter.matches(msg) is True

        msg = mock_message(file_name="Book.Pdf")
        assert await filter.matches(msg) is True


class TestExtensionFilterArchives:
    """Archive handling in ExtensionFilter."""

    @pytest.mark.asyncio
    async def test_archives_rejected_when_disabled(self, mock_message):
        """Archives should be rejected when allow_archives=False."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf"],
            allow_archives=False,
            archive_exts=[".zip", ".rar"]
        )

        msg = mock_message(file_name="books.zip")
        assert await filter.matches(msg) is False

    @pytest.mark.asyncio
    async def test_archives_accepted_when_enabled(self, mock_message):
        """Archives should be accepted when allow_archives=True."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf"],
            allow_archives=True,
            archive_exts=[".zip", ".rar"]
        )

        msg = mock_message(file_name="books.zip")
        assert await filter.matches(msg) is True

        msg = mock_message(file_name="collection.rar")
        assert await filter.matches(msg) is True


class TestExtensionFilterNoMedia:
    """Handling messages without media."""

    @pytest.mark.asyncio
    async def test_no_media_returns_false(self, message_without_media):
        """Messages without media should return False."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf"],
            allow_archives=False,
            archive_exts=[]
        )

        assert await filter.matches(message_without_media) is False


class TestExtensionFilterFallback:
    """MIME type fallback for missing filenames."""

    @pytest.mark.asyncio
    async def test_fallback_to_mime_type(self, mock_document):
        """Should use MIME type when filename is missing."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf"],
            allow_archives=False,
            archive_exts=[]
        )

        # Document with no filename but PDF MIME type
        doc = mock_document(file_name=None, mime_type="application/pdf")
        doc.file_name = None  # Explicitly set to None
        msg = MockMessage(id=1, document=doc)

        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_fallback_epub_mime(self, mock_document):
        """Should detect epub from MIME type."""
        filter = ExtensionFilter(
            ebook_exts=[".epub"],
            allow_archives=False,
            archive_exts=[]
        )

        doc = mock_document(file_name=None, mime_type="application/epub+zip")
        doc.file_name = None
        msg = MockMessage(id=1, document=doc)

        assert await filter.matches(msg) is True

    @pytest.mark.asyncio
    async def test_fallback_archive_mime(self, mock_document):
        """Should detect archive from MIME type when archives enabled."""
        filter = ExtensionFilter(
            ebook_exts=[".pdf"],
            allow_archives=True,
            archive_exts=[".zip"]
        )

        doc = mock_document(file_name=None, mime_type="application/zip")
        doc.file_name = None
        msg = MockMessage(id=1, document=doc)

        assert await filter.matches(msg) is True
