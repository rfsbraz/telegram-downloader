"""
Size-based file filtering.

Filters messages based on file size range, allowing users to avoid
tiny files (samples, covers) or huge files (audiobooks, videos).
"""

from pyrogram.types import Message
from src.filters.base import BaseFilter


class SizeFilter(BaseFilter):
    """
    Filter messages by file size range.

    Accepts min_bytes and max_bytes to define acceptable file size range.
    Both parameters are optional - omitting min_bytes allows any small files,
    omitting max_bytes allows any large files.

    All size comparisons are in bytes (Pyrogram's native unit).
    """

    def __init__(self, min_bytes: int | None = None, max_bytes: int | None = None):
        """
        Initialize size filter.

        Args:
            min_bytes: Minimum file size in bytes (inclusive), None for no minimum
            max_bytes: Maximum file size in bytes (inclusive), None for no maximum
        """
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes

    async def matches(self, message: Message) -> bool:
        """
        Check if message contains media within size range.

        Args:
            message: Pyrogram Message to evaluate

        Returns:
            True if message has media within configured size range
        """
        # Get media object (same types as ExtensionFilter)
        media_obj = (
            message.document or
            message.audio or
            message.video or
            message.animation or
            message.voice or
            message.video_note
        )

        if not media_obj:
            return False

        # Get file size (defaults to 0 if attribute missing)
        file_size = getattr(media_obj, "file_size", 0)

        # Check minimum size constraint
        if self.min_bytes is not None and file_size < self.min_bytes:
            return False

        # Check maximum size constraint
        if self.max_bytes is not None and file_size > self.max_bytes:
            return False

        return True
