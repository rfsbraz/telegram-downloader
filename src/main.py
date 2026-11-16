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
import errno
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from pyrogram import Client
from pyrogram.types import Message
from pyrogram import errors as tg_errors

from src.config import load_config, ConfigError
from src.config.schema import SourceConfig
from src.config.source_parser import parse_sources, validate_source_access
from src.organization import build_destination_path, is_duplicate, resolve_conflict
from src.sources.base import BaseSource
from src.media import collect_matching_ids, get_media, is_photo_only, media_filename
from src.state import CursorStore, DownloadHistory, PendingDownloads
from src.client import create_client, diskspace, download_media_with_retry
from src.client.downloader import DiskFullError, temp_path
from src.client.hooks import run_post_download_hook
from src.client.ratelimit import RateLimiter, parse_rate
from src.notifications import NotificationManager, DiscordNotifier, GenericWebhook
from src.client.errors import AUTH_ERRORS
from src.daemon.health import HealthMonitor
from src.daemon.service import notify_low_disk_space


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


def _media_info(msg: Message) -> tuple[object | None, str, int, str | None]:
    """Return (media, filename, size, file_unique_id) for a message."""
    media = (
        msg.document or
        msg.audio or
        msg.video or
        msg.animation or
        msg.voice or
        msg.video_note
    )
    fname = (getattr(media, "file_name", None) if media else None) or f"message_{msg.id}"
    size = getattr(media, "file_size", 0) if media else 0
    unique = getattr(media, "file_unique_id", None) if media else None
    return media, fname, size or 0, unique


