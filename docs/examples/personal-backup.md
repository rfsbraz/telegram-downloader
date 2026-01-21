# :material-content-save: Personal Chat Backup

Backup media from your personal chats and saved messages. Perfect for preserving memories and important files.

## Use Case

!!! info "Perfect For"
    - :material-account: Personal media archival
    - :material-heart: Preserving memories and photos
    - :material-file-document: Important document backup
    - :material-security: Privacy-focused data preservation

## Key Features

- **Saved Messages Support:** Backup your Telegram "Saved Messages"
- **Private Chat Backup:** Archive conversations with friends and family
- **All Media Types:** Photos, videos, documents, audio files
- **Privacy-Focused:** Runs locally, data never leaves your control

## Quick Start

### Create docker-compose.yml:

```yaml
version: '3.8'

services:
  telegram-downloader:
    image: rfsbraz/telegram-downloader:latest
    container_name: telegram-personal-backup
    restart: unless-stopped

    environment:
      # Telegram API credentials
      - TDL_API_ID=YOUR_API_ID
      - TDL_API_HASH=YOUR_API_HASH
      - TDL_PHONE_NUMBER=YOUR_PHONE_NUMBER

      # Daemon configuration
      - TDL_DAEMON_ENABLED=true
      - TDL_DAEMON_CHECK_INTERVAL=600  # Check every 10 minutes

      # Notifications (optional for personal use)
      - TDL_NOTIFICATIONS_ENABLED=false

      # Source 1: Your "Saved Messages"
      - TDL_SOURCES_0_URL=https://t.me/me
      - TDL_SOURCES_0_NAME=My Saved Messages
      - TDL_SOURCES_0_FILTERS_EXTENSIONS=.jpg,.png,.mp4,.pdf,.doc,.docx,.zip

      # Source 2: Private chat with friend (optional)
      - TDL_SOURCES_1_URL=https://t.me/friend_username
      - TDL_SOURCES_1_NAME=Friend Chat
      - TDL_SOURCES_1_FILTERS_EXTENSIONS=.jpg,.png,.mp4

    volumes:
      - ./personal_backup:/downloads
      - ./sessions:/.sessions

    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 2m
      timeout: 10s
```

### Deploy:

```bash
mkdir telegram-personal-backup && cd telegram-personal-backup
mkdir personal_backup sessions

# Create docker-compose.yml with configuration above
docker compose up -d
docker compose logs -f  # Authenticate on first run
```

## Configuration Highlights

### Saved Messages Backup

```yaml
- TDL_SOURCES_0_URL=https://t.me/me  # Special URL for "Saved Messages"
- TDL_SOURCES_0_NAME=My Saved Messages
```

!!! info "Saved Messages"
    `https://t.me/me` is a special URL that backs up your Telegram "Saved Messages".

### All Media Types

```yaml
# Comprehensive backup
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.jpg,.png,.gif,.mp4,.mp3,.pdf,.doc,.docx,.zip,.rar
```

### Privacy Settings

```yaml
# Disable notifications for privacy
- TDL_NOTIFICATIONS_ENABLED=false

# Mount volumes with restrictive permissions
# See deployment guide for security best practices
```

## Expected Results

### Folder Structure

```
personal_backup/
├── My Saved Messages/
│   ├── family_photo.jpg
│   ├── vacation_video.mp4
│   ├── important_document.pdf
│   └── work_presentation.pptx
└── Friend Chat/
    ├── shared_memory.jpg
    └── funny_video.mp4
```

### Backup Verification

```bash
# Check backup size
du -sh personal_backup/

# List recent files
find personal_backup/ -type f -mtime -7 -ls

# Count files by type
find personal_backup/ -name "*.jpg" | wc -l
find personal_backup/ -name "*.mp4" | wc -l
```

## Customization

### Selective Backup

```yaml
# Only photos and videos
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.jpg,.png,.mp4,.mov

# Only documents
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.doc,.docx,.txt

# Only recent media
- TDL_SOURCES_0_FILTERS_MIN_DATE=2025-01-01
```

### Multiple Private Chats

