# Configuration Reference

Complete reference for all configuration options.

## Configuration Methods

=== "Environment Variables (Recommended)"
    **Best for Docker deployments**

    - Easy to set in `docker-compose.yml`
    - Format: `TDL_SECTION_KEY` (uppercase, underscore-separated)

    ```yaml
    environment:
      - TDL_API_ID=12345678
      - TDL_DAEMON_ENABLED=true
    ```

=== "YAML Configuration File"
    **For running from source**

    - Read from `/app/config.yaml` (fixed path)
    - Keys match the field names below, nested the same way
    - Values can use `${VAR}` or `${VAR:-default}` to pull in environment variables

    ```yaml
    api_id: 12345678

    daemon:
      enabled: true
    ```

!!! warning "Environment variables or the file, not both"
    The two are not merged. If any `TDL_` variable is set, `/app/config.yaml` is ignored completely. The Docker image sets `TDL_DOWNLOAD_DIR`, `TDL_SESSION_DIR` and `TDL_DAEMON_HEALTH_FILE` itself, so inside the image the file is never read. Use environment variables with Docker.

## Environment Variable Format

Format: `TDL_SECTION_KEY` (uppercase, underscore-separated)

Examples:
- `TDL_API_ID` → api_id
- `TDL_DAEMON_ENABLED` → daemon.enabled
- `TDL_SOURCES_0_URL` → sources[0].url

## Core Settings

### Telegram API Credentials

`TDL_API_ID` and `TDL_API_HASH` are required.

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `TDL_API_ID` | integer | Yes | API ID from https://my.telegram.org/apps |
| `TDL_API_HASH` | string | Yes | API hash from https://my.telegram.org/apps |
| `TDL_PHONE_NUMBER` | string | No | Phone number with country code (e.g., +1234567890). If omitted, you are asked for it at first login |

=== "Environment Variables"

    ```yaml
    - TDL_API_ID=12345678
    - TDL_API_HASH=abcdef1234567890abcdef1234567890
    - TDL_PHONE_NUMBER=+1234567890
    ```

=== "config.yaml"

    ```yaml
    api_id: 12345678
    api_hash: "abcdef1234567890abcdef1234567890"
    phone_number: "+1234567890"
    ```

### Paths and Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_DOWNLOAD_DIR` | path | `/downloads` | Base directory for downloaded files |
| `TDL_FLAT_STRUCTURE` | boolean | `false` | Store all files in download dir without per-channel subfolders |
| `TDL_TRACK_DOWNLOADS` | boolean | `true` | Track downloaded files to prevent re-downloads after move/rename |

When `TDL_FLAT_STRUCTURE` is `false` (default), files are organized as `{download_dir}/{channel_name}/{filename}`. When `true`, all files go directly into `{download_dir}/{filename}`.

Channel and file names are sanitized before they touch the filesystem. Letters and digits in any script are kept (e.g. `中文文件.zip`, `Документ.txt`, `café.pdf`), along with `.`, `_` and `-`. Spaces, path separators, characters that are invalid on Windows (`: * ? " < > |`) and control characters are replaced with `_`. Leading dots and trailing dots/spaces are trimmed, and Windows reserved names such as `CON` or `NUL.txt` are prefixed with `_`.

When `TDL_TRACK_DOWNLOADS` is `true` (default), a persistent history of downloaded files is kept in the state database. This prevents re-downloading files that have been moved, renamed, or processed by external tools (e.g., media servers, Paperless-ngx, mergerfs). The tracking uses Telegram's `file_unique_id`, which is stable and unique per file content regardless of source. Set to `false` to disable and rely only on file-exists checks.

### Docker Environment

These are standard Docker environment variables, not prefixed with `TDL_`.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PUID` | integer | `1000` | User ID for file ownership ([arr-stack](https://docs.linuxserver.io/general/understanding-puid-and-pgid/) convention) |
| `PGID` | integer | `1000` | Group ID for file ownership |
| `TZ` | string | `UTC` | Container timezone (e.g., `Europe/Lisbon`) |

=== "Environment Variables"

    ```yaml
    - PUID=1000
    - PGID=1000
    - TZ=Europe/Lisbon
    - TDL_FLAT_STRUCTURE=true
    - TDL_TRACK_DOWNLOADS=true
    ```

=== "config.yaml"

    ```yaml
    flat_structure: true
    track_downloads: true
    # PUID, PGID, and TZ are Docker-only (not in config.yaml)
    ```

## Daemon Configuration

Controls continuous background operation.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_DAEMON_ENABLED` | boolean | `false` | Enable daemon mode |
| `TDL_DAEMON_CHECK_INTERVAL` | integer | `300` | Seconds between checks (60-86400) |
| `TDL_DAEMON_HEALTH_FILE` | path | `/app/health_status.txt` | Health check file path |
| `TDL_DAEMON_LOG_LEVEL` | string | unset | Log level (DEBUG/INFO/WARNING/ERROR). When unset, `TDL_VERBOSITY` decides (INFO by default) |

