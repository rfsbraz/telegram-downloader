"""Regression tests for t.me/c/ parsing (issue #127).

Kurigram's resolve_peer treats a numeric string as a phone number: it
strips [+()\\s-] and, if the rest is digits, calls contacts.ResolvePhone.
A t.me/c/ link must therefore yield an int so get_chat and resolve_peer
take the get_peer_by_id / GetChannels path instead.
"""
from src.config.url_parser import parse_telegram_url


def test_private_chat_link_returns_int_id():
    chat_id, topic_id = parse_telegram_url("https://t.me/c/123456789")

    assert topic_id is None
    assert chat_id == -100123456789
    assert type(chat_id) is int


def test_private_chat_link_with_topic_returns_int_id():
    chat_id, topic_id = parse_telegram_url("https://t.me/c/123456789/5")

    assert topic_id == 5
    assert chat_id == -100123456789
    assert type(chat_id) is int


def test_telegram_me_private_link_returns_int_id():
    chat_id, topic_id = parse_telegram_url("https://telegram.me/c/987654321")

    assert topic_id is None
    assert chat_id == -100987654321
    assert type(chat_id) is int


def test_public_username_stays_a_string():
    chat_id, topic_id = parse_telegram_url("https://t.me/my_channel")

    assert chat_id == "my_channel"
    assert type(chat_id) is str
    assert topic_id is None
