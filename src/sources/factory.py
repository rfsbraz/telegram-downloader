"""
Source factory for creating appropriate source implementations.

Factory pattern that detects chat type and returns the correct
source implementation for uniform media iteration across all
Telegram source types.
"""

from pyrogram import Client
from pyrogram.enums import ChatType

from src.sources.base import BaseSource
from src.sources.forum_topic import ForumTopicSource


async def create_source(
    client: Client,
    chat_id: int | str,
    topic_id: int | None = None
) -> BaseSource:
    """
    Create appropriate source based on chat type detection.

    Factory function that:
    1. Resolves chat_id (username or numeric) to Chat object
    2. Detects chat type using ChatType enum
    3. Returns appropriate source implementation
    4. Stores resolved numeric chat.id for state consistency

    Args:
        client: Authenticated Pyrogram Client
        chat_id: Numeric chat ID or username (str)
        topic_id: Forum topic ID (optional, for SUPERGROUP forums)

    Returns:
        Concrete BaseSource implementation based on chat type:
        - CHANNEL → ChannelSource
        - SUPERGROUP + topic_id → ForumTopicSource
        - SUPERGROUP without topic_id → GroupSource
        - GROUP → GroupSource
        - PRIVATE/BOT → PrivateChatSource

    Raises:
        ValueError: If chat type is unsupported or invalid
        pyrogram.errors.PeerIdInvalid: If chat_id cannot be resolved
        pyrogram.errors.UserNotParticipant: If not a member of the chat

    Example:
        >>> # Create source from username
        >>> source = await create_source(client, "my_channel")
        >>> print(type(source).__name__)
        'ChannelSource'

        >>> # Create source from numeric ID with forum topic
        >>> source = await create_source(client, -100123456789, topic_id=5)
        >>> print(type(source).__name__)
        'ForumTopicSource'
    """
    # Import here to avoid circular dependencies
    from src.sources.channel import ChannelSource
    from src.sources.group import GroupSource
    from src.sources.private_chat import PrivateChatSource

    # Resolve to Chat object and get numeric ID
    # This handles both usernames and numeric IDs
    chat = await client.get_chat(chat_id)
    resolved_id = chat.id  # Always numeric, permanent identifier

    # Match chat type and create appropriate source
    match chat.type:
        case ChatType.CHANNEL:
            # Public or private channel
            return ChannelSource(client, resolved_id)

        case ChatType.SUPERGROUP:
            # Supergroup - could be forum or regular
            if topic_id is not None:
                # Forum topic in supergroup
                return ForumTopicSource(client, resolved_id, topic_id)
            else:
                # Regular supergroup (no topics)
                return GroupSource(client, resolved_id)

        case ChatType.GROUP:
            # Regular group (legacy, <200 members)
            return GroupSource(client, resolved_id)

        case ChatType.PRIVATE | ChatType.BOT:
            # Private chat with user or bot
            return PrivateChatSource(client, resolved_id)

        case _:
            # Unsupported chat type
            raise ValueError(
                f"Unsupported chat type: {chat.type}. "
                f"Expected CHANNEL, SUPERGROUP, GROUP, PRIVATE, or BOT."
            )