async def dry_run_source(
    source: BaseSource,
    composite_filter,
    source_config: SourceConfig,
    last_seen_id: int,
    download_dir: Path,
    flat_structure: bool,
    history,
    log,
    display_name: str,
    planned_ids: set[str] | None = None,
    planned_paths: dict[Path, int] | None = None,
    stats: dict | None = None,
) -> dict:
    """Evaluate filters and destinations for one source without writing anything."""
    if stats is None:
        stats = {
            "downloaded": 0,
            "skipped_duplicate": 0,
            "skipped_tracked": 0,
            "skipped_error": 0,
            "skipped_filter": 0,
            "deferred_low_space": 0,
            "bytes_downloaded": 0,
        }
    planned_ids = planned_ids if planned_ids is not None else set()
    planned_paths = planned_paths if planned_paths is not None else {}
    # Filter during the scan so rejected Message objects can be released.
    # Keep only compact metadata for matches, then reserve oldest-first.
    candidates: list[tuple[int, str, int, str | None]] = []
    iterate_error = None
    try:
        async for msg in source.iterate_new_media(last_seen_id):
            _media, fname, size, unique = _media_info(msg)
            if hasattr(composite_filter, "rejection_reason"):
                reason = await composite_filter.rejection_reason(msg)
            elif not await composite_filter.matches(msg):
                reason = "filter"
            else:
                reason = None
            if reason:
                log.info(
                    f"Would skip ({reason}): {fname} ({format_bytes(size)}) from {display_name}"
                )
                stats["skipped_filter"] += 1
                continue
            candidates.append((msg.id, fname, size, unique))
    except Exception as exc:
        iterate_error = exc
    # Normal downloads process pending batches oldest-first. Preview the same way.
    candidates.sort(key=lambda item: item[0])
    for _msg_id, fname, size, unique in candidates:
        if unique and history is not None and (
            history.contains(unique) or unique in planned_ids
        ):
            log.info(
                f"Would skip (already tracked): {fname} ({format_bytes(size)}) "
                f"from {display_name}"
            )
            stats["skipped_tracked"] += 1
            continue

        try:
            dest = await build_destination_path(
                download_dir,
                source,
                fname,
                source_config,
                flat_structure,
                create_dirs=False,
            )
        except ValueError as e:
            log.info(f"Would skip (path error): {fname} from {display_name}: {e}")
            stats["skipped_error"] += 1
            continue

        if dest.exists() or dest in planned_paths:
            if is_duplicate(dest, size, overlay=planned_paths):
                log.info(
                    f"Would skip (duplicate): {dest.name} ({format_bytes(size)}) "
                    f"from {display_name}"
                )
                stats["skipped_duplicate"] += 1
                continue
            try:
                dest = resolve_conflict(dest, overlay=planned_paths)
            except RuntimeError as e:
                log.info(f"Would skip (path error): {fname} from {display_name}: {e}")
                stats["skipped_error"] += 1
                continue

        log.info(
            f"Would download: {fname} ({format_bytes(size)}) from {display_name} -> {dest}"
        )
        stats["downloaded"] += 1
        stats["bytes_downloaded"] += size
        planned_paths[dest] = size
        if unique and history is not None:
            planned_ids.add(unique)
    if iterate_error is not None:
        raise iterate_error
    return stats


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
    limiter: "RateLimiter | None" = None,
    include_photos: bool = False,
) -> tuple[dict, set[int], set[int]]:
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
        limiter: Optional shared RateLimiter capping aggregate download speed

    Returns:
        Tuple of (stats, failed_message_ids, deferred_message_ids).
        stats is a counter dict: downloaded, skipped_duplicate, skipped_tracked,
        skipped_error, skipped_filter, deferred_low_space, bytes_downloaded.
        Failed IDs are messages where download_media_with_retry returned False.
        Skips (history hit, duplicate, path error) are NOT failures.
        Deferred IDs did not fit in the free space minus min_free_space
        (issue #61): they stay pending, do not use an attempt and do not move
        the cursor.
    """
    stats = {
        "downloaded": 0,
        "skipped_duplicate": 0,
        "skipped_tracked": 0,
        "skipped_error": 0,
        "skipped_filter": 0,
        "deferred_low_space": 0,
        "bytes_downloaded": 0,
    }
    failed_ids: set[int] = set()
    deferred_ids: set[int] = set()
    reserve = diskspace.reserve_bytes(config)
    # Downloads already started in this batch: msg id -> (size, partial file). Their
    # unwritten bytes count against the free space, so concurrent downloads can't all pass
    # the check against the same free space. Written bytes are already in free_bytes.
    in_flight: dict[int, tuple[int, Path]] = {}

    def unwritten_bytes() -> int:
        return sum(max(0, size - diskspace.written_bytes(part)) for size, part in in_flight.values())

    def defer(msg_id: int, reason: str) -> None:
        log.error(reason)
        stats["deferred_low_space"] += 1
        deferred_ids.add(msg_id)

    async def download_one(msg: Message) -> None:
        """Download single message with semaphore."""

        async with semaphore:  # Acquire semaphore slot
            # Extract media and filename. Honour the source photo setting so
            # photos queued while include_photos was on are not downloaded
            # after it is turned off, and are dropped from pending.
            if is_photo_only(msg) and not include_photos:
                fname = media_filename(msg, msg.photo) or f"message_{msg.id}"
                log.info(f"Skip (photos disabled): {fname}")
                cursor_store.set(cursor_key, msg.id)
                stats["skipped_filter"] += 1
                return
            media = get_media(msg, include_photos=include_photos)
            fname = media_filename(msg, media) if media else f"message_{msg.id}"
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
            except OSError as e:
                if e.errno != errno.ENOSPC:
                    raise
                # No room even for the folder (bytes or inodes): keep it pending
                defer(msg.id, f"Disk full creating the folder for {fname}. Kept pending.")
                return
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

            # Disk space guard (issue #61): keep it pending for the next run
            if reserve:
                free = diskspace.free_bytes(download_dir) - unwritten_bytes()
                if free < (media_size or 0) + reserve:
                    defer(
                        msg.id,
                        f"Not enough free space for {dest.name}: needs "
                        f"{format_bytes(media_size or 0)} plus the "
                        f"{format_bytes(reserve)} reserve, "
                        f"{format_bytes(free)} free. Kept pending.",
                    )
                    return

            # Download with retry logic
            log.info(
                f"Downloading: {dest.relative_to(download_dir)} "
                f"(msg {msg.id}, size={getattr(media, 'file_size', 0)} bytes)"
            )
            # No await between the check above and this line, so the claim is atomic
            in_flight[msg.id] = (media_size or 0, temp_path(dest, msg.id))
            try:
                success = await download_media_with_retry(
                    client,
                    msg,
                    dest,
                    config,
                    log,
                    expected_size=media_size,
                    limiter=limiter,
                )
            except DiskFullError as e:
                defer(msg.id, f"Disk full while downloading {dest.name}: {e}. Kept pending.")
                return
            finally:
                in_flight.pop(msg.id, None)

            if success:
                stats["downloaded"] += 1
                stats["bytes_downloaded"] += media_size or 0
                cursor_store.set(cursor_key, msg.id)
                if history and file_unique_id:
                    history.record(file_unique_id, fname, media_size, cursor_key, msg.id)

                # Post-download hook (issue #35) - failures are logged but
                # never mark the download as failed (the file is already saved)
                if config.post_download_hook:
                    source_name = source_config.name or await source.get_display_name()
                    actual_size = dest.stat().st_size if dest.exists() else media_size
                    await run_post_download_hook(
                        config.post_download_hook,
                        dest,
                        source_name,
                        actual_size,
                        config.post_download_hook_timeout,
                        log,
                    )
            else:
                log.error(f"Failed to download: {dest.name}")
                failed_ids.add(msg.id)

    # Use TaskGroup (Python 3.11+) for structured concurrency
    async with asyncio.TaskGroup() as tg:
        for msg in messages:
            tg.create_task(download_one(msg))

    return stats, failed_ids, deferred_ids


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
    except AUTH_ERRORS:
        raise
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


async def run_check(cfg, log, state_store, client, sources_with_filters, history=None, pending=None, limiter=None):
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
        limiter: Optional shared RateLimiter capping aggregate download speed

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
        "skipped_filter": 0,
        "deferred_low_space": 0,
        "bytes_downloaded": 0,
    }
    total_failed = 0
    sources_failed = 0
    dry_run = cfg.dry_run is True

    if dry_run:
        log.warning(
            "DRY RUN is active: nothing will be downloaded and no state will be written. "
            "Unset TDL_DRY_RUN when you are ready to download."
        )

    # Disk space guard (issue #61): one loud error instead of failing file by file
    reserve = diskspace.reserve_bytes(cfg)
    if reserve and not dry_run:
        free = diskspace.free_bytes(Path(cfg.download_dir))
        if free < reserve:
            log.error(
                f"Free space on {cfg.download_dir} ({format_bytes(free)}) is below the "
                f"reserve of {format_bytes(reserve)} (TDL_MIN_FREE_SPACE). Skipping this "
                f"check; pending downloads resume once space is freed."
            )
            return {
                "sources_checked": 0,
                "low_disk_space": True,
                "free_space": format_bytes(free),
                "duration": f"{time.monotonic() - run_started:.1f}s",
            }

    # Create global concurrency control
    semaphore = asyncio.Semaphore(cfg.max_concurrent_downloads)

    # Shared across sources so the preview matches a real run's history
    # records and destination reservations without writing them.
    planned_ids: set[str] = set()
    planned_paths: dict[Path, int] = {}

    # Iterate sources sequentially (config order = priority)
    for source, composite_filter, source_config in sources_with_filters:
        cursor_key = source.get_cursor_key()
        display_name = cursor_key
        try:
            last_seen_id = state_store.get(cursor_key, 0)
            display_name = await source.get_display_name()

            log.info("=" * 60)
            log.info(
                f"Processing {display_name}, "
                f"last_seen={last_seen_id}"
            )
            log.info("=" * 60)

            if dry_run:
                batch_stats = {
                    "downloaded": 0,
                    "skipped_duplicate": 0,
                    "skipped_tracked": 0,
                    "skipped_error": 0,
                    "skipped_filter": 0,
                    "deferred_low_space": 0,
                    "bytes_downloaded": 0,
                }
                try:
                    await dry_run_source(
                        source,
                        composite_filter,
                        source_config,
                        last_seen_id,
                        Path(cfg.download_dir),
                        cfg.flat_structure,
                        history,
                        log,
                        display_name,
                        planned_ids=planned_ids,
                        planned_paths=planned_paths,
                        stats=batch_stats,
                    )
                finally:
                    # Keep partial preview counts even if this source fails later.
                    for key in totals:
                        totals[key] += batch_stats.get(key, 0)
                continue

            max_downloads = cfg.max_downloads_per_run or 0

            # --- Scan phase: stream IDs into pending ---
            if pending and pending.has_pending(cursor_key):
                # Resume mode: scan only for NEW messages above the pending range
                scan_above = pending.get_max_message_id(cursor_key)
                new_ids = await collect_matching_ids(
                    source, scan_above, composite_filter, log
                )
                if new_ids:
                    pending.add_batch(cursor_key, new_ids)
                    log.info(f"Added {len(new_ids)} new message(s) to pending queue")
            else:
                # Fresh scan: stream matching IDs into pending (no Message accumulation)
                scanned_ids = await collect_matching_ids(
                    source, last_seen_id, composite_filter, log
                )

                if not scanned_ids:
                    log.info("No new matching documents.")
                    continue

                pending.add_batch(cursor_key, scanned_ids)
                log.info(f"Found {len(scanned_ids)} candidates, queued for download")

            # --- Download phase: pull batches from pending, fetch fresh messages ---
            batch_size = max_downloads if max_downloads else 200
            total_downloaded = 0

            while True:
                # Exclude messages that exhausted their attempt budget so one
                # permanently failing message can't loop this check forever
                batch_ids = pending.get_oldest(
                    cursor_key, batch_size, cfg.max_download_attempts
                )
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

                batch_stats, failed_ids, deferred_ids = await download_batch(
                    candidates, semaphore, client, Path(cfg.download_dir),
                    state_store, cursor_key, cfg, log, source, source_config, history,
                    limiter,
                    include_photos=getattr(composite_filter, "include_photos", False),
                )

                # Remove from pending: orphaned + processed (everything except
                # failures and downloads deferred for disk space)
                remove_ids = orphaned_ids | (candidate_ids - failed_ids - deferred_ids)
                pending.remove_batch(cursor_key, list(remove_ids))
                total_downloaded += batch_stats["downloaded"]
                total_failed += len(failed_ids)
                for key in totals:
                    totals[key] += batch_stats.get(key, 0)

                # Track failures so repeatedly failing messages are eventually
                # dead-lettered instead of retried indefinitely
                if failed_ids:
                    pending.increment_attempts(cursor_key, list(failed_ids))
                    still_pending = pending.count(
                        cursor_key, cfg.max_download_attempts
                    )
                    exhausted_now = pending.count_exhausted(
                        cursor_key, cfg.max_download_attempts
                    )
                    log.warning(
                        f"{len(failed_ids)} download(s) failed "
                        f"({still_pending} still within attempt budget, "
                        f"{exhausted_now} exhausted after "
                        f"{cfg.max_download_attempts} attempts)"
                    )

                if deferred_ids:
                    break  # Out of disk space: the rest waits for the next run
                if max_downloads:
                    break  # Capped mode: one batch only

            remaining = pending.count(cursor_key, cfg.max_download_attempts)
            if remaining:
                log.info(f"{remaining} message(s) still pending for next run")
            exhausted = pending.count_exhausted(cursor_key, cfg.max_download_attempts)
            if exhausted:
                log.error(
                    f"{exhausted} message(s) gave up after {cfg.max_download_attempts} "
                    f"failed attempts and will not be retried (kept in pending table "
                    f"for inspection)"
                )
            log.info(f"Downloaded {total_downloaded} files")
        except (tg_errors.FloodWait, tg_errors.Unauthorized):
            # Account-wide errors hit every later source too: let the
            # daemon's circuit breaker and error handling see them (#57)
            raise
        except Exception as e:
            # One broken source must not starve the ones after it (#57).
            # Its pending queue resumes on the next run.
            sources_failed += 1
            log.error(
                f"Source {display_name} failed, continuing with the next one: {e}",
                exc_info=True,
            )

    # --- Run summary (issue #34) ---
    duration = time.monotonic() - run_started
    skipped_total = (
        totals["skipped_duplicate"]
        + totals["skipped_tracked"]
        + totals["skipped_error"]
        + totals["skipped_filter"]
    )
    breakdown_parts = []
    if totals["skipped_duplicate"]:
        breakdown_parts.append(f"{totals['skipped_duplicate']} duplicate")
    if totals["skipped_tracked"]:
        breakdown_parts.append(f"{totals['skipped_tracked']} already tracked")
    if totals["skipped_error"]:
        breakdown_parts.append(f"{totals['skipped_error']} path error")
    if totals["skipped_filter"]:
        breakdown_parts.append(f"{totals['skipped_filter']} filter")
    breakdown = f" ({', '.join(breakdown_parts)})" if breakdown_parts else ""

    downloaded_label = "Files that would download:" if dry_run else "Files downloaded:  "
    bytes_label = "Bytes that would transfer:" if dry_run else "Bytes downloaded:  "
    log.info("=" * 18 + " Run Summary " + "=" * 18)
    log.info(f"Sources checked:    {len(sources_with_filters)}")
    log.info(f"Sources failed:     {sources_failed}")
    log.info(f"{downloaded_label} {totals['downloaded']}")
    log.info(f"Files skipped:      {skipped_total}{breakdown}")
    log.info(f"Files failed:       {total_failed}")
    if totals["deferred_low_space"]:
        log.info(f"Files deferred:     {totals['deferred_low_space']} (low disk space)")
    log.info(f"{bytes_label} {format_bytes(totals['bytes_downloaded'])}")
    log.info(f"Duration:           {duration:.1f}s")
    log.info("=" * 49)

    # Isolation keeps a partial failure healthy, but a check where every
    # source failed did nothing: fail it so the daemon reports it (#57)
    if sources_with_filters and sources_failed == len(sources_with_filters):
        raise RuntimeError(
            f"{sources_failed} of {len(sources_with_filters)} source(s) failed "
            f"this check, see the errors above"
        )

    return {
        "sources_checked": len(sources_with_filters),
        "sources_failed": sources_failed,
        "files_downloaded": totals["downloaded"],
        "files_skipped": skipped_total,
        "files_failed": total_failed,
        "files_deferred_low_space": totals["deferred_low_space"],
        "low_disk_space": totals["deferred_low_space"] > 0,
        "dry_run": dry_run,
        "bytes_downloaded": format_bytes(totals["bytes_downloaded"]),
        "duration": f"{duration:.1f}s",
    }


def warn_ignored_settings(cfg, log) -> None:
    """Warn about settings that are accepted but have no effect."""
    if "detail_level" in cfg.notifications.model_fields_set:
        log.warning(
            "TDL_NOTIFICATIONS_DETAIL_LEVEL is set but has no effect: "
            "all notifications have the same content. You can remove it."
        )


def build_notification_manager(cfg, log) -> Optional[NotificationManager]:
    """Build the NotificationManager from config, or None if disabled."""
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
    return notification_manager


async def handle_auth_failure(cfg, log, notification_manager, error) -> None:
    """Report a dead Telegram session: health file error + notification (#78)."""
    reason = f"Telegram session needs re-auth: {error}"
    log.error(reason)
    HealthMonitor(Path(cfg.daemon.health_file)).update_status("error", reason=reason)
    if notification_manager:
        await notification_manager.notify(
            level="error",
            title="Telegram Session Needs Re-auth",
            message=reason,
            details={"error_type": type(error).__name__},
            force=True,
        )


async def wait_for_shutdown() -> None:
    """Block until SIGTERM/SIGINT (docker stop) instead of crash-looping."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()


async def main(
    config_path: str = "/app/config.yaml",
    state_yaml_path: str | Path = "/app/state.yaml",
):
    """Main entry point - daemon or run-once based on config."""
    cfg = load_config(config_path)
    log = setup_logging(cfg.log_file, cfg.verbosity)

    # Override log level from daemon config if specified
    if cfg.daemon.log_level:
        log.setLevel(getattr(logging, cfg.daemon.log_level.upper()))
    warn_ignored_settings(cfg, log)

    # Initialize state store (in sessions dir so it persists via volume mount).
    # Dry-run uses in-memory clones so the session dir, state.db, WAL, and
    # state.yaml are never created or rewritten.
    dry_run = cfg.dry_run is True
    state_db_path = cfg.session_dir / "state.db"
    state_store = CursorStore(str(state_db_path), ephemeral=dry_run)
    if not dry_run and Path(state_yaml_path).exists():
        log.info("Migrating state from YAML to SQLite...")
        state_store.migrate_from_yaml(str(state_yaml_path))

    # Initialize download history for persistent deduplication
    history = None
    if cfg.track_downloads:
        history = DownloadHistory(str(state_db_path), ephemeral=dry_run)
        log.info("Download history tracking enabled")

    # Initialize pending downloads queue
    pending = PendingDownloads(str(state_db_path), ephemeral=dry_run)
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

    # Optional bandwidth cap shared by all downloads (issue #36)
    limiter = None
    if cfg.max_download_speed:
        limiter = RateLimiter(parse_rate(cfg.max_download_speed))
        log.info(f"Download speed capped at {cfg.max_download_speed}/s")

    # Built before connecting so auth failures can be reported too (#78).
    # Only the daemon uses it for routine check notifications.
    notification_manager = build_notification_manager(cfg, log)

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

                # Create daemon service
                from src.daemon import DaemonService

                # BLOCKER 3 FIX: Pass sources_with_filters to run_check via closure
                # Do NOT re-parse sources in run_check - reuse startup_validation result
                async def check_wrapper():
                    """Wrapper for run_check that captures sources_with_filters."""
                    return await run_check(cfg, log, state_store, client, sources_with_filters, history, pending, limiter)

                service = DaemonService(
                    check_function=check_wrapper,
                    check_interval=cfg.daemon.check_interval,
                    check_timeout=cfg.daemon.check_timeout,
                    health_file=Path(cfg.daemon.health_file),
                    notification_manager=notification_manager,
                    active_hours=cfg.schedule_active_hours
                )

                # Run daemon
                await service.run()
            else:
                log.info("Running in single-shot mode")
                summary = await run_check(cfg, log, state_store, client, sources_with_filters, history, pending, limiter)
                if notification_manager:
                    await notify_low_disk_space(notification_manager, summary)
    except AUTH_ERRORS as e:
        await handle_auth_failure(cfg, log, notification_manager, e)
        if not cfg.daemon.enabled:
            raise SystemExit(1)
        # Stay up with status=error so Docker marks the container unhealthy,
        # instead of exiting into a restart loop. Re-auth, then restart.
        log.error("Waiting for re-auth; restart the container once the session is fixed")
        await wait_for_shutdown()
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
