"""
Group source implementation.

Handles media iteration from Telegram groups and supergroups (non-forum).
Uses identical implementation to ChannelSource - only difference is cursor key prefix.
"""

import logging
from typing import AsyncIterator

from pyrogram import Client
from pyrogram.types import Message

from src.sources.base import BaseSource


class GroupSource(BaseSource):
    """
    Media source for Telegram groups and supergroups.

    Groups are multi-user chats where all members can post.
    Two types:
    - GROUP: Legacy groups (<200 members)
    - SUPERGROUP: Modern groups (up to 200k members)

    This source:
    1. Iterates all messages using get_chat_history (uniform API)
    2. Yields messages newest-first (descending message ID)
    3. Filters for messages with media attachments
    4. Stops iteration when reaching last_seen_id cursor

    Note: Forum supergroups use ForumTopicSource instead.

    Attributes:
        log: Logger instance for this group
    """

    def __init__(self, client: Client, chat_id: int):
        """
        Initialize group source.

        Args:
            client: Authenticated Pyrogram Client
            chat_id: Numeric group ID (negative for supergroups)
        """
        super().__init__(client, chat_id)
        self.log = logging.getLogger(f"source.group.{chat_id}")

    async def iterate_new_media(self, last_seen_id: int) -> AsyncIterator[Message]:
        """
        Iterate media messages from group (newest first).

        Uses Telegram's get_chat_history which works uniformly across
        all chat types. Iterates newest-first, breaks at cursor position.

        Args:
            last_seen_id: Cursor position (last processed message ID)

        Yields:
            Message objects with media, newer than last_seen_id

        Example:
            >>> source = GroupSource(client, -1001234567890)
            >>> async for msg in source.iterate_new_media(12345):
            ...     print(f"New media in message {msg.id}")
        """
        async for msg in self.client.get_chat_history(self.chat_id):
            # Stop when we hit messages we've already seen
            if msg.id <= last_seen_id:
                break

            # Check for media attachments
            media_obj = (
                msg.document or
                msg.audio or
                msg.video or
                msg.animation or
                msg.voice or
                msg.video_note
            )

            if media_obj:
                yield msg

    def get_cursor_key(self) -> str:
        """
        Return cursor key for state tracking.

        Format: "group:{chat_id}"
        Distinguishes group sources from channels and private chats.

        Returns:
            Unique cursor key string

        Example:
            >>> source = GroupSource(client, -1001234567890)
            >>> source.get_cursor_key()
            'group:-1001234567890'
        """
        return f"group:{self.chat_id}"

    async def get_display_name(self) -> str:
        """
        Return human-readable group name for logging.

        Fetches group title from Telegram API with fallback
        to numeric ID if API call fails.

        Returns:
            Group title or numeric ID string

        Example:
            >>> await source.get_display_name()
            'Book Club Discussion'
        """
        try:
            chat = await self.client.get_chat(self.chat_id)
            return getattr(chat, "title", str(self.chat_id))
        except Exception:
            return f"Group {self.chat_id}"
