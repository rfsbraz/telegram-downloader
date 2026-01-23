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
from src.state import CursorStore
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
    source_config: SourceConfig
) -> int:
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

    Returns:
        Number of successfully downloaded files
    """
    downloaded = 0

    async def download_one(msg: Message) -> None:
        """Download single message with semaphore."""
        nonlocal downloaded

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

            # Build organized destination path (includes per-source folder and validation)
            try:
                dest = await build_destination_path(
                    download_dir,
                    source,
                    fname,
                    source_config
                )
            except ValueError as e:
                log.error(f"Path validation failed for {fname}: {e}")
                cursor_store.set(cursor_key, msg.id)
                return

            # Check for duplicates and resolve conflicts
            if dest.exists():
                media_size = getattr(media, "file_size", 0)
                if is_duplicate(dest, media_size):
                    log.info(f"Skip duplicate: {dest.name} (same size)")
                    cursor_store.set(cursor_key, msg.id)
                    return
                # Different content, resolve conflict
                original_dest = dest
                try:
                    dest = resolve_conflict(dest)
                    log.info(f"Conflict resolved: {original_dest.name} → {dest.name}")
                except RuntimeError as e:
                    log.error(f"Cannot resolve conflict for {dest.name}: {e}")
                    cursor_store.set(cursor_key, msg.id)
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
                log
            )

            if success:
                downloaded += 1
                cursor_store.set(cursor_key, msg.id)
            else:
                log.error(f"Failed to download: {dest.name}")
                # Still update cursor to avoid getting stuck
                cursor_store.set(cursor_key, msg.id)

    # Use TaskGroup (Python 3.11+) for structured concurrency
    async with asyncio.TaskGroup() as tg:
        for msg in messages:
            tg.create_task(download_one(msg))

    return downloaded


async def startup_validation(cfg, log, client):
    """
    Startup validation - fail fast on configuration/auth errors.

    Validates:
    - Telegram authentication (client.get_me())
    - Peer cache population (get_dialogs to enable private chat ID resolution)
    - Source accessibility (parse_sources + validate_source_access)

    Returns:
        sources_with_filters: List of (source, filter_config) tuples for run_check

    Raises:
        ConfigError: Configuration validation failed
        RuntimeError: Telegram auth or source access failed

    BLOCKER 2 FIX: validate_source_access() exceptions propagate unchanged.
    RuntimeError indicates source inaccessibility (fail-fast behavior).

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
    async for _ in client.get_dialogs():
        dialog_count += 1
    log.debug(f"Loaded {dialog_count} dialogs into peer cache")

    # Parse and validate sources (BLOCKER 3 FIX: parse once, return result)
    log.info("Validating configured sources...")
    sources_with_filters = await parse_sources(cfg, client)
    sources = [s for s, _ in sources_with_filters]

    # BLOCKER 2 FIX: Let validate_source_access exceptions propagate
    # RuntimeError from validate_source_access indicates source inaccessibility
    # This is fail-fast behavior - startup should fail if sources are inaccessible
    await validate_source_access(sources, client)
    log.info(f"All {len(sources)} source(s) accessible")

    return sources_with_filters


async def run_check(cfg, log, state_store, client, sources_with_filters):
    """
    Single check iteration - process all configured sources.

    This function is called either once (run-once mode) or periodically
    (daemon mode) depending on configuration.

    Args:
        cfg: Configuration object
        log: Logger instance
        state_store: CursorStore instance
        client: Pyrogram client instance
        sources_with_filters: Pre-parsed list of (source, filter_config) tuples
    """
    # Create global concurrency control
    semaphore = asyncio.Semaphore(cfg.max_concurrent_downloads)

    # Build mapping: cursor_key -> source_config for folder naming
    source_config_map: dict[str, SourceConfig] = {}
    for idx, (source, _) in enumerate(sources_with_filters):
        cursor_key = source.get_cursor_key()
        # Use same index to get corresponding source config
        source_config_map[cursor_key] = cfg.sources[idx]

    # Iterate sources sequentially (config order = priority)
    for source, composite_filter in sources_with_filters:
        cursor_key = source.get_cursor_key()
        last_seen_id = state_store.get(cursor_key, 0)

        log.info("=" * 60)
        log.info(
            f"Processing {await source.get_display_name()}, "
            f"last_seen={last_seen_id}"
        )
        log.info("=" * 60)

        # Collect candidate messages (newest first from source)
        # Stop early once we have enough to satisfy download limit
        max_downloads = cfg.max_downloads_per_run or 0
        candidates = []
        async for msg in source.iterate_new_media(last_seen_id):
            if await composite_filter.matches(msg):
                candidates.append(msg)
                # Stop scanning once we have enough (0 = unlimited)
                if max_downloads and len(candidates) >= max_downloads:
                    log.debug(f"Reached download limit ({max_downloads}), stopping scan")
                    break

        if not candidates:
            log.info("No new matching documents.")
            continue

        # Sort oldest first for sequential processing (ensures cursor advances correctly)
        candidates.sort(key=lambda m: m.id)

        log.info(
            f"Found {len(candidates)} candidates "
            f"(oldest={candidates[0].id}, newest={candidates[-1].id})"
        )

        # Look up source_config for this source with defensive check
        source_config = source_config_map.get(cursor_key)
        if source_config is None:
            log.error(f"No source config found for cursor key: {cursor_key}")
            continue  # Skip this source, move to next

        # Download batch concurrently
        downloaded = await download_batch(
            candidates,
            semaphore,
            client,
            Path(cfg.download_dir),
            state_store,
            cursor_key,
            cfg,
            log,
            source,
            source_config
        )

        log.info(f"Downloaded {downloaded}/{len(candidates)} files")


async def main():
    """Main entry point - daemon or run-once based on config."""
    cfg = load_config("/app/config.yaml")
    log = setup_logging(cfg.log_file, cfg.verbosity)

    # Override log level from daemon config if specified
    if cfg.daemon.log_level:
        log.setLevel(getattr(logging, cfg.daemon.log_level.upper()))

    # Initialize state store
    state_store = CursorStore("/app/state.db")
    if Path("/app/state.yaml").exists():
        log.info("Migrating state from YAML to SQLite...")
        state_store.migrate_from_yaml("/app/state.yaml")

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
                    await run_check(cfg, log, state_store, client, sources_with_filters)

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
                await run_check(cfg, log, state_store, client, sources_with_filters)
    finally:
        # Cleanup
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
