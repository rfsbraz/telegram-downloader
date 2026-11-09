"""An existing session file keeps working after the move from Pyrogram to kurigram (#58).

The fixture is a session file as Pyrogram 2.0.106 writes it, with synthetic values only
(tests/fixtures/pyrogram_2.0.106_session.sql). It is opened the way the app opens it, through
create_client, so no new login is needed after the upgrade.
"""

import sqlite3
from importlib import metadata
from pathlib import Path

import pytest

from src.client.factory import create_client
from src.config.schema import Config

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "pyrogram_2.0.106_session.sql"
SESSION_NAME = "telegram_downloader"


@pytest.fixture
def old_session_dir(tmp_path):
    """A session directory holding the Pyrogram 2.0.106 session file."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    con = sqlite3.connect(session_dir / f"{SESSION_NAME}.session")
    con.executescript(FIXTURE.read_text())
    con.close()
    return session_dir


def test_the_client_library_is_kurigram():
    # Upstream Pyrogram is unmaintained since 2023 (#58); kurigram keeps the pyrogram import path.
    assert metadata.version("kurigram")
    with pytest.raises(metadata.PackageNotFoundError):
        metadata.version("pyrogram")


async def test_a_pyrogram_session_file_opens_with_the_same_login(old_session_dir, minimal_config_dict):
    config = Config(**minimal_config_dict, session_dir=old_session_dir)
    client = create_client(config)
    assert Path(client.storage.database) == old_session_dir / f"{SESSION_NAME}.session"

    await client.storage.open()
    try:
        assert await client.storage.dc_id() == 2
        assert await client.storage.api_id() == 12345
        assert not await client.storage.test_mode()
        assert await client.storage.auth_key() == bytes(range(256))
        assert await client.storage.user_id() == 123456789
        assert not await client.storage.is_bot()
        # Peers cached by Pyrogram still resolve, so sources need no new lookup.
        peer = await client.storage.get_peer_by_id(-1001234567890)
        assert peer.access_hash == 987654321
    finally:
        await client.storage.close()


async def test_the_session_file_is_migrated_in_place(old_session_dir, minimal_config_dict):
    config = Config(**minimal_config_dict, session_dir=old_session_dir)
    client = create_client(config)
    await client.storage.open()
    await client.storage.close()

    con = sqlite3.connect(old_session_dir / f"{SESSION_NAME}.session")
    try:
        (version,) = con.execute("select number from version").fetchone()
        assert version > 3
        auth_key, user_id = con.execute("select auth_key, user_id from sessions").fetchone()
        assert auth_key == bytes(range(256)) and user_id == 123456789
    finally:
        con.close()
