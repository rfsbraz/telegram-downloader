"""
Destination path construction with per-source folder structure.

Implements ORG-01: Creates folder per source using source name/cursor key.
Implements ORG-02: Validates path safety using existing security primitives.
"""

from pathlib import Path

from src.config.schema import SourceConfig
from src.security.sanitizer import sanitize_filename, validate_path_safety
from src.sources.base import BaseSource


async def build_destination_path(
    base_dir: Path,
    source: BaseSource,
    filename: str,
    source_config: SourceConfig,
) -> Path:
    """
    Build destination path with per-source folder structure.

    Creates folder structure: {base_dir}/{source_folder}/{filename}

    Folder name priority:
    1. source_config.name (user-provided display name)
    2. source.get_display_name() (Telegram chat/topic name)
    3. Fallback to cursor key if sanitization results in empty string

    Security measures:
    - Sanitizes folder and filename using whitelist [a-zA-Z0-9._-]
    - Validates final path doesn't escape base_dir
    - Creates folder with safe permissions (parents=True, exist_ok=True)

    Args:
        base_dir: Base download directory
        source: Source instance for display name and cursor key
        filename: Original filename from Telegram message
        source_config: Source configuration with optional name override

    Returns:
        Validated absolute path ready for download

    Raises:
        ValueError: If path validation fails (traversal attempt detected)

    Example:
        >>> path = await build_destination_path(
        ...     Path("/downloads"),
        ...     forum_topic_source,
        ...     "book.epub",
        ...     SourceConfig(name="Book Club")
        ... )
        >>> path
        Path('/downloads/Book_Club/book.epub')
    """
    # Get folder name: use config name, fallback to display name
    if source_config.name:
        folder_name = source_config.name
    else:
        folder_name = await source.get_display_name()

    # Sanitize folder name using whitelist approach
    safe_folder = sanitize_filename(folder_name)

    # Handle edge case: folder name becomes empty after sanitization
    # Use cursor key as fallback (e.g., "source_100123456_5")
    if not safe_folder or safe_folder == "unnamed_file":
        cursor_key = source.get_cursor_key()
        # Sanitize cursor key: replace ':' with '_', remove '-'
        sanitized_cursor = cursor_key.replace(":", "_").replace("-", "")
        safe_folder = f"source_{sanitized_cursor}"

    # Sanitize filename
    safe_filename = sanitize_filename(filename)

    # Build path: {base_dir}/{safe_folder}/{safe_filename}
    dest_path = base_dir / safe_folder / safe_filename

    # Validate path safety (defense in depth)
    validated_path = validate_path_safety(base_dir, dest_path)

    # Create folder if it doesn't exist (idempotent)
    validated_path.parent.mkdir(parents=True, exist_ok=True)

    return validated_path
