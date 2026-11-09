"""Free space checks for the download volume (issue #61)."""

import shutil
from pathlib import Path

from src.config.source_parser import parse_size


def free_bytes(path: Path) -> int:
    """Free bytes on the volume holding path, or its nearest existing parent."""
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path).free


def reserve_bytes(cfg) -> int:
    """Bytes to keep free on the download volume. 0 disables the check."""
    value = (cfg.min_free_space or "").strip()
    return 0 if is_off(value) else parse_size(value)


def is_off(value: str) -> bool:
    """True for an empty value or a plain 0, the documented off switch (parse_size needs a unit)."""
    return value.strip() in ("", "0")


def written_bytes(path: Path) -> int:
    """Bytes a download has written to its partial file so far.

    The client streams into "<path>.temp" and renames it to path when the transfer
    ends, so both are counted. A missing file (not started, or removed for a retry)
    counts as 0.
    """
    total = 0
    for candidate in (path, path.with_name(path.name + ".temp")):
        try:
            total += candidate.stat().st_size
        except FileNotFoundError:
            pass
    return total
