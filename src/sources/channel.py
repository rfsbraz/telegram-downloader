"""
Channel source implementation.

Handles media iteration from Telegram channels (public and private).
Uses uniform get_chat_history API for consistent iteration across all sources.
"""

import logging
from typing import AsyncIterator

from pyrogram import Client
from pyrogram.types import Message

from src.sources.base import BaseSource


class ChannelSource(BaseSource):
    """
    Media source for Telegram channels.

    Channels are broadcast-only chats where admins post content and
    subscribers receive updates. Can be public (with username) or
    private (invite link only).

    This source:
    1. Iterates all messages using get_chat_history (uniform API)
    2. Yields messages newest-first (descending message ID)
    3. Filters for messages with media attachments
    4. Stops iteration when reaching last_seen_id cursor

    Attributes:
        log: Logger instance for this channel
    """

    def __init__(self, client: Client, chat_id: int):
        """
        Initialize channel source.

        Args:
            client: Authenticated Pyrogram Client
            chat_id: Numeric channel ID (negative for private channels)
        """
        super().__init__(client, chat_id)
        self.log = logging.getLogger(f"source.channel.{chat_id}")

    async def iterate_new_media(self, last_seen_id: int) -> AsyncIterator[Message]:
        """
        Iterate media messages from channel (newest first).

        Uses Telegram's get_chat_history which works uniformly across
        all chat types. Iterates newest-first, breaks at cursor position.

        Args:
            last_seen_id: Cursor position (last processed message ID)

        Yields:
            Message objects with media, newer than last_seen_id

        Example:
            >>> source = ChannelSource(client, -1001234567890)
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

        Format: "channel:{chat_id}"
        Distinguishes channel sources from groups and private chats.

        Returns:
            Unique cursor key string

        Example:
            >>> source = ChannelSource(client, -1001234567890)
            >>> source.get_cursor_key()
            'channel:-1001234567890'
        """
        return f"channel:{self.chat_id}"

    async def get_display_name(self) -> str:
        """
        Return human-readable channel name for logging.

        Fetches channel title from Telegram API with fallback
        to numeric ID if API call fails.

        Returns:
            Channel title or numeric ID string

        Example:
            >>> await source.get_display_name()
            'My Channel'
        """
        try:
            chat = await self.client.get_chat(self.chat_id)
            return getattr(chat, "title", str(self.chat_id))
        except Exception:
            return f"Channel {self.chat_id}"
