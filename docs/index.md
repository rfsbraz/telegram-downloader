# Telegram Media Downloader

**Automated Telegram media downloader daemon with multi-source support, flexible filtering, and Docker deployment.**

<div class="grid cards" markdown>

-   :material-book-multiple:{ .lg .middle } **Ebook Forum Archiving**

    ---

    Automatically download ebooks from Telegram forum topics as they're posted

    [:octicons-arrow-right-24: Ebook Example](examples/ebook-forum.md)

-   :material-youtube:{ .lg .middle } **YouTube Channel Mirrors**

    ---

    Archive YouTube content shared in Telegram channels

    [:octicons-arrow-right-24: YouTube Example](examples/youtube-archiver.md)

-   :material-newspaper:{ .lg .middle } **News Media Aggregation**

    ---

    Collect media from news channels automatically

    [:octicons-arrow-right-24: News Example](examples/news-aggregator.md)

-   :material-content-save:{ .lg .middle } **Personal Chat Backups**

    ---

    Backup media from your personal chats and saved messages

    [:octicons-arrow-right-24: Backup Example](examples/personal-backup.md)

</div>

## :rocket: Quick Start

Get started in 5 minutes with Docker Compose.

[Get Started](quickstart.md){ .md-button .md-button--primary }
[View Examples](examples/index.md){ .md-button }

## :sparkles: Features

<div class="grid cards" markdown>

-   :fontawesome-solid-list-check:{ .lg .middle } **Multi-Source Support**

    ---

    Download from channels, groups, forum topics, and private chats with flexible URL patterns

-   :material-filter:{ .lg .middle } **Advanced Filtering**

    ---

    Filter by file extensions, size ranges, date ranges, and filename patterns

-   :material-folder-multiple:{ .lg .middle } **Smart Organization**

    ---

    Organize with per-source folders, duplicate detection, and conflict resolution

-   :material-robot:{ .lg .middle } **Daemon Mode**

    ---

    Continuous background operation with configurable check intervals

-   :material-bell:{ .lg .middle } **Notifications**

    ---

    Get alerts via Discord webhooks and generic HTTP POST for errors and completions

-   :material-docker:{ .lg .middle } **Docker Ready**

    ---

    Multi-platform images (amd64 + arm64), Docker Compose setup, health checks

-   :material-shield-check:{ .lg .middle } **Secure**

    ---

    Session protection, path traversal prevention, non-root container

-   :material-cog:{ .lg .middle } **Flexible Configuration**

    ---

    Environment variables or TOML configuration with validation

</div>

## :dart: Featured Use Case: Ebook Forum Downloader

Automatically download ebooks from Telegram forum topics as they're posted. Set it up once, run continuously in Docker, get notifications when new books arrive.

**Example:** Follow ebook release forums, filter for PDF/EPUB/MOBI files, organize by source, receive Discord notifications on new releases.

```yaml
# docker-compose.yml - Complete example in examples/ebook-forum.yml
services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
    restart: unless-stopped
    environment:
      - TDL_API_ID=YOUR_API_ID
      - TDL_API_HASH=YOUR_API_HASH
      - TDL_PHONE_NUMBER=YOUR_PHONE
      - TDL_DAEMON_ENABLED=true
      - TDL_SOURCES_0_URL=https://t.me/c/1234567890/123
      - TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi
    volumes:
      - ./ebooks:/downloads
```

**Result:** Ebooks organized by forum topic, duplicates skipped, new releases downloaded every 5 minutes, Discord notifications on completion.

[View Complete Ebook Example :material-arrow-right:](examples/ebook-forum.md){ .md-button }

## :books: Documentation

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **[Quick Start Guide](quickstart.md)**

    ---

    5-minute Docker Compose setup with step-by-step instructions

-   :material-cog-outline:{ .lg .middle } **[Configuration Reference](configuration.md)**

    ---

    Complete reference for all settings and environment variables

-   :material-bug:{ .lg .middle } **[Troubleshooting Guide](troubleshooting.md)**

    ---

    Common errors and solutions with debugging tips

-   :material-cloud-upload:{ .lg .middle } **[Deployment Guide](deployment.md)**

    ---

    Production best practices and deployment checklist

</div>

## :art: Example Use Cases

All examples include complete Docker Compose configurations:

-   **[Ebook Forum](examples/ebook-forum.md)** - Automatic ebook downloads from forum topics (featured)
-   **[YouTube Archiver](examples/youtube-archiver.md)** - Mirror YouTube channels shared in Telegram
-   **[News Aggregator](examples/news-aggregator.md)** - Aggregate media from news channels
-   **[Personal Backup](examples/personal-backup.md)** - Backup personal chats and saved messages

[View All Examples :material-arrow-right:](examples/index.md){ .md-button }

## :wrench: Configuration Highlights

### Multiple Sources

```yaml
- TDL_SOURCES_0_URL=https://t.me/channel1
- TDL_SOURCES_1_URL=https://t.me/c/1234/567  # Forum topic
- TDL_SOURCES_2_URL=https://t.me/me  # Saved messages
```

### Flexible Filtering

```yaml
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi
- TDL_SOURCES_0_FILTERS_MIN_SIZE=100KB
- TDL_SOURCES_0_FILTERS_MAX_SIZE=500MB
- TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01
```

### Notifications

```yaml
- TDL_NOTIFICATIONS_ENABLED=true
- TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
- TDL_NOTIFICATIONS_DETAIL_LEVEL=summary
```

See [Configuration Reference](configuration.md) for complete documentation.

## :package: Installation

=== "Docker Hub"

    ```bash
    docker pull rfsbraz/telegram-downloader:latest
    ```

=== "GitHub Container Registry"

    ```bash
    docker pull ghcr.io/rfsbraz/telegram-downloader:latest
    ```

**Multi-platform support:**

- `linux/amd64` (Intel/AMD x86_64)
- `linux/arm64` (Raspberry Pi 4+, AWS Graviton, Apple M1/M2)

## :bug: Common Issues

!!! warning "FloodWait Errors"
    Telegram rate limiting - daemon automatically retries. Reduce check frequency if persistent.

!!! danger "PEER_ID_INVALID"
    Invalid source URL or no access to source. Verify URL and permissions.

!!! info "Health Check Failing"
    Check logs for errors and verify daemon is running properly.

See [Troubleshooting Guide](troubleshooting.md) for detailed solutions.

## :handshake: Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## :page_facing_up: License

MIT License - see LICENSE file for details.

## :pray: Acknowledgments

Built with:

- [Pyrogram](https://docs.pyrogram.org/) - Telegram MTProto API framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [PyYAML](https://pyyaml.org/) - Configuration parsing

## :speech_balloon: Support

- **Issues:** [GitHub Issues](https://github.com/rfsbraz/telegram-downloader/issues) for bug reports and feature requests
- **Discussions:** [GitHub Discussions](https://github.com/rfsbraz/telegram-downloader/discussions) for questions and community support
- **Documentation:** Browse the guides in the navigation menu

---

**Star this repo if it helps you!** :star:
