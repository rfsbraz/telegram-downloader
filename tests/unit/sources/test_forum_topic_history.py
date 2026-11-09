"""A forum topic scan reaches the oldest message with kurigram's get_chat_history (#58).

Kurigram ignores the offset_id it is given, so paginating by offset_id repeats the
newest batch forever. Drive the real kurigram method over a fake chunk fetcher.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from pyrogram.methods.messages import get_chat_history as history_module

from src.sources.forum_topic import ForumTopicSource

TOPIC = 5
TOTAL = 450


def message(msg_id):
    return SimpleNamespace(
        id=msg_id, reply_to_top_message_id=TOPIC, reply_to_message_id=TOPIC,
        document=MagicMock(), audio=None, video=None, animation=None, voice=None, video_note=None,
    )


async def test_scan_walks_past_the_first_batch(monkeypatch):
    calls = []

    async def fake_chunk(*, client, chat_id, limit, offset_id, **kwargs):
        # Telegram history: messages older than offset_id (0 means newest), newest first
        await asyncio.sleep(0)
        calls.append(offset_id)
        top = TOTAL if not offset_id else offset_id - 1
        return [message(i) for i in range(top, max(top - limit, 0), -1)]

    monkeypatch.setattr(history_module, "get_chunk", fake_chunk)
    client = MagicMock()
    client.get_chat_history = lambda *a, **kw: history_module.GetChatHistory.get_chat_history(client, *a, **kw)
    source = ForumTopicSource(client, -1001234567890, TOPIC)

    async def scan():
        return [m.id async for m in source._iter_docs_newest_first()]

    ids = await asyncio.wait_for(scan(), timeout=5)
    assert ids == list(range(TOTAL, 0, -1))
