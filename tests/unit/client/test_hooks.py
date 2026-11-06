"""
Unit tests for post-download hooks (issue #35).

Covers placeholder substitution, injection safety, execution,
timeout handling, and the never-fail contract.
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.daemon.service import DaemonService

from src.client.hooks import build_hook_command, run_post_download_hook

log = logging.getLogger("test-hooks")


class TestBuildHookCommand:
    """Tests for command template parsing and substitution."""

    def test_all_placeholders(self):
        file_path = Path("/downloads/Books/story.pdf")
        argv = build_hook_command(
            'process "{file}" "{dir}" {filename} {extension} "{source}" {size}',
            file_path=file_path,
            source_name="My Channel",
            size=1024,
        )
        assert argv == [
            "process",
            str(file_path),
            str(file_path.parent),
            "story.pdf",
            ".pdf",
            "My Channel",
            "1024",
        ]

    def test_filename_with_spaces_stays_one_argument(self):
        file_path = Path("/downloads/my great archive.rar")
        argv = build_hook_command(
            'unrar x "{file}" "{dir}"',
            file_path=file_path,
            source_name="src",
            size=1,
        )
        assert argv == ["unrar", "x", str(file_path), str(file_path.parent)]

    def test_malicious_filename_cannot_inject_arguments(self):
        """A filename containing shell syntax stays a single literal argument."""
        evil = Path('/downloads/x"; rm -rf / #.pdf')
        argv = build_hook_command('touch "{file}"', evil, "src", 1)
        assert argv == ["touch", str(evil)]

    def test_placeholder_like_text_in_value_is_not_reprocessed(self):
        """A filename containing {size} must not be rewritten to the size."""
        file_path = Path("/downloads/report-{size}.pdf")
        argv = build_hook_command(
            'touch "{file}" {size}',
            file_path=file_path,
            source_name="src",
            size=99,
        )
        assert argv == ["touch", str(file_path), "99"]

    def test_empty_template_yields_empty_argv(self):
        assert build_hook_command("", Path("/f.pdf"), "src", 1) == []


class TestRunPostDownloadHook:
    """Tests for hook execution semantics."""

    async def test_successful_hook_runs(self, tmp_path):
        marker = tmp_path / "marker.txt"
        # Use forward slashes so the template survives POSIX-mode shlex
        # on Windows test runs too
        py = Path(sys.executable).as_posix()
        template = (
            f'"{py}" -c '
            f'"import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])" '
            f'"{marker.as_posix()}" "{{filename}}"'
        )
        await run_post_download_hook(
            template, tmp_path / "book.pdf", "src", 42, timeout=30, log=log
        )
        assert marker.read_text() == "book.pdf"

    async def test_nonzero_exit_does_not_raise(self, tmp_path):
        template = f'"{Path(sys.executable).as_posix()}" -c "import sys; sys.exit(3)"'
        # Must not raise
        await run_post_download_hook(
            template, tmp_path / "book.pdf", "src", 1, timeout=30, log=log
        )

    async def test_missing_command_does_not_raise(self, tmp_path):
        await run_post_download_hook(
            "definitely-not-a-real-command-xyz {file}",
            tmp_path / "book.pdf", "src", 1, timeout=30, log=log,
        )

    async def test_timeout_kills_hook_and_does_not_raise(self, tmp_path):
        template = f'"{Path(sys.executable).as_posix()}" -c "import time; time.sleep(60)"'
        await run_post_download_hook(
            template, tmp_path / "book.pdf", "src", 1, timeout=1, log=log
        )

    async def test_invalid_syntax_does_not_raise(self, tmp_path):
        # Unbalanced quote is a shlex ValueError
        await run_post_download_hook(
            'echo "{file}', tmp_path / "book.pdf", "src", 1, timeout=30, log=log
        )


async def test_enclosing_check_timeout_kills_and_reaps_hook(tmp_path, monkeypatch):
    started = asyncio.Event()
    processes = []
    real_create = asyncio.create_subprocess_exec

    async def capture_process(*args, **kwargs):
        process = await real_create(*args, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_process)
    template = f'"{Path(sys.executable).as_posix()}" -c "import time; time.sleep(60)"'
    hook = asyncio.create_task(run_post_download_hook(
        template, tmp_path / "book.pdf", "src", 1, timeout=30, log=log
    ))
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        service = DaemonService(lambda: hook, 300, tmp_path / "health.txt", check_timeout=0.01)
        await asyncio.wait_for(service.run_check(), timeout=10)
        assert hook.cancelled()
        assert processes[0].returncode is not None
        assert service.health.health_file.read_text().splitlines()[0] == "error"
        service.check_function = AsyncMock()
        await service.run_check()
        assert service.health.health_file.read_text().splitlines()[0] == "healthy"
    finally:
        if not hook.done():
            hook.cancel()
            await asyncio.gather(hook, return_exceptions=True)


@pytest.mark.parametrize("cancel", [False, True])
async def test_deadline_terminates_descendants_with_inherited_output(tmp_path, cancel):
    child = tmp_path / "child.py"
    marker = tmp_path / "child.pid"
    child.write_text(
        "import os, pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "time.sleep(60)\n"
    )
    template = " ".join(f'"{p.as_posix()}"' for p in (
        Path(sys.executable), parent, child, marker
    ))
    task = asyncio.create_task(run_post_download_hook(
        template, tmp_path / "book.pdf", "src", 1,
        timeout=30 if cancel else 2, log=log,
    ))
    try:
        for _ in range(100):
            if marker.exists() and marker.read_text():
                break
            await asyncio.sleep(0.05)
        assert marker.exists(), "descendant never started"
        pid = int(marker.read_text())
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 10)
        else:
            await asyncio.wait_for(task, 10)
        if os.name == "nt":
            listing = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            assert str(pid) not in listing.stdout
        else:
            # A killed orphan may briefly remain as a zombie under container
            # PID 1, but must no longer execute or keep inherited pipes open.
            stat = Path(f"/proc/{pid}/stat")
            for _ in range(100):
                if not stat.exists() or stat.read_text().split()[2] == "Z":
                    break
                await asyncio.sleep(0.01)
            assert not stat.exists() or stat.read_text().split()[2] == "Z"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_exited_hook_does_not_wait_for_descendant_output_handles(tmp_path):
    marker = tmp_path / "child.pid"
    child = tmp_path / "child.py"
    child.write_text(
        "import os, pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import pathlib, subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.01)\n"
    )
    template = " ".join(f'"{p.as_posix()}"' for p in (
        Path(sys.executable), parent, child, marker
    ))
    try:
        await asyncio.wait_for(run_post_download_hook(
            template, tmp_path / "book.pdf", "src", 1, timeout=1, log=log,
        ), timeout=10)
        assert marker.exists()
    finally:
        if marker.exists() and marker.read_text():
            try:
                os.kill(int(marker.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
