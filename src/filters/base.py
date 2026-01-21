"""
Base filter abstraction for media selection.

Filters determine which messages should be downloaded based on
configurable criteria. Multiple filters can be composed together
for complex selection logic.
"""

from abc import ABC, abstractmethod
from pyrogram.types import Message


class BaseFilter(ABC):
    """
    Abstract base class for message filters.

    Filters implement the Strategy pattern to allow pluggable
    media selection logic. Each filter examines a message and
    returns True if it should be downloaded.

    Future filter types might include:
    - MimeTypeFilter: Filter by MIME type
    - SizeFilter: Filter by file size range
    - DateFilter: Filter by message date
    - CompositeFilter: Combine multiple filters with AND/OR logic
    """

    @abstractmethod
    async def matches(self, message: Message) -> bool:
        """
        Determine if message passes this filter.

        Args:
            message: Pyrogram Message object to evaluate

        Returns:
            True if message should be downloaded, False otherwise
        """
        pass
