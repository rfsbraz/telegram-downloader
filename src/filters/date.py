"""
Date-based message filtering.

Filters messages based on date range, allowing users to catch up from
a specific point in time or only download recent content.
"""

from datetime import datetime, timezone
from pyrogram.types import Message
from src.filters.base import BaseFilter


class DateFilter(BaseFilter):
    """
    Filter messages by date range.

    Accepts only_after and only_before to define acceptable date range.
    Both parameters are optional and timezone-aware (UTC).

    CRITICAL: All datetimes are converted to UTC to prevent naive datetime
    comparison bugs. Pyrogram message.date is already timezone-aware UTC.
    """

    def __init__(
        self,
        only_after: datetime | None = None,
        only_before: datetime | None = None
    ):
        """
        Initialize date filter.

        Args:
            only_after: Minimum message date (inclusive), None for no minimum
            only_before: Maximum message date (inclusive), None for no maximum

        Note:
            If datetimes are naive (no tzinfo), they are automatically
            converted to UTC to prevent comparison errors.
        """
        # Ensure timezone awareness - convert naive datetimes to UTC
        if only_after is not None and only_after.tzinfo is None:
            only_after = only_after.replace(tzinfo=timezone.utc)
        if only_before is not None and only_before.tzinfo is None:
            only_before = only_before.replace(tzinfo=timezone.utc)

        self.only_after = only_after
        self.only_before = only_before

    async def matches(self, message: Message) -> bool:
        """
        Check if message falls within configured date range.

        Args:
            message: Pyrogram Message to evaluate

        Returns:
            True if message date is within configured range
        """
        # Return False if message has no date
        if message.date is None:
            return False

        msg_date = message.date

        # Check minimum date constraint
        if self.only_after is not None and msg_date < self.only_after:
            return False

        # Check maximum date constraint
        if self.only_before is not None and msg_date > self.only_before:
            return False

        return True