```yaml
- TDL_SOURCES_0_URL=https://t.me/me
- TDL_SOURCES_0_NAME=Saved Messages

- TDL_SOURCES_1_URL=https://t.me/friend1
- TDL_SOURCES_1_NAME=Friend 1

- TDL_SOURCES_2_URL=https://t.me/friend2
- TDL_SOURCES_2_NAME=Friend 2

- TDL_SOURCES_3_URL=https://t.me/family_group
- TDL_SOURCES_3_NAME=Family Group
```

### Backup Schedule

```yaml
# Daily backup (check every 24 hours)
- TDL_DAEMON_CHECK_INTERVAL=86400

# Weekly backup (check every 7 days)
- TDL_DAEMON_CHECK_INTERVAL=604800

# Real-time backup (check every 5 minutes)
- TDL_DAEMON_CHECK_INTERVAL=300
```

## Security Best Practices

!!! danger "Protect Your Backup"
    **Your backup contains private data. Secure it properly!**

### File Permissions

```bash
# Restrict access to backup folder
chmod 700 personal_backup/
chmod 700 sessions/

# Verify permissions
ls -la
```

### Encryption

```yaml
# Use encrypted volumes for sensitive data
volumes:
  - /mnt/encrypted/personal_backup:/downloads
```

### Session Protection

!!! warning "Session Files are Sensitive"
    Session files grant full access to your Telegram account.

    - Keep `sessions/` folder secure (chmod 700)
    - Never share session files
    - Back up sessions separately
    - Delete sessions if device is compromised

## Backup Strategy

### Automated Offsite Backup

```bash
#!/bin/bash
# backup-to-cloud.sh
# Run daily via cron

# Compress backup
tar -czf backup-$(date +%Y-%m-%d).tar.gz personal_backup/

# Upload to cloud storage (rclone example)
rclone copy backup-*.tar.gz remote:backups/telegram/

# Clean up local compressed backup
rm backup-*.tar.gz

# Keep last 30 days in cloud
rclone delete remote:backups/telegram/ --min-age 30d
```

### Verification Script

```bash
#!/bin/bash
# verify-backup.sh
# Verify backup integrity

echo "Backup Statistics:"
echo "Total files: $(find personal_backup/ -type f | wc -l)"
echo "Total size: $(du -sh personal_backup/ | cut -f1)"
echo ""
echo "By file type:"
echo "Photos: $(find personal_backup/ -name "*.jpg" -o -name "*.png" | wc -l)"
echo "Videos: $(find personal_backup/ -name "*.mp4" -o -name "*.mov" | wc -l)"
echo "Documents: $(find personal_backup/ -name "*.pdf" -o -name "*.doc*" | wc -l)"
```

## Troubleshooting

!!! bug "Can't Access Private Chat"
    Ensure:

    1. You have permission to access the chat
    2. Chat username is correct
    3. You're authenticated with correct account

!!! warning "Large Backup Size"
    Manage storage:

    ```yaml
    # Limit file sizes
    - TDL_SOURCES_0_FILTERS_MAX_SIZE=100MB

    # Only recent media
    - TDL_SOURCES_0_FILTERS_MIN_DATE=2025-01-01
    ```

!!! info "Selective Restore"
    Restore specific files:

    ```bash
    # Find specific file
    find personal_backup/ -name "*family*"

    # Restore to different location
    cp personal_backup/Saved\ Messages/file.jpg ~/restored/
    ```

See [Troubleshooting Guide](../troubleshooting.md) for more help.

## Performance

### Resource Usage

| Metric | Typical Usage | Notes |
|--------|---------------|-------|
| CPU | <5% | Minimal for personal use |
| Memory | 100-200 MB | Light workload |
| Disk | Varies | Depends on media volume |

### Optimization

- **Less frequent checks:** Personal backups don't need real-time sync
- **Date filtering:** Only backup recent media to save space
- **Selective sources:** Backup only important chats

## Related Examples

- [Ebook Forum](ebook-forum.md) - Similar setup for ebook archival
- [News Aggregator](news-aggregator.md) - Multi-source configuration
- [YouTube Archiver](youtube-archiver.md) - Video content backup

[:material-download: Download personal-backup.yml](https://raw.githubusercontent.com/rfsbraz/telegram-downloader/master/examples/personal-backup.yml){ .md-button }

[Back to Examples](index.md){ .md-button }
