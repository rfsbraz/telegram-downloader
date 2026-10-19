"""
Source parser for creating Source instances from configuration.

Parses source configuration into Source instances with filter composition,
handling global filter defaults and per-source overrides.
"""

import logging
from typing import Optional

from pyrogram import Client

from src.config.loader import ConfigError
from src.config.schema import Config, GlobalFilters, SourceConfig
from src.config.url_parser import parse_telegram_url
from src.filters import (
    CompositeFilter,
    DateFilter,
    ExtensionFilter,
    PatternFilter,
    SizeFilter,
)
from src.sources.base import BaseSource
from src.sources.factory import create_source

logger = logging.getLogger("downloader")


def parse_size(size_str: str) -> int:
    """
    Parse human-readable size string to bytes.

    Supports formats: "1KB", "5MB", "2GB", "500B"
    Uses humanfriendly library if available, falls back to manual parsing.

    Args:
        size_str: Size string with unit suffix (KB, MB, GB)

    Returns:
        Size in bytes

    Raises:
        ValueError: If format is invalid

    Examples:
        >>> parse_size("1KB")
        1024
        >>> parse_size("5MB")
        5242880
        >>> parse_size("2GB")
        2147483648
    """
    # Try humanfriendly library first (optional dependency)
    try:
        import humanfriendly
        return humanfriendly.parse_size(size_str)
    except ImportError:
        pass

    # Fallback to manual parsing
    size_str = size_str.strip().upper()

    # Define multipliers
    units = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }

    # Extract number and unit
    import re
    match = re.match(r'^([\d.]+)\s*([A-Z]+)$', size_str)
    if not match:
        raise ValueError(
            f"Invalid size format: {size_str}. "
            f"Expected format: '1KB', '5MB', '2GB', etc."
        )

    number_str, unit = match.groups()

    # Parse number
    try:
        number = float(number_str)
    except ValueError:
        raise ValueError(f"Invalid number in size: {number_str}")

    # Validate unit
    if unit not in units:
        raise ValueError(
            f"Unknown size unit: {unit}. "
            f"Supported units: {', '.join(units.keys())}"
        )

    # Calculate bytes
    bytes_value = int(number * units[unit])
    return bytes_value


def build_filters(filter_config: GlobalFilters) -> CompositeFilter:
    """
    Build CompositeFilter from GlobalFilters configuration.

    Creates filter chain based on configured criteria:
    - Extensions (with archive support)
    - File size limits (min/max)
    - Date range (after/before)
    - Pattern matching (include/exclude)

    Args:
        filter_config: GlobalFilters configuration

    Returns:
        CompositeFilter with all configured filters

    Raises:
        ValueError: If filter configuration is invalid
    """
    filters = []

    # Extension filter (always added, default behavior)
    if filter_config.extensions:
        filters.append(
            ExtensionFilter(
                ebook_exts=filter_config.extensions,
                allow_archives=filter_config.allow_archives,
                archive_exts=filter_config.archive_exts,
            )
        )

    # Size filter
    min_bytes = None
    max_bytes = None

    if filter_config.min_size:
        try:
            min_bytes = parse_size(filter_config.min_size)
        except ValueError as e:
            raise ValueError(f"Invalid min_size: {e}")

    if filter_config.max_size:
        try:
            max_bytes = parse_size(filter_config.max_size)
        except ValueError as e:
            raise ValueError(f"Invalid max_size: {e}")

    if min_bytes is not None or max_bytes is not None:
        filters.append(SizeFilter(min_size=min_bytes, max_size=max_bytes))

    # Date filter
    if filter_config.only_after or filter_config.only_before:
        filters.append(
            DateFilter(
                after=filter_config.only_after,
                before=filter_config.only_before,
            )
        )

    # Pattern filter
    if filter_config.include_patterns or filter_config.exclude_patterns:
        filters.append(
            PatternFilter(
                include_patterns=filter_config.include_patterns,
                exclude_patterns=filter_config.exclude_patterns,
            )
        )

    return CompositeFilter(filters)


