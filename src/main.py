"""
Main entry point for Telegram media downloader.

Orchestrates the download process using modular components:
- Config validation layer
- SQLite state persistence
- Streaming client with retry logic
- Pluggable filters for media selection
- Source abstraction for forum topics

This is the refactored version of downloader.py using the new
foundation architecture.
"""

import asyncio
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from pyrogram import Client
from pyrogram.types import Message

from src.config import load_config, ConfigError
from src.config.schema import SourceConfig
from src.config.source_parser import parse_sources, validate_source_access
from src.organization import build_destination_path, is_duplicate, resolve_conflict
from src.sources.base import BaseSource
from src.state import CursorStore, DownloadHistory, PendingDownloads
from src.client import create_client, download_media_with_retry
from src.notifications import NotificationManager, DiscordNotifier, GenericWebhook


def setup_logging(log_file: str, verbosity: str) -> logging.Logger:
    """Configure logging with file and console handlers.

    Args:
        log_file: Path to log file (empty string disables file logging)
        verbosity: Logging level (quiet, normal, verbose)

    Returns:
        Configured logger instance
    """
    levels = {
        "quiet": logging.WARNING,
        "normal": logging.INFO,
        "verbose": logging.DEBUG
    }
    level = levels.get((verbosity or "normal").lower(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(
            RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
        )

    for h in handlers:
        h.setFormatter(fmt)

    logging.basicConfig(level=level, handlers=handlers, force=True)

    # Quiet noisy libraries (unless verbose mode for debugging)
    lib_level = logging.DEBUG if level == logging.DEBUG else logging.WARNING
    for name, lvl in [
        ("pyrogram", lib_level),
        ("httpx", logging.WARNING),
        ("urllib3", logging.WARNING),
        ("asyncio", logging.WARNING),
    ]:
        lg = logging.getLogger(name)
        lg.setLevel(lvl)
        lg.propagate = False

    return logging.getLogger("downloader")


def format_bytes(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (e.g. '142.5 MB')."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


async def download_batch(
    messages: list[Message],
    semaphore: asyncio.Semaphore,
    client: Client,
    download_dir: Path,
    cursor_store: CursorStore,
    cursor_key: str,
    config,
    log: logging.Logger,
    source: BaseSource,
    source_config: SourceConfig,
    history: "DownloadHistory | None" = None,
) -> tuple[int, set[int]]:
    """Download a batch of messages concurrently with semaphore limit.

    Args:
        messages: List of messages to download
        semaphore: Global concurrency limit semaphore
        client: Pyrogram client
        download_dir: Destination directory
        cursor_store: State store for cursor updates
        cursor_key: Cursor key for this source
        config: Configuration object
        log: Logger instance
        source: Source object for this batch
        source_config: Source configuration for folder naming
        history: Optional download history for persistent deduplication

    Returns:
        Tuple of (stats, failed_message_ids).
        stats is a counter dict: downloaded, skipped_duplicate, skipped_tracked,
        skipped_error, bytes_downloaded.
        Failed IDs are messages where download_media_with_retry returned False.
        Skips (history hit, duplicate, path error) are NOT failures.
    """
    stats = {
        "downloaded": 0,
        "skipped_duplicate": 0,
        "skipped_tracked": 0,
        "skipped_error": 0,
        "bytes_downloaded": 0,
    }
    failed_ids: set[int] = set()

    async def download_one(msg: Message) -> None:
        """Download single message with semaphore."""

        async with semaphore:  # Acquire semaphore slot
            # Extract media and filename
            media = (
                msg.document or
                msg.audio or
                msg.video or
                msg.animation or
                msg.voice or
                msg.video_note
            )
            fname = getattr(media, "file_name", None) or f"message_{msg.id}"
            media_size = getattr(media, "file_size", 0)

            # Check download history for persistent deduplication
            file_unique_id = getattr(media, "file_unique_id", None)
            if history and file_unique_id and history.contains(file_unique_id):
                log.info(f"Skip (already downloaded): {fname}")
                cursor_store.set(cursor_key, msg.id)
                stats["skipped_tracked"] += 1
                return

            # Build organized destination path (includes per-source folder and validation)
            try:
                dest = await build_destination_path(
                    download_dir,
                    source,
                    fname,
                    source_config,
                    config.flat_structure,
                )
            except ValueError as e:
                log.error(f"Path validation failed for {fname}: {e}")
                cursor_store.set(cursor_key, msg.id)
                stats["skipped_error"] += 1
                return

            # Check for duplicates and resolve conflicts
            if dest.exists():
                if is_duplicate(dest, media_size):
                    log.info(f"Skip duplicate: {dest.name} (same size)")
                    cursor_store.set(cursor_key, msg.id)
                    stats["skipped_duplicate"] += 1
                    return
                # Different content, resolve conflict
                original_dest = dest
                try:
                    dest = resolve_conflict(dest)
                    log.info(f"Conflict resolved: {original_dest.name} → {dest.name}")
                except RuntimeError as e:
                    log.error(f"Cannot resolve conflict for {dest.name}: {e}")
                    cursor_store.set(cursor_key, msg.id)
                    stats["skipped_error"] += 1
                    return

            # Download with retry logic
            log.info(
                f"Downloading: {dest.relative_to(download_dir)} "
                f"(msg {msg.id}, size={getattr(media, 'file_size', 0)} bytes)"
            )
            success = await download_media_with_retry(
                client,
                msg,
                dest,
                config,
                log,
                expected_size=media_size,
            )

            if success:
                stats["downloaded"] += 1
                stats["bytes_downloaded"] += media_size or 0
                cursor_store.set(cursor_key, msg.id)
                if history and file_unique_id:
                    history.record(file_unique_id, fname, media_size, cursor_key, msg.id)
            else:
                log.error(f"Failed to download: {dest.name}")
                failed_ids.add(msg.id)

    # Use TaskGroup (Python 3.11+) for structured concurrency
    async with asyncio.TaskGroup() as tg:
        for msg in messages:
            tg.create_task(download_one(msg))

    return stats, failed_ids


async def startup_validation(cfg, log, client):
    """
    Startup validation - fail fast on configuration/auth errors.

    Validates:
    - Telegram authentication (client.get_me())
    - Peer cache population (get_dialogs to enable private chat ID resolution)
    - Source accessibility (parse_sources + validate_source_access)

    Returns:
        sources_with_filters: List of (source, filter, source_config) tuples
        for run_check. Sources that cannot be resolved or accessed are
        skipped with an error log (issue #40); startup only fails if NO
        source is usable.

    Raises:
        ConfigError: Configuration validation failed or no usable sources
        RuntimeError: Telegram auth failed

    BLOCKER 3 FIX: Parse sources once here, return sources_with_filters.
    main() stores result and passes to run_check via closure.
    run_check() receives sources_with_filters as parameter (NOT re-parsing).
    """
    # Validate Telegram authentication
    try:
        me = await client.get_me()
        log.info(f"Authenticated as: {me.first_name} {me.last_name or ''}")
    except Exception as e:
        raise RuntimeError(f"Telegram authentication failed: {e}")

    # Fetch dialogs to populate peer cache (required for private chat IDs)
    # Without this, numeric chat IDs from t.me/c/ links fail with PEER_ID_INVALID
    log.info("Loading chat list to populate peer cache...")
    dialog_count = 0
    try:
        async for _ in client.get_dialogs():
            dialog_count += 1
        log.debug(f"Loaded {dialog_count} dialogs into peer cache")
    except Exception as e:
        # Pyrogram can crash while parsing certain dialogs (e.g.
        # "'NoneType' object has no attribute 'id'" on dialogs whose peer
        # can't be resolved - see issue #47). The dialogs iterated before
        # the failure are already cached, so degrade to a warning instead
        # of taking the whole app down: only sources configured via
        # private t.me/c/ links that weren't cached yet would be affected,
        # and those will surface a clear per-source error later.
        log.warning(
            f"Chat list loading failed after {dialog_count} dialog(s): {e}. "
            f"Continuing with a partial peer cache; sources configured via "
            f"private t.me/c/ links may fail to resolve this run."
        )

    # Parse and validate sources (BLOCKER 3 FIX: parse once, return result)
    log.info("Validating configured sources...")
    sources_with_filters = await parse_sources(cfg, client)
    sources_with_filters = await validate_source_access(sources_with_filters, client)

    configured = len(cfg.sources)
    usable = len(sources_with_filters)
    if usable == 0:
        raise ConfigError(
            f"None of the {configured} configured source(s) are accessible. "
            f"Check the errors above and fix your configuration."
        )
    if usable < configured:
        log.warning(
            f"{configured - usable} of {configured} source(s) skipped as "
            f"unresolvable/inaccessible - see errors above"
        )
    log.info(f"{usable} source(s) accessible")

    return sources_with_filters


async def run_check(cfg, log, state_store, client, sources_with_filters, history=None, pending=None):
    """
    Single check iteration - process all configured sources.

    This function is called either once (run-once mode) or periodically
    (daemon mode) depending on configuration.

    Args:
        cfg: Configuration object
        log: Logger instance
        state_store: CursorStore instance
        client: Pyrogram client instance
        sources_with_filters: Pre-parsed list of (source, filter, source_config) tuples
        history: Optional DownloadHistory for persistent deduplication
        pending: Optional PendingDownloads queue for resumable downloads

    Returns:
        Run summary dict (sources checked, files downloaded/skipped/failed,
        bytes downloaded, duration) for notification channels.
    """
    run_started = time.monotonic()
    totals = {
        "downloaded": 0,
        "skipped_duplicate": 0,
        "skipped_tracked": 0,
        "skipped_error": 0,
        "bytes_downloaded": 0,
    }
    total_failed = 0

    # Create global concurrency control
    semaphore = asyncio.Semaphore(cfg.max_concurrent_downloads)

    # Iterate sources sequentially (config order = priority)
    for source, composite_filter, source_config in sources_with_filters:
        cursor_key = source.get_cursor_key()
        last_seen_id = state_store.get(cursor_key, 0)

        log.info("=" * 60)
        log.info(
            f"Processing {await source.get_display_name()}, "
            f"last_seen={last_seen_id}"
        )
        log.info("=" * 60)

        max_downloads = cfg.max_downloads_per_run or 0

        # --- Scan phase: stream IDs into pending ---
        if pending and pending.has_pending(cursor_key):
            # Resume mode: scan only for NEW messages above the pending range
            scan_above = pending.get_max_message_id(cursor_key)
            new_ids = []
            async for msg in source.iterate_new_media(scan_above):
                if await composite_filter.matches(msg):
                    new_ids.append(msg.id)
            if new_ids:
                pending.add_batch(cursor_key, new_ids)
                log.info(f"Added {len(new_ids)} new message(s) to pending queue")
        else:
            # Fresh scan: stream matching IDs into pending (no Message accumulation)
            scanned_ids = []
            async for msg in source.iterate_new_media(last_seen_id):
                if await composite_filter.matches(msg):
                    scanned_ids.append(msg.id)

            if not scanned_ids:
                log.info("No new matching documents.")
                continue

            pending.add_batch(cursor_key, scanned_ids)
            log.info(f"Found {len(scanned_ids)} candidates, queued for download")

        # --- Download phase: pull batches from pending, fetch fresh messages ---
        batch_size = max_downloads if max_downloads else 200
        total_downloaded = 0

        while True:
            batch_ids = pending.get_oldest(cursor_key, batch_size)
            if not batch_ids:
                break

            # Fetch fresh Message objects (gives us valid file references)
            messages = await client.get_messages(
                chat_id=source.chat_id, message_ids=batch_ids
            )
            if not isinstance(messages, list):
                messages = [messages]
            candidates = [m for m in messages if m and m.id]
            candidates.sort(key=lambda m: m.id)

            # IDs that returned empty from get_messages (deleted/inaccessible)
            candidate_ids = {m.id for m in candidates}
            orphaned_ids = set(batch_ids) - candidate_ids

            if not candidates:
                pending.remove_batch(cursor_key, list(orphaned_ids))
                if max_downloads:
                    break
                continue

            log.info(
                f"Processing {len(candidates)} messages "
                f"(oldest={candidates[0].id}, newest={candidates[-1].id}, "
                f"total pending={pending.count(cursor_key)})"
            )

            batch_stats, failed_ids = await download_batch(
                candidates, semaphore, client, Path(cfg.download_dir),
                state_store, cursor_key, cfg, log, source, source_config, history,
            )

            # Remove from pending: orphaned + processed (everything except failures)
            remove_ids = orphaned_ids | (candidate_ids - failed_ids)
            pending.remove_batch(cursor_key, list(remove_ids))
            total_downloaded += batch_stats["downloaded"]
            total_failed += len(failed_ids)
            for key in totals:
                totals[key] += batch_stats[key]

            if max_downloads:
                break  # Capped mode: one batch only

        remaining = pending.count(cursor_key)
        if remaining:
            log.info(f"{remaining} message(s) still pending for next run")
        log.info(f"Downloaded {total_downloaded} files")

    # --- Run summary (issue #34) ---
    duration = time.monotonic() - run_started
    skipped_total = (
        totals["skipped_duplicate"]
        + totals["skipped_tracked"]
        + totals["skipped_error"]
    )
    breakdown_parts = []
    if totals["skipped_duplicate"]:
        breakdown_parts.append(f"{totals['skipped_duplicate']} duplicate")
    if totals["skipped_tracked"]:
        breakdown_parts.append(f"{totals['skipped_tracked']} already tracked")
    if totals["skipped_error"]:
        breakdown_parts.append(f"{totals['skipped_error']} path error")
    breakdown = f" ({', '.join(breakdown_parts)})" if breakdown_parts else ""

    log.info("=" * 18 + " Run Summary " + "=" * 18)
    log.info(f"Sources checked:    {len(sources_with_filters)}")
    log.info(f"Files downloaded:   {totals['downloaded']}")
    log.info(f"Files skipped:      {skipped_total}{breakdown}")
    log.info(f"Files failed:       {total_failed}")
    log.info(f"Bytes downloaded:   {format_bytes(totals['bytes_downloaded'])}")
    log.info(f"Duration:           {duration:.1f}s")
    log.info("=" * 49)

    return {
        "sources_checked": len(sources_with_filters),
        "files_downloaded": totals["downloaded"],
        "files_skipped": skipped_total,
        "files_failed": total_failed,
        "bytes_downloaded": format_bytes(totals["bytes_downloaded"]),
        "duration": f"{duration:.1f}s",
    }


async def main():
    """Main entry point - daemon or run-once based on config."""
    cfg = load_config("/app/config.yaml")
    log = setup_logging(cfg.log_file, cfg.verbosity)

    # Override log level from daemon config if specified
    if cfg.daemon.log_level:
        log.setLevel(getattr(logging, cfg.daemon.log_level.upper()))

    # Initialize state store (in sessions dir so it persists via volume mount)
    state_db_path = cfg.session_dir / "state.db"
    state_store = CursorStore(str(state_db_path))
    if Path("/app/state.yaml").exists():
        log.info("Migrating state from YAML to SQLite...")
        state_store.migrate_from_yaml("/app/state.yaml")

    # Initialize download history for persistent deduplication
    history = None
    if cfg.track_downloads:
        history = DownloadHistory(str(state_db_path))
        log.info("Download history tracking enabled")

    # Initialize pending downloads queue
    pending = PendingDownloads(str(state_db_path))
    log.info("Pending downloads queue initialized")

    # Log credentials for debugging (mask sensitive parts)
    log.debug("=" * 50)
    log.debug("AUTHENTICATION DEBUG INFO")
    log.debug("=" * 50)
    log.debug(f"API ID: {cfg.api_id}")
    log.debug(f"API Hash: {cfg.api_hash[:8]}...{cfg.api_hash[-4:]}" if cfg.api_hash else "API Hash: None")
    log.debug(f"Phone Number: {cfg.phone_number}")
    log.debug(f"Session Dir: {cfg.session_dir}")
    log.debug(f"Test Mode: {cfg.test_mode}")
    log.debug("=" * 50)

    # Warn if test mode is enabled
    if cfg.test_mode:
        log.warning("=" * 60)
        log.warning("TEST MODE ENABLED - Connecting to Telegram test servers")
        log.warning("DC2: 149.154.167.40:443")
        log.warning("Note: Test servers require test phone numbers (99966XXXXXX)")
        log.warning("=" * 60)

    # Create Pyrogram client
    client = create_client(cfg)

    try:
        log.debug("Attempting to connect and authenticate with Telegram...")
        async with client:
            log.debug("Successfully connected to Telegram!")
            # Startup validation (BLOCKER 3 FIX: parse sources once, store result)
            sources_with_filters = await startup_validation(cfg, log, client)

            # Branch based on daemon mode
            if cfg.daemon.enabled:
                log.info(
                    f"Starting daemon mode with {cfg.daemon.check_interval}s interval"
                )

                # Initialize notification manager if enabled
                notification_manager = None
                if cfg.notifications.enabled:
                    notifiers = []

                    # Add Discord notifier if webhook URL is configured
                    if cfg.notifications.discord_webhook_url:
                        discord = DiscordNotifier(
                            webhook_url=str(cfg.notifications.discord_webhook_url),
                            username=cfg.notifications.discord_username
                        )
                        notifiers.append(discord)

                    # Add generic webhook notifier if URL is configured
                    if cfg.notifications.generic_webhook_url:
                        webhook = GenericWebhook(
                            webhook_url=str(cfg.notifications.generic_webhook_url)
                        )
                        notifiers.append(webhook)

                    # Create notification manager if we have at least one channel
                    if notifiers:
                        notification_manager = NotificationManager(
                            notifiers=notifiers,
                            throttle_seconds=cfg.notifications.throttle_seconds
                        )
                        log.info(f"Notification system initialized with {len(notifiers)} channel(s)")

                # Create daemon service
                from src.daemon import DaemonService

                # BLOCKER 3 FIX: Pass sources_with_filters to run_check via closure
                # Do NOT re-parse sources in run_check - reuse startup_validation result
                async def check_wrapper():
                    """Wrapper for run_check that captures sources_with_filters."""
                    return await run_check(cfg, log, state_store, client, sources_with_filters, history, pending)

                service = DaemonService(
                    check_function=check_wrapper,
                    check_interval=cfg.daemon.check_interval,
                    health_file=Path(cfg.daemon.health_file),
                    notification_manager=notification_manager
                )

                # Run daemon
                await service.run()
            else:
                log.info("Running in single-shot mode")
                await run_check(cfg, log, state_store, client, sources_with_filters, history, pending)
    finally:
        # Cleanup
        if history:
            history.close()
        pending.close()
        state_store.close()
        log.info("Execution complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