=== "Environment Variables"

    ```yaml
    - TDL_DAEMON_ENABLED=true
    - TDL_DAEMON_CHECK_INTERVAL=300  # Check every 5 minutes
    - TDL_DAEMON_LOG_LEVEL=INFO
    ```

=== "config.yaml"

    ```yaml
    daemon:
      enabled: true
      check_interval: 300  # Check every 5 minutes
      log_level: "INFO"
    ```

## Notification Configuration

Discord webhooks and generic HTTP POST notifications. Nothing is sent unless `TDL_NOTIFICATIONS_ENABLED=true` and at least one webhook URL is set.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_NOTIFICATIONS_ENABLED` | boolean | `false` | Enable notifications |
| `TDL_NOTIFICATIONS_DETAIL_LEVEL` | string | `summary` | Accepted values: minimal/summary/detailed. Not used yet: every notification has the same content |
| `TDL_NOTIFICATIONS_THROTTLE_SECONDS` | integer | `60` | Minimum seconds between notifications (10-3600) |
| `TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL` | URL | - | Discord webhook URL |
| `TDL_NOTIFICATIONS_DISCORD_USERNAME` | string | `Telegram Downloader` | Discord bot username |
| `TDL_NOTIFICATIONS_GENERIC_WEBHOOK_URL` | URL | - | Generic webhook URL (JSON POST) |

=== "Environment Variables"

    ```yaml
    - TDL_NOTIFICATIONS_ENABLED=true
    - TDL_NOTIFICATIONS_DETAIL_LEVEL=summary
    - TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123/abc
    ```

=== "config.yaml"

    ```yaml
    notifications:
      enabled: true
      detail_level: "summary"
      discord_webhook_url: "https://discord.com/api/webhooks/123/abc"
    ```

## Source Configuration

Configure download sources (channels, groups, forum topics, private chats).

### Source URL Format

| Source Type | URL Format | Example |
|-------------|------------|---------|
| Public channel | `https://t.me/username` | `https://t.me/example_channel` |
| Public group | `https://t.me/groupname` | `https://t.me/example_group` |
| Private channel or group | `https://t.me/c/CHAT_ID` | `https://t.me/c/1234567890` |
| Forum topic | `https://t.me/c/CHAT_ID/TOPIC_ID` | `https://t.me/c/1234567890/123` |
| Private chat | `https://t.me/username` | `https://t.me/friend_username` |
| Saved messages | `https://t.me/me` | `https://t.me/me` |

In a `t.me/c/` link, a second number is read as a forum topic ID, so leave message IDs off the link.

### Source Settings

Format: `TDL_SOURCES_N_KEY` where N is the source index (0, 1, 2, ...)

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `TDL_SOURCES_N_URL` | URL | Yes* | Source URL (see formats above) |
| `TDL_SOURCES_N_CHAT_ID` | integer | Yes* | Numeric chat ID instead of a URL (e.g., `-1001234567890`) |
| `TDL_SOURCES_N_TOPIC_ID` | integer | No | Forum topic ID, used with `TDL_SOURCES_N_CHAT_ID` |
| `TDL_SOURCES_N_NAME` | string | No | Custom folder name (auto-generated if omitted) |

*Each source needs either a URL or a chat ID.

=== "Environment Variables"

    ```yaml
    - TDL_SOURCES_0_URL=https://t.me/channel1
    - TDL_SOURCES_0_NAME=Channel One
    - TDL_SOURCES_1_URL=https://t.me/c/1234567890/123
    - TDL_SOURCES_1_NAME=Forum Topic
    ```

=== "config.yaml"

    ```yaml
    sources:
      - url: "https://t.me/channel1"
        name: "Channel One"
      - url: "https://t.me/c/1234567890/123"
        name: "Forum Topic"
    ```

### Filter Configuration