async def parse_sources(
    config: Config,
    client: Client
) -> list[tuple[BaseSource, CompositeFilter, SourceConfig]]:
    """
    Parse sources from configuration and create Source instances with filters.

    For each source:
    1. Resolves URL or chat_id to Source instance via factory
    2. Builds CompositeFilter by merging global and per-source filters
    3. Returns list of (source, filter, source_config) tuples

    Configuration errors (missing url/chat_id, invalid URL, bad filter
    values) fail fast with ConfigError - they need a config fix.
    Telegram-side resolution failures (deleted/renamed channel, ban,
    network issues) only skip that source with an error log, so one dead
    source doesn't take down the remaining ones (issue #40).

    Args:
        config: Configuration with sources list
        client: Authenticated Pyrogram client

    Returns:
        List of (BaseSource, CompositeFilter, SourceConfig) tuples for
        the sources that could be resolved

    Raises:
        ConfigError: If source configuration itself is invalid
    """
    results = []

    for idx, source_config in enumerate(config.sources):
        # --- Configuration parsing: fail fast on invalid config ---
        try:
            # Determine chat_id and topic_id
            chat_id = None
            topic_id = None

            if source_config.url:
                # Parse URL to get chat_id and topic_id
                parsed_id, parsed_topic = parse_telegram_url(source_config.url)
                chat_id = parsed_id
                topic_id = parsed_topic
            elif source_config.chat_id:
                # Use numeric chat_id directly
                chat_id = source_config.chat_id
                topic_id = source_config.topic_id
            else:
                raise ConfigError(
                    f"Source {idx + 1}: Either url or chat_id must be provided"
                )

            # Build filters: merge global with per-source overrides
            if source_config.filters:
                # Per-source filters override global filters
                # For lists, use source value if non-empty, otherwise use global
                # For scalars, use source value if not None, otherwise use global
                sf = source_config.filters
                gf = config.global_filters

                merged_filters = GlobalFilters(
                    extensions=sf.extensions if sf.extensions else gf.extensions,
                    allow_archives=sf.allow_archives,
                    archive_exts=sf.archive_exts if sf.archive_exts else gf.archive_exts,
                    min_size=sf.min_size if sf.min_size is not None else gf.min_size,
                    max_size=sf.max_size if sf.max_size is not None else gf.max_size,
                    only_after=sf.only_after if sf.only_after is not None else gf.only_after,
                    only_before=sf.only_before if sf.only_before is not None else gf.only_before,
                    include_patterns=sf.include_patterns if sf.include_patterns else gf.include_patterns,
                    exclude_patterns=sf.exclude_patterns if sf.exclude_patterns else gf.exclude_patterns,
                )
                composite_filter = build_filters(merged_filters)
            else:
                # Use global filters
                composite_filter = build_filters(config.global_filters)

        except ConfigError:
            raise
        except Exception as e:
            # Wrap exceptions with source context
            raise ConfigError(
                f"Failed to parse source {idx + 1}: {e}"
            )

        # --- Telegram resolution: skip this source on failure ---
        label = source_config.url or source_config.chat_id
        try:
            source_instance = await create_source(client, chat_id, topic_id)
        except Exception as e:
            logger.error(
                f"Source {idx + 1} ({label}) could not be resolved: {e} - "
                f"skipping this source. Remove or fix it in your configuration."
            )
            continue

        results.append((source_instance, composite_filter, source_config))

    return results


async def validate_source_access(
    sources_with_filters: list[tuple[BaseSource, CompositeFilter, SourceConfig]],
    client: Client
) -> list[tuple[BaseSource, CompositeFilter, SourceConfig]]:
    """
    Validate source accessibility at startup, keeping only usable sources.

    Attempts to get chat info for each source to ensure:
    - Chat exists and is accessible
    - User has permission to access chat
    - Chat ID is valid

    Inaccessible sources are skipped with a clear error log instead of
    aborting the whole run, so one dead source doesn't block the rest
    (issue #40).

    Args:
        sources_with_filters: (source, filter, source_config) tuples to validate
        client: Authenticated Pyrogram client

    Returns:
        The subset of tuples whose sources are accessible
    """
    accessible = []

    for idx, entry in enumerate(sources_with_filters):
        source = entry[0]
        try:
            # Try to get chat info
            await client.get_chat(source.chat_id)
        except Exception as e:
            error_msg = str(e).lower()

            # Detect specific error types and provide helpful messages
            if "peer_id_invalid" in error_msg or "peer id invalid" in error_msg:
                reason = "Invalid chat ID. Chat may not exist or you haven't interacted with it."
            elif "user_not_participant" in error_msg or "not a participant" in error_msg:
                reason = "You are not a member of this chat. Join the chat first."
            elif "chat_forbidden" in error_msg or "forbidden" in error_msg:
                reason = "Access forbidden. You may have been banned or removed."
            else:
                reason = f"Cannot access chat: {e}"

            logger.error(
                f"Source {idx + 1} (chat_id={source.chat_id}): {reason} "
                f"- skipping this source."
            )
            continue

        accessible.append(entry)

    return accessible
