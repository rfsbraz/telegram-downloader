"""
Unit tests for Telegram auth failure handling (issue #78).

A revoked session (401 AUTH_KEY_UNREGISTERED) must not crash-loop silently:
it notifies, writes status=error to the health file and, in daemon mode,
stays up so Docker's HEALTHCHECK marks the container unhealthy.
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyrogram.errors import AuthKeyUnregistered

import src.main as main_module
from src.daemon.service import DaemonService


class RevokedClient:
    """Client whose start (updates.GetState) fails with a revoked session."""

    async def __aenter__(self):
        raise AuthKeyUnregistered()

    async def __aexit__(self, *exc):
        return False


def make_config(tmp_path, daemon_enabled):
    cfg = MagicMock()
    cfg.log_file = ""
    cfg.verbosity = "normal"
    cfg.daemon.log_level = None
    cfg.daemon.enabled = daemon_enabled
    cfg.daemon.check_interval = 300
    cfg.daemon.health_file = tmp_path / "health_status.txt"
    cfg.session_dir = tmp_path
    cfg.track_downloads = False
    cfg.api_hash = "x" * 32
    cfg.test_mode = False
    cfg.max_download_speed = None
    cfg.notifications.enabled = True
    cfg.notifications.discord_webhook_url = "https://example.invalid/hook"
    cfg.notifications.discord_username = "Telegram Downloader"
    cfg.notifications.generic_webhook_url = None
    cfg.notifications.throttle_seconds = 60
    return cfg


@pytest.fixture
def revoked_session(tmp_path):
    """Patch main() collaborators; yields (make_cfg, notify mock)."""
    manager = MagicMock()
    manager.notify = AsyncMock()
    state = {}

    def configure(daemon_enabled):
        state["cfg"] = make_config(tmp_path, daemon_enabled)
        return state["cfg"]

    with patch.object(main_module, "load_config", lambda _p: state["cfg"]), \
         patch.object(main_module, "setup_logging",
                      lambda *_a: logging.getLogger("test-auth")), \
         patch.object(main_module, "create_client", lambda _c: RevokedClient()), \
         patch.object(main_module, "DiscordNotifier", MagicMock()), \
         patch.object(main_module, "NotificationManager",
                      MagicMock(return_value=manager)):
        yield configure, manager.notify


async def wait_for_file(path, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not path.exists() and loop.time() < deadline:
        await asyncio.sleep(0.01)


class TestAuthFailureDaemonMode:

    async def test_auth_key_unregistered_parks_unhealthy(self, revoked_session):
        configure, notify = revoked_session
        cfg = configure(daemon_enabled=True)

        task = asyncio.create_task(main_module.main())
        try:
            await wait_for_file(cfg.daemon.health_file)
            await asyncio.sleep(0.05)

            # No crash: the process stays up instead of exiting into a restart loop
            assert not task.done(), (
                f"main() exited instead of staying up: {task.exception()!r}"
                if task.done() and not task.cancelled() else "main() exited"
            )

            lines = cfg.daemon.health_file.read_text().splitlines()
            assert lines[0] == "error"
            assert "AUTH_KEY_UNREGISTERED" in lines[2]

            notify.assert_awaited_once()
            kwargs = notify.await_args.kwargs
            assert kwargs["level"] == "error"
            assert kwargs["force"] is True
            assert "AUTH_KEY_UNREGISTERED" in kwargs["message"]
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class TestAuthFailureSingleShot:

    async def test_auth_key_unregistered_notifies_and_exits(self, revoked_session):
        configure, notify = revoked_session
        cfg = configure(daemon_enabled=False)

        with pytest.raises(SystemExit) as exc_info:
            await main_module.main()

        assert exc_info.value.code == 1
        assert cfg.daemon.health_file.read_text().splitlines()[0] == "error"
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["force"] is True


class TestStartupValidationAuthError:

    async def test_get_me_auth_error_keeps_its_type(self):
        client = MagicMock()
        client.get_me = AsyncMock(side_effect=AuthKeyUnregistered())

        with pytest.raises(AuthKeyUnregistered):
            await main_module.startup_validation(MagicMock(), MagicMock(), client)


class ConnectedClient:
    """Client that starts fine; the session dies later, mid-run."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestAuthFailureMidRun:

    async def test_auth_error_inside_daemon_check_gets_reauth_handling(
        self, revoked_session
    ):
        configure, notify = revoked_session
        cfg = configure(daemon_enabled=True)

        shutdowns = []

        async def fake_shutdown(service):
            # The real shutdown cancels every task, including the test's own
            shutdowns.append(service)
            service.shutdown_event.set()

        with patch.object(main_module, "create_client", lambda _c: ConnectedClient()), \
             patch.object(DaemonService, "shutdown", fake_shutdown), \
             patch.object(main_module, "startup_validation", AsyncMock(return_value=[])), \
             patch.object(main_module, "run_check",
                          AsyncMock(side_effect=AuthKeyUnregistered())):
            task = asyncio.create_task(main_module.main())
            try:
                titles = []
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 2.0
                while loop.time() < deadline:
                    titles = [c.kwargs["title"] for c in notify.await_args_list]
                    if "Telegram Session Needs Re-auth" in titles or task.done():
                        break
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.05)

                assert not task.done(), "main() exited instead of staying up"

                titles = [c.kwargs["title"] for c in notify.await_args_list]
                lines = cfg.daemon.health_file.read_text().splitlines()
                assert lines[0] == "error"
                assert len(lines) > 2 and "AUTH_KEY_UNREGISTERED" in lines[2], (
                    f"no re-auth reason in health file; notifications sent: {titles}"
                )
                assert titles.count("Telegram Session Needs Re-auth") == 1
                assert "Check Failed" not in titles
                assert "Daemon Shutting Down" not in titles
                assert not shutdowns, "daemon ran its normal shutdown"
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
