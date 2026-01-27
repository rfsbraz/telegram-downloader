#!/bin/sh
set -e

# Ensure bind-mounted directories are writable by appuser (uid 1000)
# Docker creates bind mounts as root, but the app runs as appuser
for dir in /downloads /app/.sessions; do
    if [ -d "$dir" ] && [ ! -w "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
    fi
done

exec gosu appuser "$@"
