"""
Source abstraction layer for multi-source media downloads.

Provides unified interface for iterating media from different
Telegram source types (forum topics, channels, groups, private chats).
"""

from src.sources.base import BaseSource
from src.sources.forum_topic import ForumTopicSource
from src.sources.channel import ChannelSource
from src.sources.group import GroupSource
from src.sources.private_chat import PrivateChatSource
from src.sources.factory import create_source

__all__ = [
    "BaseSource",
    "ForumTopicSource",
    "ChannelSource",
    "GroupSource",
    "PrivateChatSource",
    "create_source",
]
