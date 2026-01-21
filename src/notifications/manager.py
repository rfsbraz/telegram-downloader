"""Central notification orchestration with throttling."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.notifications.base import Notifier


logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Central notification orchestrator with throttling and error handling.

    Features:
    - Pluggable notification channels (Discord, webhooks, etc.)
    - Automatic throttling to prevent spam (one notification per level per interval)
    - Critical error bypass (force=True skips throttling)
    - Parallel delivery to all channels
    - Individual channel failures don't block other channels

    Throttling logic:
    - Tracks last notification time per severity level
    - Skips notification if within throttle window
    - Critical errors (force=True) always send immediately
    """

    def __init__(
        self,
        notifiers: list[Notifier],
        throttle_seconds: int = 60
    ):
        """
        Initialize notification manager.

        Args:
            notifiers: List of notification channel implementations
            throttle_seconds: Minimum seconds between notifications of same level
        """
        self.notifiers = notifiers
        self.throttle_seconds = throttle_seconds
        self.last_notification: dict[str, datetime] = {}
        self.log = logging.getLogger("notifications")

    async def notify(
        self,
        level: str,
        title: str,
        message: str,
        details: Optional[dict] = None,
        force: bool = False
    ):
        """
        Send notification through all configured channels.

        Throttling behavior:
        - Checks last notification time for this level
        - Skips if within throttle window (unless force=True)
        - Updates throttle timestamp after successful send

        Args:
            level: Notification severity ("error", "success", "info")
            title: Notification title
            message: Main message body
            details: Additional structured data (optional)
            force: Skip throttling for critical errors (default: False)

        Example:
            # Normal notification (subject to throttling)
            await manager.notify("success", "Check Complete", "Downloaded 5 files")

            # Critical error (bypasses throttling)
            await manager.notify("error", "Auth Failed", "Invalid credentials", force=True)
        """
        # Throttling check (skip for critical errors)
        if not force and not self._should_notify(level):
            self.log.debug(f"Throttling {level} notification: {title}")
            return

        # Send to all channels in parallel
        results = await asyncio.gather(
            *[n.send(level, title, message, details or {}) for n in self.notifiers],
            return_exceptions=True
        )

        # Log individual channel failures
        success_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.log.error(f"Notification channel {i} failed: {result}")
            elif result:
                success_count += 1

        # Update throttle timestamp if at least one channel succeeded
        if success_count > 0:
            self.last_notification[level] = datetime.now()
            self.log.debug(
                f"Notification sent: {level} - {title} "
                f"({success_count}/{len(self.notifiers)} channels)"
            )

    def _should_notify(self, level: str) -> bool:
        """
        Check if enough time has passed since last notification of this level.

        Args:
            level: Notification severity level

        Returns:
            True if notification should be sent, False if throttled
        """
        last = self.last_notification.get(level)
        if not last:
            return True

        elapsed = (datetime.now() - last).total_seconds()
        return elapsed >= self.throttle_seconds
