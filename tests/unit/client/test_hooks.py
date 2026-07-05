"""
Unit tests for post-download hooks (issue #35).

Covers placeholder substitution, injection safety, execution,
timeout handling, and the never-fail contract.
"""
import logging
import sys
from pathlib import Path

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
