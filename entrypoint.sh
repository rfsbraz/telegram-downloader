#!/bin/sh
set -e

# Support PUID/PGID environment variables (arr-stack convention)
# Defaults to 1000:1000 if not set
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Update appuser uid/gid if they differ from defaults
if [ "$(id -u appuser)" != "$PUID" ] || [ "$(id -g appuser)" != "$PGID" ]; then
    groupmod -o -g "$PGID" appuser 2>/dev/null || true
    usermod -o -u "$PUID" appuser 2>/dev/null || true
    chown -R appuser:appuser /app
fi

# Ensure bind-mounted directories are writable by appuser
for dir in /downloads /app/.sessions; do
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
    fi
done

exec gosu appuser "$@"
