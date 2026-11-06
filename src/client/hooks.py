"""Post-download hook execution.

Runs a user-configured command after each successful download,
enabling integration with external tools (unrar, ffmpeg, library scans)
without modifying the downloader itself.

Security model: the command template is split with shlex FIRST, then
placeholder values are substituted into the resulting tokens verbatim.
Filenames can never inject additional arguments or shell syntax, and no
shell is involved (subprocess exec, shell=False).
"""

import asyncio
import re
import logging
import os
import shlex
import signal
import tempfile
from pathlib import Path

# Supported placeholders in the hook command template
PLACEHOLDERS = ("file", "dir", "filename", "extension", "source", "size")


_PLACEHOLDER_RE = re.compile(
    r"\{(" + "|".join(PLACEHOLDERS) + r")\}"
)

HOOK_CLEANUP_TIMEOUT = 5


async def _terminate_hook(process, log):
    """Terminate the isolated hook tree without waiting forever on cleanup."""
    try:
        if os.name == "posix":
            # The group remains addressable even when its leader exited while
            # a descendant retained the output handles.
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), HOOK_CLEANUP_TIMEOUT)
            except asyncio.TimeoutError:
                killer.kill()
    except ProcessLookupError:
        pass
    except (OSError, asyncio.TimeoutError) as error:
        log.warning(f"Could not terminate hook process tree: {error}")
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), HOOK_CLEANUP_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("Hook process cleanup exceeded its deadline")


def build_hook_command(
    template: str,
    file_path: Path,
    source_name: str,
    size: int,
) -> list[str]:
    """Build the argv list for a hook command template.

    The template is tokenized first (shlex), then placeholders are
    replaced inside each token in a single pass, so values containing
    spaces, quotes, or placeholder-like text stay a single argument and
    cannot inject extra ones or trigger further substitution.

    Args:
        template: Command template, e.g. 'unrar x "{file}" "{dir}"'
        file_path: Absolute path of the downloaded file
        source_name: Display name of the source
        size: File size in bytes

    Returns:
        argv list ready for subprocess execution (empty if template is blank)
    """
    values = {
        "file": str(file_path),
        "dir": str(file_path.parent),
        "filename": file_path.name,
        "extension": file_path.suffix,
        "source": source_name,
        "size": str(size),
    }

    argv = []
    for token in shlex.split(template):
        argv.append(
            _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], token)
        )
    return argv


async def run_post_download_hook(
    template: str,
    file_path: Path,
    source_name: str,
    size: int,
    timeout: int,
    log: logging.Logger,
) -> None:
    """Run the post-download hook for a downloaded file.

    Hook failures (bad command, non-zero exit, timeout) are logged but
    never raised: the file was already saved successfully, so the
    download must not be marked as failed because of the hook. Cancellation
    from the enclosing daemon check is propagated after the child is reaped.

    Args:
        template: Command template with placeholders
        file_path: Absolute path of the downloaded file
        source_name: Display name of the source
        size: File size in bytes
        timeout: Max seconds to wait for the hook before killing it
        log: Logger instance
    """
    try:
        argv = build_hook_command(template, file_path, source_name, size)
    except ValueError as e:
        log.warning(f"Post-download hook has invalid syntax: {e}")
        return

    if not argv:
        return

    log.debug(f"Running post-download hook for {file_path.name}: {argv}")

    # File-backed output cannot hold process.wait() open when descendants
    # inherit stdout/stderr. Pipes would make even cancellation cleanup hang.
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=os.name == "posix",
            )
        except Exception as e:
            log.warning(f"Post-download hook failed to start for {file_path.name}: {e}")
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            await _terminate_hook(process, log)
            if isinstance(error, asyncio.CancelledError):
                raise
            log.warning(
                f"Post-download hook timed out after {timeout}s for {file_path.name}"
            )
            return
        except Exception as e:
            await _terminate_hook(process, log)
            log.warning(f"Post-download hook failed for {file_path.name}: {e}")
            return
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout, stderr = stdout_file.read(), stderr_file.read()

    if stdout:
        log.debug(f"Hook stdout: {stdout.decode(errors='replace').strip()}")
    if stderr:
        log.debug(f"Hook stderr: {stderr.decode(errors='replace').strip()}")

    if process.returncode != 0:
        log.warning(
            f"Post-download hook exited with code {process.returncode} "
            f"for {file_path.name}"
        )
    else:
        log.debug(f"Post-download hook completed for {file_path.name}")
