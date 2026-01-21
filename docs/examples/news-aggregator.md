# :material-newspaper: News Media Aggregator

Collect and organize media from news channels automatically. Perfect for media monitoring and journalism.

## Use Case

!!! info "Perfect For"
    - :material-newspaper-variant: Journalists and media professionals
    - :material-magnify: Researchers and analysts
    - :material-chart-line: Media monitoring services
    - :material-archive: News archival projects

## Key Features

- **Multi-Channel Aggregation:** Monitor multiple news sources simultaneously
- **Media Type Filtering:** Images, videos, and documents
- **Date-Based Organization:** Filter by publication date
- **Real-Time Monitoring:** Continuous updates from news channels

## Quick Start

### Create docker-compose.yml:

```yaml
version: '3.8'

services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
    container_name: telegram-news-aggregator
    restart: unless-stopped

    environment:
      # Telegram API credentials
      - TDL_API_ID=YOUR_API_ID
      - TDL_API_HASH=YOUR_API_HASH
      - TDL_PHONE_NUMBER=YOUR_PHONE_NUMBER

      # Daemon configuration
      - TDL_DAEMON_ENABLED=true
      - TDL_DAEMON_CHECK_INTERVAL=180  # Check every 3 minutes for news

      # Notifications
      - TDL_NOTIFICATIONS_ENABLED=true
      - TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_URL
      - TDL_NOTIFICATIONS_DETAIL_LEVEL=summary

      # Source 1: Breaking News Channel
      - TDL_SOURCES_0_URL=https://t.me/breaking_news_channel
      - TDL_SOURCES_0_NAME=Breaking News
      - TDL_SOURCES_0_FILTERS_EXTENSIONS=.jpg,.png,.mp4,.pdf
      - TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01

      # Source 2: Tech News Channel
      - TDL_SOURCES_1_URL=https://t.me/tech_news_channel
      - TDL_SOURCES_1_NAME=Tech News
      - TDL_SOURCES_1_FILTERS_EXTENSIONS=.jpg,.png,.mp4

      # Source 3: Local News Channel
      - TDL_SOURCES_2_URL=https://t.me/local_news_channel
      - TDL_SOURCES_2_NAME=Local News
      - TDL_SOURCES_2_FILTERS_EXTENSIONS=.jpg,.png,.mp4,.pdf

    volumes:
      - ./news_media:/downloads
      - ./sessions:/.sessions

    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 2m
      timeout: 10s
```

### Deploy:

```bash
mkdir telegram-news-aggregator && cd telegram-news-aggregator
mkdir news_media sessions

# Create docker-compose.yml with configuration above
docker compose up -d
docker compose logs -f  # Authenticate on first run
```

## Configuration Highlights

### Fast Updates

```yaml
- TDL_DAEMON_CHECK_INTERVAL=180  # 3 minutes for breaking news
```

!!! warning "Balance Performance"
    Faster checks = more API usage. Monitor for FloodWait errors.

### Date Filtering

```yaml
- TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01  # Only recent news
```

### Media Types

```yaml
# Images and videos only
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.jpg,.png,.mp4,.webm

# Include documents
- TDL_SOURCES_1_FILTERS_EXTENSIONS=.jpg,.png,.mp4,.pdf,.doc,.docx
```

## Expected Results

### Folder Structure

```
news_media/
├── Breaking News/
│   ├── 2026-01-21_breaking_story.jpg
│   ├── 2026-01-21_video_report.mp4
│   └── 2026-01-21_press_release.pdf
├── Tech News/
│   ├── product_launch.jpg
│   └── keynote_video.mp4
└── Local News/
    ├── local_event.jpg
    └── community_report.pdf
```

### Notifications

Discord alerts for:

- :material-bell: New media from monitored channels
- :material-alert: Missing or deleted posts
- :material-information: Daily summary of collected media

## Customization

### Topic-Based Filtering

```yaml
# Only download content about specific topics
- TDL_SOURCES_0_FILTERS_PATTERNS=*breaking*,*urgent*,*alert*

# Filter out certain topics
- TDL_SOURCES_1_FILTERS_PATTERNS=*election*,*politics*
```

### Size Limits for Storage Management

```yaml
# Limit individual file sizes
- TDL_SOURCES_0_FILTERS_MIN_SIZE=50KB
- TDL_SOURCES_0_FILTERS_MAX_SIZE=50MB
```

### Multiple Detail Levels

```yaml
# Minimal: Just counts
- TDL_NOTIFICATIONS_DETAIL_LEVEL=minimal

# Summary: Counts + source info (recommended for news)
- TDL_NOTIFICATIONS_DETAIL_LEVEL=summary

# Detailed: Full file listings
- TDL_NOTIFICATIONS_DETAIL_LEVEL=detailed
```

## Use Cases

### Media Monitoring

Monitor competitor coverage or brand mentions across news channels.

### Research & Analysis

Collect media for academic research or trend analysis.

### Archival Projects

Build comprehensive archives of historical news coverage.

### Journalism

Track breaking stories across multiple sources in real-time.

## Performance Tips

!!! tip "Optimize for News"
    1. **Faster checks:** 2-3 minutes for breaking news
    2. **Date filtering:** Only recent posts to reduce processing
    3. **Multiple sources:** Aggregate from 5-10 channels effectively
    4. **Storage monitoring:** News media accumulates quickly

## Troubleshooting

!!! bug "Too Many Files"
    Use date filtering to limit scope:

    ```yaml
    - TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-15
    - TDL_SOURCES_0_FILTERS_MAX_DATE=2026-01-21
    ```

!!! warning "Rate Limiting"
    If checking many sources rapidly, increase interval:

    ```yaml
    - TDL_DAEMON_CHECK_INTERVAL=300  # 5 minutes
    ```

See [Troubleshooting Guide](../troubleshooting.md) for more help.

[:material-download: Download news-aggregator.yml](https://raw.githubusercontent.com/rfsbraz/telegram-downloader/master/examples/news-aggregator.yml){ .md-button }

[Back to Examples](index.md){ .md-button }
