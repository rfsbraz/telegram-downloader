"""Bandwidth rate limiting for downloads.

Token-bucket limiter shared by all concurrent downloads. Pyrogram
reports cumulative progress per file; the download progress callback
feeds byte deltas into the limiter, which sleeps just long enough to
keep the aggregate download rate at or below the configured cap.
"""

import asyncio
import re
import time as time_module

# Rate units (binary multiples, matching the size filters)
_RATE_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
}

_RATE_RE = re.compile(r"^([\d.]+)\s*([A-Z]+)?(?:/S)?$")


def parse_rate(rate_str: str) -> int:
    """Parse a human-readable rate string to bytes per second.

    Supports "500KB", "5MB", "1.5MB", optionally suffixed with "/s".

    Args:
        rate_str: Rate string with unit suffix

    Returns:
        Rate in bytes per second

    Raises:
        ValueError: If the format is invalid or the rate is not positive
    """
    match = _RATE_RE.match(rate_str.strip().upper())
    if not match:
        raise ValueError(
            f"Invalid download speed: '{rate_str}'. "
            f"Expected format: '500KB', '5MB', etc."
        )

    number_str, unit = match.groups()
    unit = unit or "B"
    if unit not in _RATE_UNITS:
        raise ValueError(
            f"Unknown speed unit: '{unit}'. "
            f"Supported units: {', '.join(_RATE_UNITS)}"
        )

    rate = float(number_str) * _RATE_UNITS[unit]
    if rate <= 0:
        raise ValueError(f"Download speed must be positive: '{rate_str}'")
    return int(rate)


class RateLimiter:
    """Async token-bucket rate limiter shared across concurrent downloads.

    Tokens (bytes) accrue at `rate` per second up to a burst of one
    second's worth. Consumers call `throttle(nbytes)` after receiving
    a chunk; when the bucket runs dry the caller sleeps just long
    enough for the average rate to converge to the cap.
    """

    def __init__(self, rate: int):
        """
        Args:
            rate: Maximum aggregate rate in bytes per second
        """
        self.rate = rate
        self._allowance = float(rate)  # start with one second of burst
        self._last = time_module.monotonic()
        self._lock = asyncio.Lock()

    async def throttle(self, nbytes: int) -> None:
        """Account for `nbytes` transferred; sleep if over the cap."""
        if nbytes <= 0:
            return

        async with self._lock:
            now = time_module.monotonic()
            self._allowance = min(
                float(self.rate),
                self._allowance + (now - self._last) * self.rate,
            )
            self._last = now
            self._allowance -= nbytes
            # Deficit determines how long to wait for the bucket to refill
            wait = -self._allowance / self.rate if self._allowance < 0 else 0.0

        if wait > 0:
            await asyncio.sleep(wait)
