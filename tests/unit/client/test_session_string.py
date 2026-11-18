"""TDL_SESSION_STRING and the auth command (#60).

Every string here is made up: a packed session with a fake auth key, never a real login.
"""

import base64
import io
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.client.factory import create_client
from src.config.loader import _load_from_env
from src.config.schema import Config

SESSION_NAME = "telegram_downloader"


def fake_session_string(user_id: int = 123456789) -> str:
    packed = struct.pack(">BI?256sQ?", 2, 12345, False, bytes(range(256)), user_id, False)
    return base64.urlsafe_b64encode(packed).decode().rstrip("=")


FAKE = fake_session_string()


@pytest.fixture
def auth_module():
    from src.client import auth

    return auth


@pytest.fixture
def config(minimal_config_dict, tmp_path):
    return Config(**minimal_config_dict, session_dir=tmp_path / "sessions")


def test_the_env_var_fills_the_session_string(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("TDL_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("TDL_SESSION_STRING", FAKE)
    assert _load_from_env()["session_string"] == FAKE


def test_the_session_string_is_off_by_default(config):
    assert config.session_string is None


def test_a_blank_session_string_counts_as_unset(minimal_config_dict):
    assert Config(**minimal_config_dict, session_string="  ").session_string is None


def test_the_session_string_stays_out_of_the_config_repr(minimal_config_dict):
    config = Config(**minimal_config_dict, session_string=FAKE)
    assert FAKE not in repr(config)
    assert FAKE not in str(config)


async def test_the_client_logs_in_from_the_session_string(minimal_config_dict, tmp_path):
    config = Config(**minimal_config_dict, session_dir=tmp_path / "s", session_string=FAKE)
    client = create_client(config)
    await client.storage.open()
    try:
        assert await client.storage.auth_key() == bytes(range(256))
        assert await client.storage.user_id() == 123456789
    finally:
        await client.storage.close()


async def test_the_session_string_wins_over_an_existing_session_file(minimal_config_dict, tmp_path):
    session_dir = tmp_path / "sessions"
    other = create_client(Config(**minimal_config_dict, session_dir=session_dir))
    await other.storage.open()
    await other.storage.user_id(111)
    await other.storage.save()
    await other.storage.close()
    assert (session_dir / f"{SESSION_NAME}.session").is_file()

    config = Config(**minimal_config_dict, session_dir=session_dir, session_string=FAKE)
    client = create_client(config)
    await client.storage.open()
    try:
        assert await client.storage.user_id() == 123456789
    finally:
        await client.storage.close()


def test_the_session_string_skips_the_interactive_phone_login(minimal_config_dict, tmp_path):
    config = Config(
        **minimal_config_dict, session_dir=tmp_path / "s", session_string=FAKE, phone_number="+10000000000"
    )
    with patch("src.client.factory.Client") as client_cls:
        create_client(config)
    kwargs = client_cls.call_args.kwargs
    assert kwargs["session_string"] == FAKE
    assert "phone_number" not in kwargs


def test_without_a_session_string_the_file_flow_is_unchanged(config):
    with patch("src.client.factory.Client") as client_cls:
        create_client(config)
    assert "session_string" not in client_cls.call_args.kwargs


def test_dry_run_with_a_session_string_needs_no_session_file(minimal_config_dict, tmp_path):
    config = Config(
        **minimal_config_dict, session_dir=tmp_path / "empty", session_string=FAKE, dry_run=True
    )
    client = create_client(config)
    assert client.session_string == FAKE
    assert not (tmp_path / "empty").exists()


def fake_login_client(string: str = FAKE):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.export_session_string = AsyncMock(return_value=string)
    return client


async def test_auth_prints_only_the_session_string_on_stdout(config, auth_module):
    out, err = io.StringIO(), io.StringIO()
    with patch.object(auth_module, "create_client", return_value=fake_login_client()):
        await auth_module.run_auth(config, out=out, err=err)
    assert out.getvalue() == FAKE + "\n"
    assert FAKE not in err.getvalue()
    assert "password" in err.getvalue().lower()


async def test_auth_ignores_a_configured_session_string_and_logs_in_again(
    minimal_config_dict, tmp_path, auth_module
):
    config = Config(**minimal_config_dict, session_dir=tmp_path / "s", session_string=fake_session_string(1))
    with patch.object(auth_module, "create_client", return_value=fake_login_client()) as create:
        await auth_module.run_auth(config, out=io.StringIO(), err=io.StringIO())
    assert create.call_args.args[0].session_string is None


async def test_the_auth_argument_runs_the_login_helper_not_the_downloader():
    from src import main as main_module

    with patch.object(main_module, "auth_command", new=AsyncMock()) as auth, patch.object(
        main_module, "main", new=AsyncMock()
    ) as run:
        await main_module.cli(["auth"])
    auth.assert_awaited_once()
    run.assert_not_awaited()


async def test_no_argument_runs_the_downloader():
    from src import main as main_module

    with patch.object(main_module, "auth_command", new=AsyncMock()) as auth, patch.object(
        main_module, "main", new=AsyncMock()
    ) as run:
        await main_module.cli([])
    run.assert_awaited_once()
    auth.assert_not_awaited()


def test_the_entrypoint_maps_the_auth_argument_to_the_login_helper():
    script = (Path(__file__).resolve().parents[3] / "entrypoint.sh").read_text()
    assert 'python3 -m src.main "$@"' in script
