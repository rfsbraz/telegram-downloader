"""Generic HTTP POST webhook with retry logic."""
import logging
import time
from datetime import datetime

import requests


logger = logging.getLogger(__name__)


class GenericWebhook:
    """
    Generic HTTP POST webhook with exponential backoff retry.

    Features:
    - Retry on 5xx errors (server-side issues)
    - Retry on network errors
    - No retry on 4xx errors (client errors)
    - Exponential backoff: 1s, 2s, 4s (max 3 attempts)
    - 10 second timeout per attempt

    Compatible with:
    - Slack incoming webhooks
    - IFTTT webhook service
    - n8n webhook nodes
    - Zapier webhooks
    - Custom HTTP endpoints
    """

    def __init__(
        self,
        webhook_url: str,
        max_retries: int = 3,
        base_delay: float = 1.0
    ):
        """
        Initialize generic webhook.

        Args:
            webhook_url: HTTP POST endpoint URL
            max_retries: Maximum retry attempts (default: 3)
            base_delay: Base delay for exponential backoff (default: 1.0s)
        """
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.log = logging.getLogger("webhook")

    async def send(
        self,
        level: str,
        title: str,
        message: str,
        details: dict
    ) -> bool:
        """
        Send generic webhook with exponential backoff retry.

        Retry strategy:
        - Retry on 5xx errors (server-side issues)
        - Retry on network errors
        - Don't retry on 4xx errors (client errors)
        - Exponential backoff: 1s, 2s, 4s

        Payload format:
        {
            "level": "error" | "success" | "info",
            "title": "Notification title",
            "message": "Message body",
            "timestamp": "2026-01-21T12:00:00",
            "details": {...}
        }

        Args:
            level: Notification severity ("error", "success", "info")
            title: Notification title
            message: Main message body
            details: Additional structured data

        Returns:
            True if successfully sent, False after max retries exceeded
        """
        payload = {
            "level": level,
            "title": title,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10
                )

                # Success (2xx)
                if 200 <= response.status_code < 300:
                    if attempt > 0:
                        self.log.info(
                            f"Webhook succeeded on attempt {attempt + 1}/{self.max_retries}"
                        )
                    return True

                # Client error (4xx) - don't retry
                if 400 <= response.status_code < 500:
                    self.log.error(
                        f"Webhook failed with {response.status_code}: {response.text[:200]}"
                    )
                    return False

                # Server error (5xx) - retry with backoff
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    self.log.warning(
                        f"Webhook returned {response.status_code}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    continue

                # Max retries exceeded
                self.log.error(
                    f"Webhook failed after {self.max_retries} attempts: "
                    f"status {response.status_code}"
                )
                return False

            except requests.RequestException as e:
                # Network error - retry with backoff
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    self.log.warning(
                        f"Webhook network error: {e}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    continue

                self.log.error(f"Webhook failed after {self.max_retries} attempts: {e}")
                return False

        return False