Per-source filters override global defaults. A per-source value replaces the global one; a list, size or date left empty falls back to the global value.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_SOURCES_N_FILTERS_EXTENSIONS` | list | global value | File extensions (comma-separated, with dots) |
| `TDL_SOURCES_N_FILTERS_ALLOW_ARCHIVES` | boolean | `false` | Also download archives. Does not fall back to the global value |
| `TDL_SOURCES_N_FILTERS_ARCHIVE_EXTS` | list | global value | Archive extensions used when archives are allowed |
| `TDL_SOURCES_N_FILTERS_MIN_SIZE` | string | - | Minimum file size (e.g., "100KB", "5MB") |
| `TDL_SOURCES_N_FILTERS_MAX_SIZE` | string | - | Maximum file size (e.g., "2GB") |
| `TDL_SOURCES_N_FILTERS_ONLY_AFTER` | date | - | Oldest message date to download, inclusive (ISO format: YYYY-MM-DD) |
| `TDL_SOURCES_N_FILTERS_ONLY_BEFORE` | date | - | Newest message date to download, inclusive |
| `TDL_SOURCES_N_FILTERS_INCLUDE_PATTERNS` | list | - | Only download files whose name matches one of these |
| `TDL_SOURCES_N_FILTERS_EXCLUDE_PATTERNS` | list | - | Skip files whose name matches one of these (checked first) |

=== "Environment Variables"

    ```yaml
    - TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi
    - TDL_SOURCES_0_FILTERS_MIN_SIZE=100KB
    - TDL_SOURCES_0_FILTERS_MAX_SIZE=500MB
    - TDL_SOURCES_0_FILTERS_ONLY_AFTER=2026-01-01
    ```

=== "config.yaml"

    ```yaml
    sources:
      - url: "https://t.me/channel1"
        filters:
          extensions: [".pdf", ".epub", ".mobi"]
          min_size: "100KB"
          max_size: "500MB"
          only_after: "2026-01-01"
          include_patterns: ["*ebook*", "*book*"]
    ```

!!! bug "Known issue: list filters other than extensions"
    `INCLUDE_PATTERNS`, `EXCLUDE_PATTERNS` and `ARCHIVE_EXTS` are currently rejected when set through environment variables (the value is not split into a list, so startup fails with "Input should be a valid list"). Until that is fixed they only work from `config.yaml`.

**Size format:** Number + unit: B, KB, MB, GB or TB, 1024-based (e.g., `500KB`, `1.5GB`). A bare number without a unit is rejected at startup.
**Date format:** `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`, read as UTC. A date alone means midnight at the start of that day, so `ONLY_BEFORE=2026-01-31` stops at the start of 31 January; use `2026-01-31T23:59:59` to include the whole day.
**Pattern format:** Wildcards (`*` = any characters, `?` = single character), or a regex when the pattern starts with `^`, ends with `$`, or contains any of `( ) [ ] { } | +`. Patterns are matched against the file name.

## Global Filter Defaults

Applied to all sources unless overridden.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_GLOBAL_FILTERS_EXTENSIONS` | list | `.pdf,.epub,.mobi` | Default file extensions |
| `TDL_GLOBAL_FILTERS_MIN_SIZE` | string | - | Default minimum size |
| `TDL_GLOBAL_FILTERS_MAX_SIZE` | string | - | Default maximum size |
| `TDL_GLOBAL_FILTERS_ALLOW_ARCHIVES` | boolean | `false` | Also download archives |
| `TDL_GLOBAL_FILTERS_ARCHIVE_EXTS` | list | `.zip,.rar,.7z` | Archive extensions (see the known issue above) |

Global include and exclude patterns can only be set in `config.yaml` (`global_filters.include_patterns` and `global_filters.exclude_patterns`).

## Retry Configuration

How a failed download is retried within one check.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_MAX_RETRIES` | integer | `2` | Attempts per file within one check, counting the first try (2 = one try and one retry) |
| `TDL_BASE_DELAY` | integer | `2` | Seconds before the first retry, doubled for each later retry (minimum 1) |
| `TDL_MAX_DELAY` | integer | `60` | Upper limit for the delay between retries, in seconds (minimum 1) |
| `TDL_MAX_DOWNLOAD_ATTEMPTS` | integer | `5` | Checks a file is retried in before it is given up on (minimum 1) |

Example:
```yaml
- TDL_MAX_RETRIES=3
- TDL_BASE_DELAY=2
- TDL_MAX_DELAY=120
```

## Other Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_SESSION_DIR` | path | `/app/.sessions` | Telegram session and state database. Mount a volume here |
| `TDL_MAX_CONCURRENT_DOWNLOADS` | integer | `1` | Downloads running at the same time (1-10) |
| `TDL_SCHEDULE_ACTIVE_HOURS` | string | unset | Only run checks inside these windows, e.g. `02:00-08:00,22:00-23:59` (local time via `TZ`) |
| `TDL_MAX_DOWNLOAD_SPEED` | string | unset | Cap on total download speed, e.g. `500KB` or `5MB` |
| `TDL_POST_DOWNLOAD_HOOK` | string | unset | Command run after each successful download (see the README for placeholders) |
| `TDL_POST_DOWNLOAD_HOOK_TIMEOUT` | integer | `300` | Seconds before the hook is stopped (1-86400) |
| `TDL_VERBOSITY` | string | `normal` | `quiet` (WARNING), `normal` (INFO) or `verbose` (DEBUG) |
| `TDL_LOG_FILE` | path | unset | Also write logs to this file |
| `TDL_TEST_MODE` | boolean | `false` | Connect to Telegram's test servers (needs a test account) |

## config.yaml Example

Alternative to environment variables when running from source:

```yaml
api_id: 12345678
api_hash: "abcdef1234567890abcdef1234567890"
phone_number: "+1234567890"
download_dir: "/downloads"
flat_structure: true
track_downloads: true

daemon:
  enabled: true
  check_interval: 300
  health_file: "/app/health_status.txt"

notifications:
  enabled: true
  detail_level: "summary"
  discord_webhook_url: "https://discord.com/api/webhooks/123/abc"

sources:
  - url: "https://t.me/channel1"
    name: "Channel One"
    filters:
      extensions: [".pdf", ".epub", ".mobi"]
      min_size: "100KB"
      max_size: "500MB"
  - url: "https://t.me/c/1234567890/123"
    name: "Forum Topic"
```

**Note:** This file is ignored if any `TDL_` environment variable is set.
