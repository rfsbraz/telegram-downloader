"""
Telegram URL parser for extracting chat identifiers.

Parses t.me URLs to extract username or numeric chat ID with topic ID.
Supports both public usernames and private chat links.
"""

import re
from urllib.parse import urlparse


def parse_telegram_url(url: str) -> tuple[str, int | None]:
    """
    Parse Telegram URL to extract chat identifier and topic ID.

    Handles two URL formats:
    1. Public username: https://t.me/channel_name
    2. Private link: https://t.me/c/123456789/5

    For private links, adds -100 prefix to chat ID as required by
    Telegram's API for channels and supergroups.

    Args:
        url: Telegram URL (t.me or telegram.me)

    Returns:
        Tuple of (chat_identifier, topic_id):
        - chat_identifier: Username (str) or numeric ID with -100 prefix (str)
        - topic_id: Forum topic ID (int) or None

    Raises:
        ValueError: If URL is invalid or malformed

    Examples:
        >>> parse_telegram_url("https://t.me/my_channel")
        ('my_channel', None)

        >>> parse_telegram_url("https://t.me/c/123456789/5")
        ('-100123456789', 5)

        >>> parse_telegram_url("https://t.me/c/987654321")
        ('-100987654321', None)

        >>> parse_telegram_url("invalid://bad.url")
        ValueError: Invalid Telegram URL: invalid://bad.url
    """
    # Parse URL components
    parsed = urlparse(url)

    # Validate domain
    if parsed.netloc not in ["t.me", "telegram.me"]:
        raise ValueError(
            f"Invalid Telegram URL: {url}. "
            f"Expected domain 't.me' or 'telegram.me', got '{parsed.netloc}'"
        )

    # Split path into components
    path_parts = parsed.path.strip('/').split('/')

    if not path_parts or not path_parts[0]:
        raise ValueError(
            f"Invalid Telegram URL: {url}. "
            f"URL path is empty"
        )

    # Handle private chat link: t.me/c/123456789/5
    if path_parts[0] == 'c':
        if len(path_parts) < 2:
            raise ValueError(
                f"Invalid private chat URL: {url}. "
                f"Expected format: t.me/c/CHAT_ID or t.me/c/CHAT_ID/TOPIC_ID"
            )

        # Extract numeric chat ID
        try:
            chat_id_num = int(path_parts[1])
        except ValueError:
            raise ValueError(
                f"Invalid chat ID in URL: {url}. "
                f"Expected numeric ID, got '{path_parts[1]}'"
            )

        # Add -100 prefix (required for channels/supergroups)
        chat_id = f"-100{chat_id_num}"

        # Extract topic ID if present
        topic_id = None
        if len(path_parts) > 2:
            try:
                topic_id = int(path_parts[2])
            except ValueError:
                raise ValueError(
                    f"Invalid topic ID in URL: {url}. "
                    f"Expected numeric ID, got '{path_parts[2]}'"
                )

        return (chat_id, topic_id)

    # Handle public username: t.me/channel_name
    username = path_parts[0]

    # Validate username format (Telegram rules: 5+ chars, alphanumeric + underscore)
    if not re.match(r'^[a-zA-Z0-9_]{5,}$', username):
        raise ValueError(
            f"Invalid username in URL: {url}. "
            f"Username '{username}' must be 5+ characters, alphanumeric and underscore only"
        )

    return (username, None)
