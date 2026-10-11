"""Post-download hook execution.

Runs a user-configured shell command after each successful download,
enabling integration with external tools (unrar, ffmpeg, library scans)
without modifying the downloader itself.

Security model: the command template is split with shlex FIRST, then
placeholder values are substituted into the resulting tokens verbatim.
Filenames can never inject additional arguments or shell syntax, and no
shell is involved (subprocess exec, shell=False).
"""

import asyncio
import logging
import shlex
from pathlib import Path

# Supported placeholders in the hook command template
PLACEHOLDERS = ("file", "dir", "filename", "extension", "source", "size")


def build_hook_command(
    template: str,
    file_path: Path,
    source_name: str,
    size: int,
) -> list[str]:
    """Build the argv list for a hook command template.

    The template is tokenized first (shlex), then placeholders are
    replaced inside each token, so values containing spaces or quotes
    stay a single argument and cannot inject extra ones.

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
        for name in PLACEHOLDERS:
            token = token.replace("{" + name + "}", values[name])
        argv.append(token)
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
    download must not be marked as failed because of the hook.

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

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        log.warning(f"Post-download hook failed to start for {file_path.name}: {e}")
        return

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        log.warning(
            f"Post-download hook timed out after {timeout}s for {file_path.name}"
        )
        return
    except Exception as e:
        log.warning(f"Post-download hook failed for {file_path.name}: {e}")
        return

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
