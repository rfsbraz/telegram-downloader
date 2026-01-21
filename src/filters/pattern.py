"""
Filename pattern filtering.

Filters messages based on filename patterns, supporting both simple
wildcards (user-friendly) and regex patterns (power users).
"""

import re
import fnmatch
from pyrogram.types import Message
from src.filters.base import BaseFilter


class PatternFilter(BaseFilter):
    """
    Filter messages by filename patterns.

    Supports both wildcard patterns (e.g., "*book*", "*.pdf") and
    regex patterns (e.g., "^[A-Z].*\\.pdf$"). Pattern type is
    auto-detected based on regex indicators.

    Include patterns use OR logic (any match → accept).
    Exclude patterns use OR logic (any match → reject).
    Excludes are checked first for early rejection.
    """

    def __init__(
        self,
        include: list[str] | None = None,
        exclude: list[str] | None = None
    ):
        """
        Initialize pattern filter.

        Args:
            include: Patterns to include (OR logic), None for all
            exclude: Patterns to exclude (OR logic), None for none

        Pattern auto-detection:
            - Regex: starts with ^, ends with $, or contains regex chars
            - Wildcard: everything else (user-friendly default)
        """
        self.include_patterns = self._compile_patterns(include or [])
        self.exclude_patterns = self._compile_patterns(exclude or [])

    def _compile_patterns(self, patterns: list[str]) -> list[tuple[str, bool]]:
        """
        Compile patterns and detect type (wildcard vs regex).

        Args:
            patterns: List of pattern strings

        Returns:
            List of tuples: [(pattern, is_regex), ...]
        """
        compiled = []
        regex_indicators = {'^', '$', '(', ')', '[', ']', '{', '}', '|', '+'}

        for pattern in patterns:
            # Detect if pattern is regex based on special characters
            is_regex = (
                pattern.startswith('^') or
                pattern.endswith('$') or
                any(char in pattern for char in regex_indicators)
            )
            compiled.append((pattern, is_regex))

        return compiled

    def _matches_pattern(self, filename: str, pattern: str, is_regex: bool) -> bool:
        """
        Check if filename matches pattern.

        Args:
            filename: Filename to check
            pattern: Pattern string
            is_regex: True for regex, False for wildcard

        Returns:
            True if filename matches pattern
        """
        if is_regex:
            # Regex pattern matching
            return re.search(pattern, filename) is not None
        else:
            # Wildcard pattern matching (case-insensitive)
            return fnmatch.fnmatch(filename.lower(), pattern.lower())

    async def matches(self, message: Message) -> bool:
        """
        Check if message filename matches pattern criteria.

        Args:
            message: Pyrogram Message to evaluate

        Returns:
            True if filename passes include/exclude filters
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

        # Extract filename
        filename = getattr(media_obj, "file_name", None)
        if not filename:
            # No filename to filter - pass through
            return True

        # Check exclude patterns first (early rejection)
        for pattern, is_regex in self.exclude_patterns:
            if self._matches_pattern(filename, pattern, is_regex):
                return False

        # Check include patterns (OR logic)
        if not self.include_patterns:
            # No include patterns - accept all (that passed excludes)
            return True

        for pattern, is_regex in self.include_patterns:
            if self._matches_pattern(filename, pattern, is_regex):
                return True

        # Has include patterns but none matched
        return False
