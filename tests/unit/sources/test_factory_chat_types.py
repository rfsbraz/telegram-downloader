"""Kurigram reports a forum-enabled supergroup as ChatType.FORUM, not SUPERGROUP (#58)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from pyrogram.enums import ChatType

from src.sources.factory import create_source
from src.sources.forum_topic import ForumTopicSource
from src.sources.group import GroupSource


def client_for(chat_type):
    chat = MagicMock()
    chat.id = -1001234567890
    chat.type = chat_type
    client = MagicMock()
    client.get_chat = AsyncMock(return_value=chat)
    return client


@pytest.mark.parametrize("chat_type", [ChatType.SUPERGROUP, ChatType.FORUM])
async def test_a_topic_in_a_forum_is_a_forum_topic_source(chat_type):
    source = await create_source(client_for(chat_type), "@forum", topic_id=7)
    assert isinstance(source, ForumTopicSource)


@pytest.mark.parametrize("chat_type", [ChatType.SUPERGROUP, ChatType.FORUM])
async def test_a_whole_forum_is_a_group_source(chat_type):
    source = await create_source(client_for(chat_type), "@forum")
    assert isinstance(source, GroupSource)
