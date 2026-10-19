"""
Filename sanitization and path validation for secure file operations.

Protects against:
- Path traversal attacks (../../etc/passwd)
- Null byte injection (file\x00.exe)
- Hidden files (leading dots)
- Invalid filesystem characters
- Unicode normalization attacks
"""
import unicodedata
from pathlib import Path

# Punctuation allowed in addition to Unicode letters, digits and combining marks
_ALLOWED_PUNCTUATION = frozenset("._-")

# Device names reserved by Windows, regardless of case or extension
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _is_allowed_char(char: str) -> bool:
    """Return True for Unicode letters/digits, combining marks and ``._-``."""
    if char in _ALLOWED_PUNCTUATION or char.isalnum():
        return True
    # Combining marks (Mn/Mc/Me) are needed by scripts such as Devanagari
    return unicodedata.category(char).startswith("M")


def _replace_disallowed(text: str) -> str:
    """Replace every character that is not explicitly allowed with ``_``."""
    return "".join(char if _is_allowed_char(char) else "_" for char in text)


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename using whitelist approach for maximum security.

    Only allows Unicode letters, digits and combining marks plus ``._-``
    (so non-Latin names such as ``中文文件.zip`` or ``Документ.txt`` are kept).
    Everything else - path separators, ``: * ? " < > |``, whitespace, control
    and invisible format characters - is replaced with an underscore.

    - Normalizes to Unicode NFC
    - Strips leading/trailing whitespace, leading dots and trailing dots
    - Replaces path separators and null bytes with underscore
    - Prefixes Windows reserved device names (CON, NUL, COM1, ...) with "_"
    - Preserves file extension if present
    - Truncates to max_length bytes
    - Returns "unnamed_file" if result is empty

    Examples:
        >>> sanitize_filename("../../etc/passwd")
        '_.._etc_passwd'
        >>> sanitize_filename("file\x00.exe")
        'file_.exe'
        >>> sanitize_filename("book (2023).epub")
        'book__2023_.epub'
        >>> sanitize_filename(".hidden_file.txt")
        'hidden_file.txt'
        >>> sanitize_filename("../../../../etc/passwd.epub")
        '_.._.._.._etc_passwd.epub'
        >>> sanitize_filename("中文文件.zip")
        '中文文件.zip'
        >>> sanitize_filename("con.txt")
        '_con.txt'

    Args:
        filename: Original filename from Telegram or user input
        max_length: Maximum length in bytes (filesystem limit is 255)

    Returns:
        Sanitized filename safe for filesystem operations
    """
    if not filename:
        return "unnamed_file"

    # Normalize so visually identical names map to the same byte sequence
    name = unicodedata.normalize("NFC", filename)

    # Strip leading/trailing whitespace
    name = name.strip()

    # Strip leading dots (prevents hidden files)
    while name.startswith("."):
        name = name[1:]

    # Strip trailing dots and whitespace (invalid on Windows)
    name = name.rstrip(". ")

    # Separate extension if present (preserve it)
    extension = ""
    if "." in name:
        parts = name.rsplit(".", 1)
        if len(parts) == 2:
            name, extension = parts
            extension = "." + extension

    # Whitelist: only allow Unicode letters/digits/marks, dots, underscores,
    # hyphens. Path separators, null bytes and other control characters are
    # replaced with underscores.
    name = _replace_disallowed(name)

    # Also sanitize the extension
    extension = _replace_disallowed(extension)

    # Avoid Windows reserved device names (e.g. "CON", "nul.txt", "COM1.log")
    if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        name = "_" + name

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
