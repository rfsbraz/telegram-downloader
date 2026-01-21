"""
Forum topic source implementation.

Handles media iteration from specific forum topics in Telegram supergroups.
Extracted from downloader.py download_topic_docs_for_topic function.
"""

import logging
from typing import AsyncIterator
from pyrogram import Client, raw
from pyrogram.types import Message
from pyrogram.enums import MessagesFilter

from src.sources.base import BaseSource


async def export_link_contains_topic(
    client: Client,
    chat_id: int,
    msg_id: int,
    topic_id: int
) -> bool:
    """
    Verify message belongs to specific forum topic.

    Uses Telegram's ExportMessageLink API to get canonical link,
    then checks if link contains "/{topic_id}/" segment.

    This is necessary because Telegram's search_messages API doesn't
    reliably filter by topic ID, so we must verify each message.

    Args:
        client: Authenticated Pyrogram Client
        chat_id: Chat/supergroup ID
        msg_id: Message ID to check
        topic_id: Expected topic ID

    Returns:
        True if message belongs to topic, False otherwise

    Raises:
        Exception: If API call fails or peer is not a channel/supergroup
    """
    peer = await client.resolve_peer(chat_id)

    # Supergroups are represented as InputPeerChannel in raw API
    if not isinstance(peer, raw.types.InputPeerChannel):
        return False

    channel = raw.types.InputChannel(
        channel_id=peer.channel_id,
        access_hash=peer.access_hash
    )

    res = await client.invoke(
        raw.functions.channels.ExportMessageLink(
            channel=channel,
            id=msg_id,
            grouped=False,
            thread=True
        )
    )

    link = getattr(res, "link", "") or ""
    return f"/{topic_id}/" in link


class ForumTopicSource(BaseSource):
    """
    Media source for Telegram forum topics.

    Forum topics are discussion threads within Telegram supergroups
    that have forum mode enabled. Each topic has a unique ID and
    behaves like a sub-chat within the parent supergroup.

    This source:
    1. Searches for documents in the entire chat (fast server-side search)
    2. Falls back to full history scan if search fails
    3. Verifies each message belongs to the specific topic via ExportMessageLink
    4. Yields only messages with media that belong to this topic

    Attributes:
        topic_id: Forum topic ID to monitor
    """

    def __init__(self, client: Client, chat_id: int, topic_id: int):
        """
        Initialize forum topic source.

        Args:
            client: Authenticated Pyrogram Client
            chat_id: Numeric supergroup ID (negative number)
            topic_id: Forum topic ID to monitor
        """
        super().__init__(client, chat_id)
        self.topic_id = topic_id
        self.log = logging.getLogger(f"source.forum_topic.{topic_id}")

    async def iterate_new_media(self, last_seen_id: int) -> AsyncIterator[Message]:
        """
        Iterate media messages from this forum topic.

        Strategy:
        1. Try search_messages(filter=DOCUMENT) for fast server-side search
        2. Fall back to get_chat_history if search fails
        3. For each message with media, verify it belongs to this topic
        4. Yield messages with ID > last_seen_id

        Messages are yielded newest-first (descending ID).

        Args:
            last_seen_id: Cursor position (last processed message ID)

        Yields:
            Message objects with media, belonging to this topic

        Example:
            >>> source = ForumTopicSource(client, -100123456789, 5)
            >>> async for msg in source.iterate_new_media(0):
            ...     print(f"Found message {msg.id} in topic")
        """
        async for msg in self._iter_docs_newest_first():
            # Stop scanning once we hit messages we've already seen
            if msg.id <= last_seen_id:
                break

            # Verify message has media
            media_obj = (
                msg.document or
                msg.audio or
                msg.video or
                msg.animation or
                msg.voice or
                msg.video_note
            )
            if not media_obj:
                continue

            # Verify message belongs to this specific topic
            try:
                in_topic = await export_link_contains_topic(
                    self.client,
                    self.chat_id,
                    msg.id,
                    self.topic_id
                )
            except Exception as e:
                # If we can't verify topic membership, skip to be safe
                self.log.debug(
                    f"Failed to verify topic for msg {msg.id}: {e}"
                )
                continue

            if not in_topic:
                continue

            yield msg

    async def _iter_docs_newest_first(self) -> AsyncIterator[Message]:
        """
        Iterate documents from chat, newest first.

        Tries server-side document search first (fast), falls back
        to full history scan if search fails.

        Yields:
            Message objects with potential media attachments
        """
        # Try server-side document search (fast)
        try:
            async for m in self.client.search_messages(
                self.chat_id,
                query="",
                limit=0,
                filter=MessagesFilter.DOCUMENT
            ):
                yield m
            return
        except Exception as e:
            self.log.warning(
                f"search_messages(DOCUMENT) failed: {e}; "
                f"falling back to history scan"
            )

        # Fallback: full chat history scan
        # Only yield messages that look like they have file-ish media
        offset_id = 0
        batch_size = 200

        while True:
            buf = []
            async for m in self.client.get_chat_history(
                self.chat_id,
                offset_id=offset_id,
                limit=batch_size
            ):
                buf.append(m)

            if not buf:
                break

            for m in buf:
                offset_id = m.id
                # Yield messages with media attachments
                if (
                    m.document or
                    m.audio or
                    m.video or
                    m.animation or
                    m.voice or
                    m.video_note
                ):
                    yield m

            if len(buf) < batch_size:
                break

    def get_cursor_key(self) -> str:
        """
        Return cursor key for state tracking.

        Format: "{chat_id}:{topic_id}"
        Matches existing state.yaml format from downloader.py.

        Returns:
            Cursor key string

        Example:
            >>> source = ForumTopicSource(client, -100123456789, 5)
            >>> source.get_cursor_key()
            '-100123456789:5'
        """
        return f"{self.chat_id}:{self.topic_id}"

    async def get_display_name(self) -> str:
        """
        Return human-readable source name.

        Format: "{chat_title} - Topic {topic_id}"

        Returns:
            Display name for logging

        Example:
            >>> await source.get_display_name()
            'Book Club - Topic 5'
        """
        try:
            chat = await self.client.get_chat(self.chat_id)
            title = getattr(chat, "title", str(self.chat_id))
            return f"{title} - Topic {self.topic_id}"
        except Exception:
            return f"Chat {self.chat_id} - Topic {self.topic_id}"
