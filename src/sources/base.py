"""
Base source abstraction for Telegram media sources.

Defines the interface for iterating media messages from different
Telegram source types. Each source type (forum topic, channel, group,
private chat) implements this interface with source-specific logic.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator
from pyrogram import Client
from pyrogram.types import Message


class BaseSource(ABC):
    """
    Abstract base class for media sources.

    Sources implement the Strategy pattern to allow different Telegram
    source types (forum topics, channels, groups, private chats) to be
    processed uniformly by the daemon loop.

    Each source is responsible for:
    - Iterating new messages with media attachments
    - Tracking its position in the message stream (cursor)
    - Providing a human-readable display name for logging

    Attributes:
        client: Pyrogram Client for API access
        chat_id: Numeric chat/channel ID
    """

    def __init__(self, client: Client, chat_id: int):
        """
        Initialize source with client and chat ID.

        Args:
            client: Authenticated Pyrogram Client
            chat_id: Numeric chat/channel ID (negative for supergroups)
        """
        self.client = client
        self.chat_id = chat_id

    @abstractmethod
    async def iterate_new_media(self, last_seen_id: int) -> AsyncIterator[Message]:
        """
        Yield messages newer than last_seen_id with media attachments.

        Messages should be yielded in newest-first order (descending ID).
        The caller will collect candidates and sort them for oldest-first
        processing.

        Only messages that:
        1. Have media attachments (document, audio, video, etc.)
        2. Have message.id > last_seen_id
        3. Belong to this specific source (e.g., correct forum topic)

        Args:
            last_seen_id: Message ID of last processed message (cursor position)

        Yields:
            Message objects with media, newer than last_seen_id

        Example:
            >>> async for msg in source.iterate_new_media(12345):
            ...     # Process msg.document, msg.audio, msg.video, etc.
            ...     pass
        """
        pass

    @abstractmethod
    def get_cursor_key(self) -> str:
        """
        Return unique key for state tracking.

        The cursor key identifies this source in the state store.
        Must be unique across all sources in the configuration.

        Format examples:
        - Forum topic: "{chat_id}:{topic_id}"
        - Channel: "channel:{chat_id}"
        - Group: "group:{chat_id}"
        - Private chat: "chat:{user_id}"

        Returns:
            Unique string identifier for this source

        Example:
            >>> source.get_cursor_key()
            '-100123456789:5'
        """
        pass

    @abstractmethod
    async def get_display_name(self) -> str:
        """
        Return human-readable source name for logging.

        Used in log messages and notifications to identify which
        source is being processed.

        Returns:
            Display name string (e.g., "Book Club - Topic 5")

        Example:
            >>> await source.get_display_name()
            'Book Club - Topic 5'
        """
        pass
