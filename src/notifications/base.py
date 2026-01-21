"""Base protocol for notification channels."""
from typing import Protocol


class Notifier(Protocol):
    """
    Protocol for notification channel implementations.

    All notifiers must implement the async send method to deliver
    notifications through their respective channels (Discord, webhooks, etc.).
    """

    async def send(
        self,
        level: str,
        title: str,
        message: str,
        details: dict
    ) -> bool:
        """
        Send notification through this channel.

        Args:
            level: Notification severity ("error", "success", "info")
            title: Notification title
            message: Main message body
            details: Additional structured data (dict)

        Returns:
            True if notification was successfully sent, False otherwise
        """
        ...
