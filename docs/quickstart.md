# Quick Start Guide

Get Telegram Downloader running in 5 minutes with Docker Compose.

## Prerequisites

!!! info "Required Software"
    **Docker and Docker Compose installed**

    - Docker Desktop (Windows/Mac): https://www.docker.com/products/docker-desktop
    - Docker Engine (Linux): https://docs.docker.com/engine/install/

!!! warning "Telegram API Credentials Required"
    **Get your API credentials from Telegram:**

    1. Visit https://my.telegram.org/apps
    2. Log in with your phone number
    3. Create a new application
    4. Note your `api_id` and `api_hash`

    **Keep these credentials secure!**

!!! tip "Optional: Discord Notifications"
    **Set up Discord webhooks for download notifications:**

    1. Open Discord server settings
    2. Integrations → Webhooks → New Webhook
    3. Copy webhook URL

## Step-by-Step Setup

### 1. Create Project Directory

```bash
mkdir telegram-downloader
cd telegram-downloader
mkdir downloads sessions
```

### 2. Create docker-compose.yml

Create `docker-compose.yml` with this content:

```yaml
version: '3.8'

services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
    container_name: telegram-downloader
    restart: unless-stopped

    environment:
      # Required: Telegram API credentials
      - TDL_API_ID=YOUR_API_ID
      - TDL_API_HASH=YOUR_API_HASH
      - TDL_PHONE_NUMBER=YOUR_PHONE_NUMBER

      # Daemon configuration
      - TDL_DAEMON_ENABLED=true
      - TDL_DAEMON_CHECK_INTERVAL=300  # Check every 5 minutes

      # Notification configuration (optional)
      - TDL_NOTIFICATIONS_ENABLED=false
      # - TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_URL

      # Source configuration
      - TDL_SOURCES_0_URL=https://t.me/example_channel
      - TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi

    volumes:
      - ./downloads:/downloads
      - ./sessions:/.sessions

    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 2m
      timeout: 10s
```

**Replace these values:**
- `YOUR_API_ID` - Your Telegram API ID from step 2
- `YOUR_API_HASH` - Your Telegram API hash from step 2
- `YOUR_PHONE_NUMBER` - Your phone number with country code (e.g., +1234567890)
- `https://t.me/example_channel` - The Telegram source you want to download from

### 3. Start the Service

```bash
docker compose up -d
```

### 4. First Run: Authentication

On first run, you need to authenticate with Telegram:

```bash
# View logs
docker compose logs -f

# You'll see: "Enter phone code:"
# Check your Telegram app for verification code
# Enter code in logs (if prompted via stdin)

# OR restart container to trigger authentication prompt
docker compose restart
docker compose logs -f
```

!!! note "Authentication with Daemon Mode"
    For daemon mode, you may need to temporarily set `TDL_DAEMON_ENABLED=false`, authenticate, then re-enable daemon mode and restart the service.

### 5. Monitor Operation

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f

# Check health
docker compose ps  # "healthy" status means working

# Stop service
docker compose down

# Restart service
docker compose restart
```

## Next Steps

### Enable Notifications

Add Discord webhook to get notified:

```yaml
- TDL_NOTIFICATIONS_ENABLED=true
- TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123/abc
- TDL_NOTIFICATIONS_DETAIL_LEVEL=summary
```

Restart: `docker compose restart`

### Add More Sources

Add multiple sources by incrementing the index:

```yaml
- TDL_SOURCES_0_URL=https://t.me/channel1
- TDL_SOURCES_1_URL=https://t.me/channel2
- TDL_SOURCES_2_URL=https://t.me/c/1234567890/123  # Forum topic
```

### Adjust Filtering

Filter by file type, size, date:

```yaml
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.mp4,.mkv,.webm
- TDL_SOURCES_0_FILTERS_MIN_SIZE=10MB
- TDL_SOURCES_0_FILTERS_MAX_SIZE=2GB
- TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01
```

### Use Example Configurations

See `examples/` directory for complete use cases:
- `examples/ebook-forum.yml` - Ebook forum downloader
- `examples/youtube-archiver.yml` - YouTube mirror archiver
- `examples/news-aggregator.yml` - News channel aggregator
- `examples/personal-backup.yml` - Personal chat backup

## Troubleshooting

!!! danger "Service Won't Start"
    **Check these common issues:**

    - Check logs: `docker compose logs`
    - Verify API credentials are correct
    - Ensure phone number includes country code (+1...)

!!! warning "FloodWait Errors"
    **Telegram rate limiting (normal behavior):**

    - Daemon automatically retries with exponential backoff
    - Reduce `TDL_DAEMON_CHECK_INTERVAL` if persistent
    - Consider spreading downloads across multiple sources

!!! bug "Health Check Failing"
    **Verify daemon configuration:**

    - Check logs for errors: `docker compose logs`
    - Verify daemon is enabled: `TDL_DAEMON_ENABLED=true`
    - Increase start period if container is slow to start

!!! info "Need More Help?"
    See [Troubleshooting Guide](troubleshooting.md) for detailed solutions and debugging tips.
