#!/usr/bin/env python3
"""
Health check script for Docker HEALTHCHECK.

Reads health status file and returns appropriate exit code:
- Exit 0: Healthy (status=healthy or starting)
- Exit 1: Unhealthy (status=error or file missing/stale)

Health file format:
Line 1: status (starting|healthy|error|stopped)
Line 2: ISO timestamp of last update
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

HEALTH_FILE = Path(os.getenv("TDL_DAEMON_HEALTH_FILE", "/app/health_status.txt"))
MAX_AGE_SECONDS = 600  # 10 minutes

def main():
    # Check if health file exists
    if not HEALTH_FILE.exists():
        print("Health file not found", file=sys.stderr)
        sys.exit(1)

    try:
        # Read health status
        lines = HEALTH_FILE.read_text().strip().split('\n')
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

        # Check if status is stale
        age = datetime.now() - timestamp
        if age.total_seconds() > MAX_AGE_SECONDS:
            print(f"Health status stale ({age.total_seconds():.0f}s old)", file=sys.stderr)
            sys.exit(1)

        # Check status value
        if status in ("healthy", "starting"):
            print(f"Status: {status}")
            sys.exit(0)
        elif status == "error":
            print("Status: error", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Unknown status: {status}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Health check failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
