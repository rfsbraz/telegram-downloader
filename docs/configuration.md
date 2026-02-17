# Configuration Reference

Complete reference for all configuration options.

## Configuration Methods

=== "Environment Variables (Recommended)"
    **Best for Docker deployments**

    - Easy to set in `docker-compose.yml`
    - Override TOML configuration
    - Format: `TDL_SECTION_KEY` (uppercase, underscore-separated)

    ```yaml
    environment:
      - TDL_API_ID=12345678
      - TDL_DAEMON_ENABLED=true
    ```

=== "TOML Configuration File"
    **Best for standalone Python execution**

    - Create `config.toml` in project root
    - Cleaner for complex configurations
    - Environment variables override TOML values

    ```toml
    api_id = 12345678

    [daemon]
    enabled = true
    ```

!!! tip "Priority Order"
    Environment variables **always override** config.toml values. Use environment variables for secrets and deployment-specific settings.

## Environment Variable Format

Format: `TDL_SECTION_KEY` (uppercase, underscore-separated)

Examples:
- `TDL_API_ID` → api_id
- `TDL_DAEMON_ENABLED` → daemon.enabled
- `TDL_SOURCES_0_URL` → sources[0].url

## Core Settings

### Telegram API Credentials

**Required for all operations.**

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `TDL_API_ID` | integer | Yes | API ID from https://my.telegram.org/apps |
| `TDL_API_HASH` | string | Yes | API hash from https://my.telegram.org/apps |
| `TDL_PHONE_NUMBER` | string | Yes | Phone number with country code (e.g., +1234567890) |

=== "Environment Variables"

    ```yaml
    - TDL_API_ID=12345678
    - TDL_API_HASH=abcdef1234567890abcdef1234567890
    - TDL_PHONE_NUMBER=+1234567890
    ```

=== "config.toml"

    ```toml
    api_id = 12345678
    api_hash = "abcdef1234567890abcdef1234567890"
    phone_number = "+1234567890"
    ```

### Paths and Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_DOWNLOAD_DIR` | path | `/downloads` | Base directory for downloaded files |
| `TDL_FLAT_STRUCTURE` | boolean | `false` | Store all files in download dir without per-channel subfolders |
| `TDL_TRACK_DOWNLOADS` | boolean | `true` | Track downloaded files to prevent re-downloads after move/rename |

When `TDL_FLAT_STRUCTURE` is `false` (default), files are organized as `{download_dir}/{channel_name}/{filename}`. When `true`, all files go directly into `{download_dir}/{filename}`.

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

=== "config.toml"

    ```toml
    flat_structure = true
    track_downloads = true
    # PUID, PGID, and TZ are Docker-only (not in config.toml)
    ```

## Daemon Configuration

Controls continuous background operation.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_DAEMON_ENABLED` | boolean | `false` | Enable daemon mode |
| `TDL_DAEMON_CHECK_INTERVAL` | integer | `300` | Seconds between checks (60-86400) |
| `TDL_DAEMON_HEALTH_FILE` | path | `/app/health_status.txt` | Health check file path |
| `TDL_DAEMON_LOG_LEVEL` | string | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |

=== "Environment Variables"

    ```yaml
    - TDL_DAEMON_ENABLED=true
    - TDL_DAEMON_CHECK_INTERVAL=300  # Check every 5 minutes
    - TDL_DAEMON_LOG_LEVEL=INFO
    ```

=== "config.toml"

    ```toml
    [daemon]
    enabled = true
    check_interval = 300  # Check every 5 minutes
    log_level = "INFO"
    ```

## Notification Configuration

Discord webhooks and generic HTTP POST notifications.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_NOTIFICATIONS_ENABLED` | boolean | `false` | Enable notifications |
| `TDL_NOTIFICATIONS_DETAIL_LEVEL` | string | `summary` | Detail level: minimal/summary/detailed |
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

=== "config.toml"

    ```toml
    [notifications]
    enabled = true
    detail_level = "summary"
    discord_webhook_url = "https://discord.com/api/webhooks/123/abc"
    ```

**Detail levels:**
- `minimal`: Status only (success/failure)
- `summary`: Status + file counts + error types (default)
- `detailed`: Includes file names, timestamps, stack traces

## Source Configuration

Configure download sources (channels, groups, forum topics, private chats).

### Source URL Format

