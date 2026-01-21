"""Discord webhook notifier with embeds."""
import logging
from datetime import datetime
from typing import Optional

import requests


logger = logging.getLogger(__name__)


class DiscordNotifier:
    """
    Discord webhook notifier with colored embeds.

    Features:
    - Color-coded embeds based on severity (red=error, green=success, blue=info)
    - Timestamp in ISO format
    - Details converted to embed fields
    - 429 rate limit detection (logged but not automatically retried)

    Note: We don't use the discord-webhook library to avoid adding an extra
    dependency when the requests library (already a project dependency via
    Pyrogram) is sufficient for simple webhook POST operations.
    """

    # Discord embed color codes (decimal format)
    COLORS = {
        "error": 15548997,    # Red
        "success": 5763719,   # Green
        "info": 3447003       # Blue
    }

    def __init__(self, webhook_url: str, username: str = "Telegram Downloader"):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL (https://discord.com/api/webhooks/...)
            username: Bot username to display (default: "Telegram Downloader")
        """
        self.webhook_url = webhook_url
        self.username = username
        self.log = logging.getLogger("discord")

    async def send(
        self,
        level: str,
        title: str,
        message: str,
        details: dict
    ) -> bool:
        """
        Send Discord webhook notification with embed.

        Rate limiting: Discord limits webhooks to ~5 messages per 2 seconds.
        We rely on external throttling in NotificationManager. If 429 is
        received, we log a warning and return False.

        Args:
            level: Notification severity ("error", "success", "info")
            title: Notification title
            message: Main message body
            details: Additional structured data

        Returns:
            True if successfully sent, False on failure
        """
        # Build Discord embed
        embed = {
            "title": title,
            "description": message,
            "color": self.COLORS.get(level, self.COLORS["info"]),
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [
                {"name": k, "value": str(v), "inline": True}
                for k, v in details.items()
            ]
        }

        payload = {
            "username": self.username,
            "embeds": [embed]
        }

        try:
            # Synchronous request (requests library)
            # Note: For async version, would use aiohttp or httpx
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            # Check for rate limiting
            if response.status_code == 429:
                retry_after = response.json().get("retry_after", 0)
                self.log.warning(
                    f"Discord rate limited, retry after {retry_after}s. "
                    "Consider reducing notification frequency."
                )
                return False

            # Raise for other errors
            response.raise_for_status()
            return True

        except requests.RequestException as e:
            self.log.error(f"Discord webhook failed: {e}")
            return False
