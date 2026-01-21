# Telegram Media Downloader

> **📖 [View Full Documentation](https://rfsbraz.github.io/telegram-downloader/)** | [🚀 Quick Start](https://rfsbraz.github.io/telegram-downloader/quickstart/) | [⚙️ Configuration](https://rfsbraz.github.io/telegram-downloader/configuration/)

---

**Automated Telegram media downloader daemon with multi-source support, flexible filtering, and Docker deployment.**

Perfect for:
- 📚 **Ebook forum archiving** (featured use case)
- 📺 YouTube channel mirrors
- 📰 News channel media aggregation
- 💾 Personal chat backups

## 🎯 Featured Use Case: Ebook Forum Downloader

Automatically download ebooks from Telegram forum topics as they're posted. Set it up once, run continuously in Docker, get notifications when new books arrive.

**Example:** Follow ebook release forums, filter for PDF/EPUB/MOBI files, organize by source, receive Discord notifications on new releases.

```yaml
# See examples/ebook-forum.yml for complete configuration
services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
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

## ✨ Features

- **Multi-Source Support:** Channels, groups, forum topics, private chats
- **Advanced Filtering:** Extensions, size ranges, date ranges, filename patterns
- **Smart Organization:** Per-source folders, duplicate detection, conflict resolution
- **Daemon Mode:** Continuous background operation with configurable check intervals
- **Notifications:** Discord webhooks and generic HTTP POST for errors and completions
- **Docker Ready:** Multi-platform images (amd64 + arm64), Docker Compose setup, health checks
- **Secure:** Session protection, path traversal prevention, non-root container

## 🚀 Quick Start

### Prerequisites

1. **Docker and Docker Compose** installed
2. **Telegram API credentials** from https://my.telegram.org/apps
3. **Discord webhook URL** (optional, for notifications)

### 5-Minute Setup

1. Create project directory:
```bash
mkdir telegram-downloader && cd telegram-downloader
mkdir downloads sessions
```

2. Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
    restart: unless-stopped
    environment:
      - TDL_API_ID=YOUR_API_ID
      - TDL_API_HASH=YOUR_API_HASH
      - TDL_PHONE_NUMBER=YOUR_PHONE_NUMBER
      - TDL_DAEMON_ENABLED=true
      - TDL_SOURCES_0_URL=https://t.me/example_channel
    volumes:
      - ./downloads:/downloads
      - ./sessions:/.sessions
```

3. Start service:
```bash
docker compose up -d
```

4. View logs:
```bash
docker compose logs -f
```

5. Check health:
```bash
docker compose ps  # Should show "healthy" status
```

**First run:** You'll need to enter the Telegram verification code sent to your phone. Check logs with `docker compose logs -f`, enter code when prompted.

See [docs/quickstart.md](docs/quickstart.md) for detailed guide.

## 📖 Documentation

- **[Quick Start Guide](docs/quickstart.md):** 5-minute Docker Compose setup
- **[Configuration Reference](docs/configuration.md):** All settings explained
- **[Troubleshooting Guide](docs/troubleshooting.md):** Common errors and solutions
- **[Deployment Guide](docs/deployment.md):** Production best practices

## 🎨 Example Use Cases

All examples in `examples/` directory with complete configurations:

- **[ebook-forum.yml](examples/ebook-forum.yml):** Ebook forum downloader (featured)
- **[youtube-archiver.yml](examples/youtube-archiver.yml):** YouTube channel mirror archiver
- **[news-aggregator.yml](examples/news-aggregator.yml):** News channel media aggregator
- **[personal-backup.yml](examples/personal-backup.yml):** Personal chat backup

## 🔧 Configuration Highlights

**Multiple Sources:**
```yaml
- TDL_SOURCES_0_URL=https://t.me/channel1
- TDL_SOURCES_1_URL=https://t.me/c/1234/567  # Forum topic
- TDL_SOURCES_2_URL=https://t.me/me  # Saved messages
```

**Flexible Filtering:**
```yaml
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi
- TDL_SOURCES_0_FILTERS_MIN_SIZE=100KB
- TDL_SOURCES_0_FILTERS_MAX_SIZE=500MB
- TDL_SOURCES_0_FILTERS_MIN_DATE=2026-01-01
```

**Notifications:**
```yaml
- TDL_NOTIFICATIONS_ENABLED=true
- TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
- TDL_NOTIFICATIONS_DETAIL_LEVEL=summary
```

See [docs/configuration.md](docs/configuration.md) for complete reference.

## 🐛 Troubleshooting

**Common issues:**

- **"FloodWait" errors:** Telegram rate limiting, daemon automatically retries. Reduce check frequency if persistent.
- **"PEER_ID_INVALID":** Invalid source URL or no access to source
- **Health check failing:** Check logs for errors, verify daemon is running

See [docs/troubleshooting.md](docs/troubleshooting.md) for detailed solutions.

## 📦 Installation

**Docker Hub:**
```bash
docker pull rfsbraz/telegram-downloader:latest
```

**GitHub Container Registry:**
```bash
docker pull ghcr.io/rfsbraz/telegram-downloader:latest
```

**Multi-platform support:**
- `linux/amd64` (Intel/AMD x86_64)
- `linux/arm64` (Raspberry Pi 4+, AWS Graviton, Apple M1/M2)

## 🤝 Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

Built with:
- [Pyrogram](https://docs.pyrogram.org/) - Telegram MTProto API framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [PyYAML](https://pyyaml.org/) - Configuration parsing

## 💬 Support

- **Issues:** GitHub Issues for bug reports and feature requests
- **Discussions:** GitHub Discussions for questions and community support
- **Documentation:** See `docs/` directory for guides

---

**Star this repo if it helps you!** ⭐
