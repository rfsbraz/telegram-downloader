"""Pyrogram client factory with secure session management.

Creates properly configured Pyrogram clients with:
- Secure session directory (700 permissions, owner-only)
- Session file isolation from working directory
- Configuration validation
"""

import os
from pathlib import Path
from pyrogram import Client

from src.config.schema import Config


def create_client(config: Config) -> Client:
    """Create Pyrogram client with secure session handling.

    Session files are stored in config.session_dir with owner-only permissions (700).
    The session directory is created if it doesn't exist.

    Args:
        config: Validated configuration object

    Returns:
        Unauthenticated Pyrogram Client (caller must use `async with client:` to start)

    Raises:
        ValueError: If api_id or api_hash are invalid

    Example:
        >>> from src.config import load_config
        >>> from src.client import create_client
        >>> cfg = load_config("config.yaml")
        >>> client = create_client(cfg)
        >>> async with client:
        ...     # Client is now authenticated and ready
        ...     pass
    """
    # Defensive validation (Config should already validate, but double-check)
    if config.api_id <= 0:
        raise ValueError("api_id must be greater than 0")
    if not config.api_hash or not config.api_hash.strip():
        raise ValueError("api_hash must be a non-empty string")

    # Ensure session directory exists with secure permissions
    session_dir = Path(config.session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Set directory permissions to 700 (owner-only: rwx------)
    # This works on both Unix and Windows (Windows restricts to owner)
    try:
        os.chmod(session_dir, 0o700)
    except (OSError, NotImplementedError):
        # Windows may not support chmod, but directory ACLs still provide owner-only access
        pass

    # Build client arguments
    client_kwargs = {
        "name": "telegram_downloader",
        "api_id": config.api_id,
        "api_hash": config.api_hash,
        "workdir": str(session_dir),

        # Daemon-optimized settings for long-running operation
        # These settings improve stability and reduce resource usage for continuous operation
        "sleep_threshold": 60,  # Auto-retry FloodWait errors ≤ 60 seconds (Pyrogram handles sleep/retry)
        "no_updates": True,  # Disable incoming update handlers (we only iterate history, don't need real-time updates)
        "max_concurrent_transmissions": 1,  # Conservative networking for long-running daemon (prevents connection issues)
    }

    # Add phone number if provided (optional for session reuse)
    if config.phone_number:
        client_kwargs["phone_number"] = config.phone_number

    # Create and return unauthenticated client
    # Caller must use `async with client:` to authenticate and start
    return Client(**client_kwargs)
