#!/usr/bin/env python3
"""
Health check script for Docker HEALTHCHECK.

Reads health status file and returns appropriate exit code:
- Exit 0: Healthy (status=healthy or starting)
- Exit 1: Unhealthy (status=error or file missing/stale)

Health file format:
Line 1: status (starting|healthy|error|stopped)
Line 2: ISO timestamp of last update
Line 3: optional reason (e.g. why status is error)
Line 4: optional versioned JSON progress metadata (new daemons)
"""
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HEALTH_FILE = Path(os.getenv("TDL_DAEMON_HEALTH_FILE", "/app/health_status.txt"))
MAX_AGE_SECONDS = int(os.getenv("TDL_DAEMON_HEALTH_MAX_AGE", "600"))


def main():
    # Check if health file exists
    if not HEALTH_FILE.exists():
        print("Health file not found", file=sys.stderr)
        sys.exit(1)

    try:
        # Read health status
        lines = HEALTH_FILE.read_text().strip().split("\n")
        if len(lines) < 2:
            print("Invalid health file format", file=sys.stderr)
            sys.exit(1)

        status = lines[0]
        timestamp_str = lines[1]

        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            print(f"Invalid timestamp: {timestamp_str}", file=sys.stderr)
            sys.exit(1)

        # Older daemons wrote naive timestamps, which were always UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Check if status is stale
        age = datetime.now(timezone.utc) - timestamp
        if age.total_seconds() > MAX_AGE_SECONDS:
            print(
                f"Health status stale ({age.total_seconds():.0f}s old)", file=sys.stderr
            )
            sys.exit(1)

        # Check status value
        if status in ("healthy", "starting"):
            if len(lines) > 3:
                metadata = json.loads(lines[3])
                if metadata["version"] != 1:
                    raise ValueError("Unsupported health metadata version")
                limit = metadata["max_check_age"]
                if limit is not None:
                    if (
                        isinstance(limit, bool)
                        or not math.isfinite(limit)
                        or limit <= 0
                    ):
                        raise ValueError("Invalid health check age limit")
                    # A scheduled skip is valid loop progress, but a heartbeat
                    # must never refresh this deadline for an unfinished check.
                    progress = datetime.fromisoformat(
                        metadata["last_progress"] or metadata["started_at"]
                    )
                    if progress.tzinfo is None:
                        progress = progress.replace(tzinfo=timezone.utc)
                    check_age = (datetime.now(timezone.utc) - progress).total_seconds()
                    if check_age > limit:
                        print(
                            f"Last check progress stale ({check_age:.0f}s old)",
                            file=sys.stderr,
                        )
                        sys.exit(1)
            print(f"Status: {status}")
            sys.exit(0)
        elif status == "error":
            reason = f" ({lines[2]})" if len(lines) > 2 else ""
            print(f"Status: error{reason}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Unknown status: {status}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Health check failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
