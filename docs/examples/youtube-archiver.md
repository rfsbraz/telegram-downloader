# :material-youtube: YouTube Channel Archiver

Archive YouTube content shared in Telegram channels. Perfect for content preservation and offline viewing.

## Use Case

!!! info "Perfect For"
    - :material-video-box: Content archivists and preservationists
    - :material-school: Educational content collection
    - :material-database: Building offline video libraries
    - :material-backup-restore: Preserving valuable content

## Key Features

- **Video File Filtering:** Automatically filters MP4, MKV, and WEBM files
- **Organized Storage:** Videos organized by channel name
- **Size Filtering:** Configurable size limits for storage management
- **Automatic Archival:** Continuous monitoring and downloading

## Quick Start

### Create docker-compose.yml:

```yaml
version: '3.8'

services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
    container_name: telegram-youtube-archiver
    restart: unless-stopped

    environment:
      # Telegram API credentials
      - TDL_API_ID=YOUR_API_ID
      - TDL_API_HASH=YOUR_API_HASH
      - TDL_PHONE_NUMBER=YOUR_PHONE_NUMBER

      # Daemon configuration
      - TDL_DAEMON_ENABLED=true
      - TDL_DAEMON_CHECK_INTERVAL=300

      # Notifications
      - TDL_NOTIFICATIONS_ENABLED=true
      - TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_URL

      # Source: YouTube archival channel
      - TDL_SOURCES_0_URL=https://t.me/youtube_archive_channel
      - TDL_SOURCES_0_NAME=YouTube Archive
      - TDL_SOURCES_0_FILTERS_EXTENSIONS=.mp4,.mkv,.webm
      - TDL_SOURCES_0_FILTERS_MIN_SIZE=10MB
      - TDL_SOURCES_0_FILTERS_MAX_SIZE=2GB

    volumes:
      - ./youtube_archive:/downloads
      - ./sessions:/.sessions

    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 2m
      timeout: 10s
```

### Deploy:

```bash
mkdir telegram-youtube-archiver && cd telegram-youtube-archiver
mkdir youtube_archive sessions

# Create docker-compose.yml with configuration above
docker compose up -d
docker compose logs -f  # Authenticate on first run
```

## Configuration Highlights

### Video Filtering

```yaml
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.mp4,.mkv,.webm
- TDL_SOURCES_0_FILTERS_MIN_SIZE=10MB
- TDL_SOURCES_0_FILTERS_MAX_SIZE=2GB
```

!!! tip "Size Limits"
    - **Min 10MB:** Filters out low-quality clips
    - **Max 2GB:** Reasonable limit for most videos

### Multiple Channels

```yaml
- TDL_SOURCES_0_URL=https://t.me/channel1
- TDL_SOURCES_0_NAME=Tech Videos

- TDL_SOURCES_1_URL=https://t.me/channel2
- TDL_SOURCES_1_NAME=Educational Content
```

## Expected Results

### Folder Structure

```
youtube_archive/
└── YouTube Archive/
    ├── Video Title 1.mp4
    ├── Video Title 2.mkv
    └── Video Title 3.webm
```

### Storage Considerations

!!! warning "Disk Space"
    Video files consume significant storage. Monitor disk usage:

    ```bash
    df -h ./youtube_archive
    du -sh ./youtube_archive/*
    ```

## Customization

### Quality-Based Filtering

```yaml
# Only high-quality videos (>50MB)
- TDL_SOURCES_0_FILTERS_MIN_SIZE=50MB

# Only short clips (<500MB)
- TDL_SOURCES_0_FILTERS_MAX_SIZE=500MB
```

### Check Less Frequently

```yaml
# Check every 15 minutes for less frequent updates
- TDL_DAEMON_CHECK_INTERVAL=900
```

## Troubleshooting

!!! bug "Large Files Not Downloading"
    Check Telegram limits. Files >2GB require Telegram Premium.

!!! warning "Disk Space Full"
    Set up automatic cleanup or use external storage:

    ```yaml
    volumes:
      - /mnt/external/youtube_archive:/downloads
    ```

See [Troubleshooting Guide](../troubleshooting.md) for more help.

[:material-download: Download youtube-archiver.yml](https://raw.githubusercontent.com/rfsbraz/telegram-downloader/master/examples/youtube-archiver.yml){ .md-button }

[Back to Examples](index.md){ .md-button }
