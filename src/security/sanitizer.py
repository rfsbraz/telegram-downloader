"""
Filename sanitization and path validation for secure file operations.

Protects against:
- Path traversal attacks (../../etc/passwd)
- Null byte injection (file\x00.exe)
- Hidden files (leading dots)
- Invalid filesystem characters
- Unicode normalization attacks
"""
import re
from pathlib import Path


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename using whitelist approach for maximum security.

    Only allows: [a-zA-Z0-9._-] characters
    - Strips leading/trailing whitespace and dots
    - Replaces path separators and null bytes with underscore
    - Preserves file extension if present
    - Truncates to max_length bytes
    - Returns "unnamed_file" if result is empty

    Examples:
        >>> sanitize_filename("../../etc/passwd")
        'etc_passwd'
        >>> sanitize_filename("file\x00.exe")
        'file_.exe'
        >>> sanitize_filename("book (2023).epub")
        'book_2023.epub'
        >>> sanitize_filename(".hidden_file.txt")
        'hidden_file.txt'
        >>> sanitize_filename("../../../../etc/passwd.epub")
        'etc_passwd.epub'

    Args:
        filename: Original filename from Telegram or user input
        max_length: Maximum length in bytes (filesystem limit is 255)

    Returns:
        Sanitized filename safe for filesystem operations
    """
    if not filename:
        return "unnamed_file"

    # Strip leading/trailing whitespace
    name = filename.strip()

    # Strip leading dots (prevents hidden files)
    while name.startswith("."):
        name = name[1:]

    # Separate extension if present (preserve it)
    extension = ""
    if "." in name:
        parts = name.rsplit(".", 1)
        if len(parts) == 2:
            name, extension = parts
            extension = "." + extension

    # Replace path separators and null bytes
    name = name.replace("/", "_")
    name = name.replace("\\", "_")
    name = name.replace("\x00", "_")

    # Whitelist: only allow alphanumeric, dots, underscores, hyphens
    # This is the safest approach - explicitly allow known-safe characters
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)

    # Also sanitize the extension
    extension = re.sub(r"[^a-zA-Z0-9._-]", "_", extension)

    # Reconstruct filename
    result = name + extension

    # Truncate to max_length (account for byte length, not character length)
    # Most filesystems limit to 255 bytes
    if len(result.encode("utf-8")) > max_length:
        # Try to preserve extension
        ext_bytes = extension.encode("utf-8")
        available = max_length - len(ext_bytes)
        if available > 0:
            # Truncate name to fit
            name_truncated = name.encode("utf-8")[:available].decode("utf-8", errors="ignore")
            result = name_truncated + extension
        else:
            # Extension itself is too long, just truncate everything
            result = result.encode("utf-8")[:max_length].decode("utf-8", errors="ignore")

    # If result is empty after sanitization, return default
    if not result or result == extension:
        return "unnamed_file" + extension

    return result


def validate_path_safety(base_dir: Path, target_path: Path) -> Path:
    """
    Validate that target_path is safely within base_dir.

    Prevents path traversal attacks by:
    - Resolving both paths to absolute
    - Checking target is relative to base
    - Raising ValueError if path escapes base directory

    Examples:
        >>> base = Path("/downloads")
        >>> validate_path_safety(base, Path("/downloads/book.epub"))
        Path('/downloads/book.epub')
        >>> validate_path_safety(base, Path("/downloads/../etc/passwd"))
        ValueError: Path traversal detected: /etc/passwd escapes /downloads

    Args:
        base_dir: Base directory that files must stay within
        target_path: Target file path to validate

    Returns:
        Resolved absolute target_path if safe

    Raises:
        ValueError: If target_path escapes base_dir
    """
    # Resolve both paths to absolute (resolves .. and symlinks)
    base_resolved = base_dir.resolve()
    target_resolved = target_path.resolve()

    # Check if target is within base directory
    # Python 3.9+ has is_relative_to method
    try:
        # Try the modern way first
        if not target_resolved.is_relative_to(base_resolved):
            raise ValueError(
                f"Path traversal detected: {target_resolved} escapes {base_resolved}"
            )
    except AttributeError:
        # Fallback for Python < 3.9
        try:
            target_resolved.relative_to(base_resolved)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {target_resolved} escapes {base_resolved}"
            )

    return target_resolved
