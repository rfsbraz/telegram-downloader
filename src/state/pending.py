"""SQLite-based pending downloads queue.

Caches message IDs that still need downloading so that older messages
are not permanently orphaned when max_downloads_per_run cuts a scan short.
Uses WAL mode for concurrent access alongside CursorStore/DownloadHistory.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional

from .cursor import StateError


class PendingDownloads:
    """Persistent queue of message IDs awaiting download.

    Features:
    - WAL mode for concurrent access with CursorStore/DownloadHistory
    - Oldest-first retrieval ensures fair processing order
    - Idempotent add_batch (INSERT OR IGNORE)
    - Retry logic for "database is locked" errors
    - Integrity checking on initialization
    """

    def __init__(self, db_path: str):
        """Initialize SQLite connection with WAL mode.

        Args:
            db_path: Path to SQLite database file

        Raises:
            StateError: If database is corrupted or initialization fails
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

        # Create parent directory if needed
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect and initialize
        self._connection = sqlite3.connect(db_path)

        # Enable WAL mode for concurrent access
        self._connection.execute("PRAGMA journal_mode=WAL")

        # Check database integrity
        result = self._connection.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            raise StateError(f"Database integrity check failed: {result[0]}")

        # Create table if not exists
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS pending_downloads (
                cursor_key TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (cursor_key, message_id)
            )
        """)
        # Migrate databases created before the attempts column existed
        try:
            self._connection.execute(
                "ALTER TABLE pending_downloads ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists
        self._connection.commit()

    def _check_connection(self) -> None:
        """Raise StateError if connection is closed."""
        if not self._connection:
            raise StateError("Database connection is closed")

    def add_batch(self, cursor_key: str, message_ids: list[int]) -> None:
        """Add message IDs to the pending queue (idempotent).

        Uses INSERT OR IGNORE so duplicates are silently skipped.

        Args:
            cursor_key: Source cursor key (e.g., "chat_123:topic_0")
            message_ids: List of message IDs to enqueue

        Raises:
            StateError: If database operation fails
        """
        self._check_connection()
        if not message_ids:
            return

        max_retries = 3
        delays = [0.1, 0.2, 0.4]

        for attempt in range(max_retries):
            try:
                self._connection.execute("BEGIN")
                self._connection.executemany(
                    "INSERT OR IGNORE INTO pending_downloads (cursor_key, message_id) VALUES (?, ?)",
                    [(cursor_key, mid) for mid in message_ids],
                )
                self._connection.commit()
                return
            except sqlite3.OperationalError as e:
                self._connection.rollback()
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                raise StateError(f"Database operation failed: {e}")
            except Exception as e:
                self._connection.rollback()
                raise StateError(f"Unexpected error during add_batch: {e}")

        raise StateError(f"Failed to add batch after {max_retries} retries (database locked)")

    def get_oldest(
        self, cursor_key: str, limit: int, max_attempts: Optional[int] = None
    ) -> list[int]:
        """Get the oldest pending message IDs for a source.

        Args:
            cursor_key: Source cursor key
            limit: Maximum number of IDs to return
            max_attempts: If set, exclude entries with attempts >= max_attempts
                (exhausted entries stay in the table for inspection but are
                no longer scheduled for download)

        Returns:
            List of message IDs ordered ascending (oldest first)

        Raises:
            StateError: If database operation fails
        """
        self._check_connection()
        if max_attempts is not None:
            cursor = self._connection.execute(
                "SELECT message_id FROM pending_downloads "
                "WHERE cursor_key = ? AND attempts < ? "
                "ORDER BY message_id ASC LIMIT ?",
                (cursor_key, max_attempts, limit),
            )
        else:
            cursor = self._connection.execute(
                "SELECT message_id FROM pending_downloads "
                "WHERE cursor_key = ? ORDER BY message_id ASC LIMIT ?",
                (cursor_key, limit),
            )
        return [row[0] for row in cursor.fetchall()]

    def increment_attempts(self, cursor_key: str, message_ids: list[int]) -> None:
        """Increment the attempt counter for failed downloads.

        Args:
            cursor_key: Source cursor key
            message_ids: List of message IDs that failed to download

        Raises:
            StateError: If database operation fails
        """
        self._check_connection()
        if not message_ids:
            return

        max_retries = 3
        delays = [0.1, 0.2, 0.4]

        for attempt in range(max_retries):
            try:
                self._connection.execute("BEGIN")
                placeholders = ",".join("?" * len(message_ids))
                self._connection.execute(
                    f"UPDATE pending_downloads SET attempts = attempts + 1 "
                    f"WHERE cursor_key = ? AND message_id IN ({placeholders})",
                    [cursor_key] + list(message_ids),
                )
                self._connection.commit()
                return
            except sqlite3.OperationalError as e:
                self._connection.rollback()
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                raise StateError(f"Database operation failed: {e}")
            except Exception as e:
                self._connection.rollback()
                raise StateError(f"Unexpected error during increment_attempts: {e}")

        raise StateError(f"Failed to increment attempts after {max_retries} retries (database locked)")

    def count_exhausted(self, cursor_key: str, max_attempts: int) -> int:
        """Count entries that exceeded the attempt limit (dead-lettered).

        Args:
            cursor_key: Source cursor key
            max_attempts: Attempt limit

        Returns:
            Number of entries with attempts >= max_attempts
        """
        self._check_connection()
        cursor = self._connection.execute(
            "SELECT COUNT(*) FROM pending_downloads "
            "WHERE cursor_key = ? AND attempts >= ?",
            (cursor_key, max_attempts),
        )
        return cursor.fetchone()[0]

    def remove_batch(self, cursor_key: str, message_ids: list[int]) -> None:
        """Remove processed message IDs from the pending queue.

        Args:
            cursor_key: Source cursor key
            message_ids: List of message IDs to remove

        Raises:
            StateError: If database operation fails
        """
        self._check_connection()
        if not message_ids:
            return

        max_retries = 3
        delays = [0.1, 0.2, 0.4]

        for attempt in range(max_retries):
            try:
                self._connection.execute("BEGIN")
                placeholders = ",".join("?" * len(message_ids))
                self._connection.execute(
                    f"DELETE FROM pending_downloads WHERE cursor_key = ? AND message_id IN ({placeholders})",
                    [cursor_key] + list(message_ids),
                )
                self._connection.commit()
                return
            except sqlite3.OperationalError as e:
                self._connection.rollback()
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                raise StateError(f"Database operation failed: {e}")
            except Exception as e:
                self._connection.rollback()
                raise StateError(f"Unexpected error during remove_batch: {e}")

        raise StateError(f"Failed to remove batch after {max_retries} retries (database locked)")

    def count(self, cursor_key: str, max_attempts: Optional[int] = None) -> int:
        """Count pending message IDs for a source.

        Args:
            cursor_key: Source cursor key
            max_attempts: If set, count only entries still eligible for
                download (attempts < max_attempts)

        Returns:
            Number of pending messages
        """
        self._check_connection()
        if max_attempts is not None:
            cursor = self._connection.execute(
                "SELECT COUNT(*) FROM pending_downloads "
                "WHERE cursor_key = ? AND attempts < ?",
                (cursor_key, max_attempts),
            )
        else:
            cursor = self._connection.execute(
                "SELECT COUNT(*) FROM pending_downloads WHERE cursor_key = ?",
                (cursor_key,),
            )
        return cursor.fetchone()[0]

    def has_pending(self, cursor_key: str) -> bool:
        """Check if a source has any pending downloads.

        Args:
            cursor_key: Source cursor key

        Returns:
            True if there are pending downloads
        """
        self._check_connection()
        cursor = self._connection.execute(
            "SELECT 1 FROM pending_downloads WHERE cursor_key = ? LIMIT 1",
            (cursor_key,),
        )
        return cursor.fetchone() is not None

    def get_max_message_id(self, cursor_key: str) -> int:
        """Get the highest pending message ID for a source.

        Used to determine where to start scanning for new arrivals
        above the existing pending range.

        Args:
            cursor_key: Source cursor key

        Returns:
            Highest message ID, or 0 if no pending entries
        """
        self._check_connection()
        cursor = self._connection.execute(
            "SELECT MAX(message_id) FROM pending_downloads WHERE cursor_key = ?",
            (cursor_key,),
        )
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically close connection."""
        self.close()
        return False
