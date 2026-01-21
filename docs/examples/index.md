# Example Use Cases

Complete Docker Compose configurations for common use cases.

## Overview

Each example includes:

- :material-file-document-outline: **Use case description** with target audience
- :material-star: **Key features** highlighted
- :material-docker: **Complete docker-compose.yml** configuration
- :material-list-status: **Step-by-step setup** instructions
- :material-check-circle: **Expected results** and validation
- :material-tune: **Customization options** for your needs

## Available Examples

<div class="grid cards" markdown>

-   :material-book-multiple:{ .lg .middle } **[Ebook Forum Downloader](ebook-forum.md)**

    ---

    Automatically download ebooks from Telegram forum topics

    **Perfect for:** Book collectors, students, researchers

    **Features:** PDF/EPUB/MOBI filtering, per-topic organization, Discord notifications

    [:octicons-arrow-right-24: View Example](ebook-forum.md)

-   :material-youtube:{ .lg .middle } **[YouTube Channel Archiver](youtube-archiver.md)**

    ---

    Archive YouTube content shared in Telegram channels

    **Perfect for:** Content archivists, education, preservation

    **Features:** Video file filtering, automatic organization, content preservation

    [:octicons-arrow-right-24: View Example](youtube-archiver.md)

-   :material-newspaper:{ .lg .middle } **[News Media Aggregator](news-aggregator.md)**

    ---

    Collect and organize media from news channels

    **Perfect for:** Journalists, researchers, media monitoring

    **Features:** Multi-channel aggregation, media type filtering, date-based organization

    [:octicons-arrow-right-24: View Example](news-aggregator.md)

-   :material-content-save:{ .lg .middle } **[Personal Chat Backup](personal-backup.md)**

    ---

    Backup media from personal chats and saved messages

    **Perfect for:** Personal archiving, data preservation, backup solutions

    **Features:** Comprehensive media backup, saved messages support, privacy-focused

    [:octicons-arrow-right-24: View Example](personal-backup.md)

</div>

## Quick Start with Examples

!!! tip "Using These Examples"
    1. Choose an example that matches your use case
    2. Copy the complete `docker-compose.yml` configuration
    3. Replace placeholder values with your credentials
    4. Customize filters and settings for your needs
    5. Deploy with `docker compose up -d`

## Configuration Patterns

### Common Settings Across Examples

All examples share these core settings:

=== "API Credentials"

    ```yaml
    - TDL_API_ID=YOUR_API_ID
    - TDL_API_HASH=YOUR_API_HASH
    - TDL_PHONE_NUMBER=YOUR_PHONE_NUMBER
    ```

    Get credentials from [https://my.telegram.org/apps](https://my.telegram.org/apps)

=== "Daemon Mode"

    ```yaml
    - TDL_DAEMON_ENABLED=true
    - TDL_DAEMON_CHECK_INTERVAL=300  # Check every 5 minutes
    ```

    Enables continuous background operation

=== "Notifications"

    ```yaml
    - TDL_NOTIFICATIONS_ENABLED=true
    - TDL_NOTIFICATIONS_DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_URL
    - TDL_NOTIFICATIONS_DETAIL_LEVEL=summary
    ```

    Optional but recommended for monitoring

### Customization Options

Each example can be customized:

-   **File Filters:** Change file extensions to match your needs
-   **Size Limits:** Adjust min/max file sizes
-   **Date Ranges:** Filter by message date
-   **Check Frequency:** Balance between responsiveness and API usage
-   **Notification Detail:** Choose minimal, summary, or detailed notifications

## Example Comparison

| Example | Best For | File Types | Complexity | Setup Time |
|---------|----------|------------|------------|------------|
| [Ebook Forum](ebook-forum.md) | Book collectors | PDF, EPUB, MOBI | Medium | 10 min |
| [YouTube Archiver](youtube-archiver.md) | Content archivists | MP4, MKV, WEBM | Low | 5 min |
| [News Aggregator](news-aggregator.md) | Media monitoring | Images, Videos | Medium | 10 min |
| [Personal Backup](personal-backup.md) | Personal archiving | All media types | Low | 5 min |

## Need Help?

!!! question "Common Questions"
    **"Can I combine multiple examples?"**

    Yes! Use multiple source configurations in a single docker-compose.yml file.

    **"How do I modify an example for my needs?"**

    Each example page includes a "Customization Options" section with guidance.

    **"What if my use case isn't covered?"**

    Use the [Configuration Reference](../configuration.md) to create a custom setup.

## Next Steps

1. Choose an example that matches your needs
2. Follow the setup instructions
3. Customize for your specific requirements
4. Deploy and monitor

!!! success "Pro Tip"
    Start with one of these examples and gradually customize it. It's easier than starting from scratch!