| Source Type | URL Format | Example |
|-------------|------------|---------|
| Public channel | `https://t.me/username` | `https://t.me/example_channel` |
| Public group | `https://t.me/groupname` | `https://t.me/example_group` |
| Private channel | `https://t.me/c/CHAT_ID/MSG_ID` | `https://t.me/c/1234567890/1` |
| Forum topic | `https://t.me/c/CHAT_ID/TOPIC_ID` | `https://t.me/c/1234567890/123` |
| Private chat | `https://t.me/username` | `https://t.me/friend_username` |
| Saved messages | `https://t.me/me` | `https://t.me/me` |

### Source Settings

Format: `TDL_SOURCES_N_KEY` where N is the source index (0, 1, 2, ...)

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `TDL_SOURCES_N_URL` | URL | Yes | Source URL (see formats above) |
| `TDL_SOURCES_N_NAME` | string | No | Custom folder name (auto-generated if omitted) |

=== "Environment Variables"

    ```yaml
    - TDL_SOURCES_0_URL=https://t.me/channel1
    - TDL_SOURCES_0_NAME=Channel One
    - TDL_SOURCES_1_URL=https://t.me/c/1234567890/123
    - TDL_SOURCES_1_NAME=Forum Topic
    ```

=== "config.toml"

    ```toml
    [[sources]]
    url = "https://t.me/channel1"
    name = "Channel One"

    [[sources]]
    url = "https://t.me/c/1234567890/123"
    name = "Forum Topic"
    ```

### Filter Configuration

Per-source filters override global defaults.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_SOURCES_N_FILTERS_EXTENSIONS` | list | `.pdf,.epub,.mobi` | File extensions (comma-separated, with dots) |
| `TDL_SOURCES_N_FILTERS_MIN_SIZE` | string | - | Minimum file size (e.g., "100KB", "5MB") |
| `TDL_SOURCES_N_FILTERS_MAX_SIZE` | string | - | Maximum file size (e.g., "2GB") |
| `TDL_SOURCES_N_FILTERS_MIN_DATE` | date | - | Minimum message date (ISO format: YYYY-MM-DD) |
| `TDL_SOURCES_N_FILTERS_MAX_DATE` | date | - | Maximum message date |
| `TDL_SOURCES_N_FILTERS_PATTERNS` | list | - | Filename patterns (comma-separated) |

=== "Environment Variables"

    ```yaml
    - TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi
    - TDL_SOURCES_0_FILTERS_MIN_SIZE=100KB
    - TDL_SOURCES_0_FILTERS_MAX_SIZE=500MB
    - TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01
    - TDL_SOURCES_0_FILTERS_PATTERNS=*ebook*,*book*
    ```

=== "config.toml"

    ```toml
    [[sources]]
    url = "https://t.me/channel1"

    [sources.filters]
    extensions = [".pdf", ".epub", ".mobi"]
    min_size = "100KB"
    max_size = "500MB"
    min_date = "2026-01-01"
    patterns = ["*ebook*", "*book*"]
    ```

**Size format:** Number + unit (KB, MB, GB) or raw bytes
**Pattern format:** Wildcards (* = any characters, ? = single character) or regex (auto-detected)

## Global Filter Defaults

Applied to all sources unless overridden.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_GLOBAL_FILTERS_EXTENSIONS` | list | `.pdf,.epub,.mobi` | Default file extensions |
| `TDL_GLOBAL_FILTERS_MIN_SIZE` | string | - | Default minimum size |
| `TDL_GLOBAL_FILTERS_MAX_SIZE` | string | - | Default maximum size |

## Retry Configuration

Error handling and retry behavior.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TDL_RETRY_MAX_RETRIES` | integer | `2` | Maximum retry attempts |
| `TDL_RETRY_BASE_DELAY` | integer | `2` | Base delay in seconds |
| `TDL_RETRY_MAX_DELAY` | integer | `60` | Maximum delay in seconds |

Example:
```yaml
- TDL_RETRY_MAX_RETRIES=3
- TDL_RETRY_BASE_DELAY=2
- TDL_RETRY_MAX_DELAY=120
```

## config.toml Example

Alternative to environment variables:

```toml
api_id = 12345678
api_hash = "abcdef1234567890abcdef1234567890"
phone_number = "+1234567890"
download_dir = "/downloads"
flat_structure = true
track_downloads = true

[daemon]
enabled = true
check_interval = 300
health_file = "/app/health_status.txt"

[notifications]
enabled = true
detail_level = "summary"
discord_webhook_url = "https://discord.com/api/webhooks/123/abc"

[[sources]]
url = "https://t.me/channel1"
name = "Channel One"

[sources.filters]
extensions = [".pdf", ".epub", ".mobi"]
min_size = "100KB"
max_size = "500MB"

[[sources]]
url = "https://t.me/c/1234567890/123"
name = "Forum Topic"
```

**Note:** Environment variables override config.toml values.
