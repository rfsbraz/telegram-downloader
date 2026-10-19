"""Time-window scheduling for download checks.

Parses active-hours specifications like "02:00-08:00" or
"02:00-08:00,22:00-23:59" (local time via TZ) and answers whether the
current time falls inside any configured window. Windows may cross
midnight (e.g. "23:00-06:00").
"""

import re
from datetime import datetime, time

# One window: HH:MM-HH:MM
_WINDOW_RE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def parse_active_hours(spec: str) -> list[tuple[time, time]]:
    """Parse an active-hours spec into a list of (start, end) windows.

    Args:
        spec: Comma-separated windows in 24h format, e.g.
            "02:00-08:00" or "02:00-08:00,22:00-23:59".
            Windows may cross midnight ("23:00-06:00").

    Returns:
        List of (start, end) datetime.time tuples (empty for blank spec)

    Raises:
        ValueError: If any window has an invalid format or out-of-range values
    """
    windows = []

    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue

        match = _WINDOW_RE.match(part)
        if not match:
            raise ValueError(
                f"Invalid active hours window: '{part}'. "
                f"Expected 24h format like '02:00-08:00'."
            )

        h1, m1, h2, m2 = (int(g) for g in match.groups())
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
            raise ValueError(
                f"Invalid active hours window: '{part}'. "
                f"Hours must be 00-23 and minutes 00-59."
            )

        windows.append((time(h1, m1), time(h2, m2)))

    return windows


def is_within_active_hours(
    windows: list[tuple[time, time]],
    now: time | None = None,
) -> bool:
    """Check whether `now` falls inside any active window.

    Args:
        windows: Parsed (start, end) windows; empty means no restriction
        now: Time to test (defaults to current local time)

    Returns:
        True if inside any window or no windows are configured
    """
    if not windows:
        return True

    if now is None:
        now = datetime.now().time()

    for start, end in windows:
        if start <= end:
            # Normal window within a single day
            if start <= now <= end:
                return True
        else:
            # Window crosses midnight (e.g. 23:00-06:00)
            if now >= start or now <= end:
                return True

    return False
