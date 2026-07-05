"""Streaming download manager with retry logic and FloodWait handling.

Implements robust download functionality with:
- Streaming to avoid memory exhaustion on large files (2GB+)
- FloodWait handling (respects Telegram's required delay)
- Exponential backoff for transient errors
- Temporary .partial files with atomic rename on success
- Automatic cleanup of partial downloads on failure
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, FileReferenceExpired

from src.config.schema import Config
from src.client.ratelimit import RateLimiter


async def download_media_with_retry(
    client: Client,
    message: Message,
    dest_path: Path,
    config: Config,
    log: logging.Logger,
    expected_size: int = 0,
    limiter: "RateLimiter | None" = None,
) -> bool:
    """Download media with streaming, retry logic, and FloodWait handling.

    Downloads media to a temporary .partial file and atomically renames to final
    destination on success. Uses streaming to avoid loading entire file in memory.

    After download_media() returns, validates the file is non-empty. Pyrogram may
    silently handle FileReferenceExpired/FloodWait errors internally and write a
    0-byte file instead of raising an exception.

    FloodWait errors are handled specially:
    - Sleep for the exact duration Telegram specifies
    - Do NOT count against retry budget (Telegram mandates the wait)
    - Automatically retry after waiting

    Transient errors use exponential backoff:
    - Retry up to config.max_retries times
    - Delay doubles each retry: base_delay, base_delay*2, base_delay*4, etc.
    - Capped at config.max_delay

    Args:
        client: Authenticated Pyrogram client
        message: Message containing media to download
        dest_path: Final destination path for downloaded file
        config: Configuration with retry settings
        log: Logger instance for progress/error reporting
        expected_size: Expected file size in bytes (for logging context)
        limiter: Optional shared RateLimiter capping aggregate download speed

    Returns:
        True if download succeeded, False if all retries exhausted

    Example:
        >>> success = await download_media_with_retry(
        ...     client, message, Path("/downloads/file.pdf"), config, log
        ... )
        >>> if success:
        ...     print("Download complete")
        ... else:
        ...     print("Download failed after all retries")
    """
    # Create parent directories if needed
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Use temporary .partial file during download
    dest_temp = dest_path.with_suffix(dest_path.suffix + ".partial")

    # Track cumulative progress so the rate limiter sees byte deltas
    progress_state = {"last": 0}

    def _log_progress(current: int, total: int) -> None:
        """Log download progress at intervals."""
        if total > 0:
            percent = (current / total) * 100
            # Log every 10% to avoid spam
            if int(percent) % 10 == 0 and int(percent) > 0:
                log.debug(f"Download progress: {percent:.1f}% ({current}/{total} bytes)")

    if limiter:
        # Async callback: pyrogram awaits coroutine progress callbacks, so
        # the limiter can sleep without blocking the event loop
        async def progress_callback(current: int, total: int) -> None:
            delta = current - progress_state["last"]
            progress_state["last"] = current
            if delta > 0:
                await limiter.throttle(delta)
            _log_progress(current, total)
    else:
        def progress_callback(current: int, total: int) -> None:
            _log_progress(current, total)

    # Main download loop with retry logic
    for attempt in range(1, config.max_retries + 1):
        # Each attempt restarts the transfer from zero
        progress_state["last"] = 0
        try:
            # Stream download to temporary file
            await client.download_media(
                message,
                file_name=str(dest_temp),
                progress=progress_callback
            )

            # Validate file is non-empty (pyrogram may silently produce 0-byte
            # files when it handles FileReferenceExpired/FloodWait internally)
            if dest_temp.exists() and dest_temp.stat().st_size == 0:
                dest_temp.unlink()
                if attempt < config.max_retries:
                    delay = min(config.base_delay * (2 ** (attempt - 1)), config.max_delay)
                    log.warning(
                        f"Stale file reference for {dest_path.name}, "
                        f"refreshing and retrying in {delay}s..."
                    )
                    # Re-fetch message to get fresh file references before retry
                    try:
                        fresh = await client.get_messages(
                            chat_id=message.chat.id,
                            message_ids=message.id,
                            replies=0,
                        )
                        if fresh:
                            message = fresh
                    except Exception as ref_err:
                        log.warning(f"Failed to refresh message reference: {ref_err}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    log.error(
                        f"Download produced empty file after "
                        f"{config.max_retries} retries: {dest_path.name}"
                    )
                    return False

            # Validate file size against expected (catches truncated downloads
            # from 503 recovery where pyrogram reports success)
            if expected_size > 0 and dest_temp.exists():
                actual_size = dest_temp.stat().st_size
                if actual_size < int(expected_size * 0.99):  # 1% tolerance
                    dest_temp.unlink()
                    if attempt < config.max_retries:
                        delay = min(config.base_delay * (2 ** (attempt - 1)), config.max_delay)
                        log.warning(
                            f"Size mismatch for {dest_path.name}: "
                            f"expected ~{expected_size} bytes, got {actual_size}. "
                            f"Retrying in {delay}s..."
                        )
                        # Refresh message reference before retry
                        try:
                            fresh = await client.get_messages(
                                chat_id=message.chat.id,
                                message_ids=message.id,
                                replies=0,
                            )
                            if fresh:
                                message = fresh
                        except Exception as ref_err:
                            log.warning(f"Failed to refresh message reference: {ref_err}")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        log.error(
                            f"Download incomplete after {config.max_retries} retries: "
                            f"{dest_path.name} ({actual_size}/{expected_size} bytes)"
                        )
                        return False

            # Atomic rename on success (prevents partial files in download dir)
            dest_temp.rename(dest_path)
            log.info(f"Download complete: {dest_path.name}")
            return True

        except FloodWait as e:
            # FloodWait is special: Telegram mandates the wait, so we MUST respect it
            # Do NOT count this against retry budget - it's not a "failure"
            log.warning(f"FloodWait: Telegram requires {e.value}s wait. Sleeping...")
            await asyncio.sleep(e.value)
            # Loop continues to retry WITHOUT incrementing attempt counter
            # Note: We don't increment here, so this doesn't count as a retry
            continue

        except FileReferenceExpired:
            # Pyrogram sometimes raises this instead of handling it internally.
            # Re-fetch the message to get a fresh file reference before retrying.
            if dest_temp.exists():
                dest_temp.unlink()
            if attempt < config.max_retries:
                delay = min(config.base_delay * (2 ** (attempt - 1)), config.max_delay)
                log.warning(
                    f"Stale file reference for {dest_path.name}, "
                    f"refreshing and retrying in {delay}s..."
                )
                try:
                    fresh = await client.get_messages(
                        chat_id=message.chat.id,
                        message_ids=message.id,
                        replies=0,
                    )
                    if fresh:
                        message = fresh
                except Exception as ref_err:
                    log.warning(f"Failed to refresh message reference: {ref_err}")
                await asyncio.sleep(delay)
                continue
            else:
                log.error(
                    f"Download failed after {config.max_retries} retries "
                    f"(stale file reference): {dest_path.name}"
                )
                return False

        except Exception as e:
            # Transient errors: network issues, timeouts, etc.
            if attempt < config.max_retries:
                # Calculate exponential backoff: 2^(attempt-1) * base_delay, capped at max_delay
                delay = min(config.base_delay * (2 ** (attempt - 1)), config.max_delay)
                log.warning(
                    f"Download failed (attempt {attempt}/{config.max_retries}): {e}. "
                    f"Retrying in {delay}s..."
                )

                # Delete partial file on failure (per 01-CONTEXT.md decision)
                if dest_temp.exists():
                    dest_temp.unlink()

                await asyncio.sleep(delay)
                # Loop continues for next retry attempt
            else:
                # All retries exhausted
                log.error(
                    f"Download failed after {config.max_retries} retries: {e}"
                )

                # Clean up partial file
                if dest_temp.exists():
                    dest_temp.unlink()

                return False

    # This should never be reached due to return statements in loop
    # But included for completeness
    return False
