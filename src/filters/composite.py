"""
Filter composition for complex selection logic.

Combines multiple filters with AND logic, allowing flexible
combinations like: "PDF files, 1-10MB, from last week".
"""

from pyrogram.types import Message
from src.filters.base import BaseFilter
from src.media import is_photo_only


class CompositeFilter(BaseFilter):
    """
    Combine multiple filters with AND logic.

    All filters must pass for message to be accepted.
    Short-circuits on first failure for efficiency.

    Example:
        CompositeFilter([
            ExtensionFilter([".pdf"]),
            SizeFilter(min_bytes=1024*1024, max_bytes=10*1024*1024),
            DateFilter(only_after=datetime(2025, 1, 1))
        ])
    """

    def __init__(self, filters: list[BaseFilter], include_photos: bool = False):
        """
        Initialize composite filter.

        Args:
            filters: List of filters to combine with AND logic
            include_photos: Accept Telegram compressed photos (default off)
        """
        self.filters = filters
        self.include_photos = include_photos

    async def matches(self, message: Message) -> bool:
        """
        Check if message passes all filters.

        Args:
            message: Pyrogram Message to evaluate

        Returns:
            True if message passes all filters (AND logic)
        """
        if is_photo_only(message) and not self.include_photos:
            return False

        # Short-circuit AND: return False on first failure
        for f in self.filters:
            if not await f.matches(message):
                return False

        return True
