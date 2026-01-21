"""
Private chat source implementation.

Handles media iteration from private chats with users and bots.
Includes support for "Saved Messages" (chat with self).
"""

import logging
from typing import AsyncIterator

from pyrogram import Client
from pyrogram.types import Message

from src.sources.base import BaseSource


class PrivateChatSource(BaseSource):
    """
    Media source for private chats with users and bots.

    Private chats are one-on-one conversations with:
    - Regular users
    - Bots
    - Self (Saved Messages)

    This source:
    1. Iterates all messages using get_chat_history (uniform API)
    2. Yields messages newest-first (descending message ID)
    3. Filters for messages with media attachments
    4. Stops iteration when reaching last_seen_id cursor
    5. Handles "Saved Messages" gracefully

    Attributes:
        log: Logger instance for this chat
    """

    def __init__(self, client: Client, chat_id: int):
        """
        Initialize private chat source.

        Args:
            client: Authenticated Pyrogram Client
            chat_id: Numeric user/bot ID (positive for users, varies for bots)
        """
        super().__init__(client, chat_id)
        self.log = logging.getLogger(f"source.private_chat.{chat_id}")

    async def iterate_new_media(self, last_seen_id: int) -> AsyncIterator[Message]:
        """
        Iterate media messages from private chat (newest first).

        Uses Telegram's get_chat_history which works uniformly across
        all chat types. Iterates newest-first, breaks at cursor position.

        Args:
            last_seen_id: Cursor position (last processed message ID)

        Yields:
            Message objects with media, newer than last_seen_id

        Example:
            >>> source = PrivateChatSource(client, 123456789)
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

        Format: "chat:{chat_id}"
        Distinguishes private chat sources from channels and groups.

        Returns:
            Unique cursor key string

        Example:
            >>> source = PrivateChatSource(client, 123456789)
            >>> source.get_cursor_key()
            'chat:123456789'
        """
        return f"chat:{self.chat_id}"

    async def get_display_name(self) -> str:
        """
        Return human-readable chat name for logging.

        Fetches user/bot name from Telegram API:
        - For users: first_name (and last_name if available)
        - For groups: title
        - For self: "Saved Messages"
        - Fallback: numeric ID

        Returns:
            Display name string

        Example:
            >>> await source.get_display_name()
            'John Doe'
        """
        try:
            chat = await self.client.get_chat(self.chat_id)

            # Check if it's saved messages (chat with self)
            me = await self.client.get_me()
            if chat.id == me.id:
                return "Saved Messages"

            # For users: use first_name (+ last_name)
            if hasattr(chat, "first_name"):
                name = chat.first_name
                if hasattr(chat, "last_name") and chat.last_name:
                    name += f" {chat.last_name}"
                return name

            # For groups/channels: use title
            if hasattr(chat, "title"):
                return chat.title

            # Fallback to ID
            return str(self.chat_id)

        except Exception:
            return f"Chat {self.chat_id}"
