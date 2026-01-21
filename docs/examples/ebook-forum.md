# :material-book-multiple: Ebook Forum Downloader

Automatically download ebooks from Telegram forum topics as they're posted. Perfect for building a personal ebook library from release forums.

## Use Case

!!! info "Perfect For"
    - :material-book-open-variant: Book collectors and readers
    - :material-school: Students and researchers
    - :material-library: Digital library curation
    - :material-forum: Following ebook release forums

## Key Features

<div class="grid cards" markdown>

-   :material-file-document:{ .lg .middle } **Ebook-Specific Filtering**

    ---

    Automatically filters for PDF, EPUB, MOBI, and AZW3 files

-   :material-folder-multiple:{ .lg .middle } **Organized by Topic**

    ---

    Each forum topic downloads to its own folder

-   :material-bell-ring:{ .lg .middle } **Discord Notifications**

    ---

    Get notified when new ebooks are downloaded

-   :material-shield-check:{ .lg .middle } **Duplicate Detection**

    ---

    Automatically skips files you already have

</div>

## Quick Start

### Prerequisites

- [x] Docker and Docker Compose installed
- [x] Telegram API credentials from [my.telegram.org/apps](https://my.telegram.org/apps)
- [x] Discord webhook URL (optional but recommended)
- [x] Member of the ebook forum/channel

### Setup Steps

**1. Create project directory:**

```bash
mkdir telegram-ebook-downloader
cd telegram-ebook-downloader
mkdir ebooks sessions
```

**2. Create `docker-compose.yml`:**

```yaml
--8<-- "examples/ebook-forum.yml"
```

**3. Configure your settings:**

Replace these placeholders:

| Placeholder | Get From | Example |
|-------------|----------|---------|
| `YOUR_API_ID` | https://my.telegram.org/apps | `12345678` |
| `YOUR_API_HASH` | https://my.telegram.org/apps | `abcdef123...` |
| `YOUR_PHONE_NUMBER` | Your phone with country code | `+1234567890` |
| `YOUR_DISCORD_WEBHOOK_URL` | Discord server settings | `https://discord.com/api/webhooks/...` |
| `https://t.me/c/1234567890/123` | Your forum topic URL | Copy from Telegram |

!!! tip "Finding Forum Topic URL"
    1. Open forum topic in Telegram Desktop
    2. Right-click topic → Copy Link
    3. URL format: `https://t.me/c/CHAT_ID/TOPIC_ID`

**4. Start the downloader:**

```bash
docker compose up -d
```

**5. First-time authentication:**

```bash
# View logs
docker compose logs -f

# Enter verification code when prompted
# Check your Telegram app for the code
```

**6. Verify it's working:**

```bash
# Check service status
docker compose ps

# Should show "healthy" status after ~1 minute

# Check downloads
ls -lh ebooks/
```

## Configuration Details

### File Filtering

The example configuration filters for ebooks:

```yaml
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi,.azw3
- TDL_SOURCES_0_FILTERS_MIN_SIZE=100KB
- TDL_SOURCES_0_FILTERS_MAX_SIZE=500MB
```

!!! info "Why These Settings?"
    - **Extensions:** Common ebook formats
    - **Min Size (100KB):** Filters out tiny files (likely not books)
    - **Max Size (500MB):** Reasonable limit for ebooks with images

### Check Interval

```yaml
- TDL_DAEMON_CHECK_INTERVAL=300  # 5 minutes
```

The daemon checks for new ebooks every 5 minutes. This is a good balance between:

- :material-clock-fast: **Responsiveness:** New books appear quickly
- :material-api: **API Usage:** Avoids Telegram rate limiting
- :material-battery: **Resource Usage:** Minimal CPU and network usage

### Notifications

```yaml
- TDL_NOTIFICATIONS_ENABLED=true
- TDL_NOTIFICATIONS_DETAIL_LEVEL=summary
- TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=YOUR_DISCORD_WEBHOOK_URL
```

You'll receive Discord notifications when:

- :material-check: New ebooks are downloaded
- :material-alert: Errors occur (authentication, network, etc.)
- :material-information: Daemon status changes

## Expected Results

### Folder Structure

```
ebooks/
└── Ebook Releases/          # Named from TDL_SOURCES_0_NAME
    ├── Book Title 1.pdf
    ├── Book Title 2.epub
    ├── Book Title 3.mobi
    └── Book Title 4.azw3
```

### Discord Notifications

You'll receive messages like:

> **Telegram Downloader** - Summary
>
> :white_check_mark: Download completed
>
> **Downloaded:** 3 new ebooks
>
> **Source:** Ebook Releases
>
> **Time:** 2026-01-21 10:30:00

### Logs

```bash
docker compose logs --tail=50
```

Healthy logs look like:

```
[INFO] Daemon started, checking every 300 seconds
[INFO] Checking source: Ebook Releases
[INFO] Found 3 new messages
[INFO] Downloading: Book Title 1.pdf (2.5 MB)
[INFO] Downloaded: Book Title 1.pdf
[INFO] Notification sent to Discord
[INFO] Cycle complete, waiting 300 seconds
```

## Customization Options

### Multiple Forum Topics

Add more sources by incrementing the index:

```yaml
# First topic
- TDL_SOURCES_0_URL=https://t.me/c/1234567890/123
- TDL_SOURCES_0_NAME=Fiction Ebooks
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi

# Second topic
- TDL_SOURCES_1_URL=https://t.me/c/1234567890/456
- TDL_SOURCES_1_NAME=Technical Books
- TDL_SOURCES_1_FILTERS_EXTENSIONS=.pdf

# Third topic
- TDL_SOURCES_2_URL=https://t.me/c/1234567890/789
- TDL_SOURCES_2_NAME=Comics
- TDL_SOURCES_2_FILTERS_EXTENSIONS=.cbr,.cbz,.pdf
```

### Genre-Specific Filtering

Filter by filename patterns:

```yaml
# Only download Python books
- TDL_SOURCES_0_FILTERS_PATTERNS=*python*,*Python*,*PYTHON*

# Only download fiction
- TDL_SOURCES_0_FILTERS_PATTERNS=*novel*,*fiction*,*story*
```

### Date-Based Filtering

Only download recent posts:

```yaml
- TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01  # Only 2026 onwards
```

### Adjust Check Frequency

```yaml
# More responsive (check every minute)
- TDL_DAEMON_CHECK_INTERVAL=60

# Less aggressive (check every 10 minutes)
- TDL_DAEMON_CHECK_INTERVAL=600

# Very light (check every hour)
- TDL_DAEMON_CHECK_INTERVAL=3600
```

!!! warning "Rate Limiting"
    Checking too frequently (< 60 seconds) may trigger Telegram rate limiting (FloodWait errors). The daemon automatically handles these, but they slow down downloads.

### Notification Detail Levels

```yaml
# Minimal: Just success/failure
- TDL_NOTIFICATIONS_DETAIL_LEVEL=minimal

# Summary: Include file counts and errors (recommended)
- TDL_NOTIFICATIONS_DETAIL_LEVEL=summary

# Detailed: Include filenames and full error messages
- TDL_NOTIFICATIONS_DETAIL_LEVEL=detailed
```

## Troubleshooting

!!! bug "No ebooks being downloaded"
    **Check these:**

    1. Verify you're a member of the forum/channel
    2. Check source URL is correct: `docker compose logs | grep "source"`
    3. Verify file filters match forum content
    4. Check for FloodWait errors in logs

!!! warning "FloodWait errors"
    **Solution:** Increase check interval

    ```yaml
    - TDL_DAEMON_CHECK_INTERVAL=600  # 10 minutes
    ```

!!! danger "Authentication failed"
    **Solution:** Delete sessions and re-authenticate

    ```bash
    docker compose down
    rm -rf sessions/*
    docker compose up -d
    docker compose logs -f
    # Enter verification code when prompted
    ```

See [Troubleshooting Guide](../troubleshooting.md) for more solutions.

## Performance

### Resource Usage

| Metric | Typical Usage | Notes |
|--------|---------------|-------|
| CPU | <5% average | Spikes during downloads |
| Memory | 150-250 MB | Depends on file sizes |
| Network | Varies | Based on download activity |
| Disk I/O | Low | Only during downloads |

### Scalability

- **Single topic:** Handles 1000s of ebooks easily
- **Multiple topics:** 5-10 sources work well on modest hardware
- **Large forums:** Consider increasing check interval to reduce load

## Production Deployment

!!! tip "Production Best Practices"
    1. Use `.env` file for secrets (not hardcoded)
    2. Set resource limits in docker-compose.yml
    3. Configure log rotation
    4. Set up automated backups of sessions folder
    5. Monitor with health checks

See [Production Deployment Guide](../deployment.md) for detailed setup.

## Complete Configuration File

Download the complete example:

[:material-download: Download ebook-forum.yml](../../examples/ebook-forum.yml){ .md-button }

## Related Examples

- [Personal Chat Backup](personal-backup.md) - Backup your saved ebooks
- [News Aggregator](news-aggregator.md) - Similar multi-source setup
- [YouTube Archiver](youtube-archiver.md) - Archive video content

## Need Help?

!!! question "Questions?"
    - See [Configuration Reference](../configuration.md) for all settings
    - Check [Troubleshooting Guide](../troubleshooting.md) for common issues
    - Open an issue on [GitHub](https://github.com/rfsbraz/telegram-downloader/issues)
