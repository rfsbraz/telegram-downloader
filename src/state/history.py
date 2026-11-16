"""SQLite-based download history for persistent deduplication.

Tracks downloaded files by Telegram's file_unique_id to prevent re-downloads
even after files are moved, renamed, or processed by external tools.
Uses WAL mode for concurrent access alongside CursorStore on the same database.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional

from .cursor import StateError, open_sqlite


class DownloadHistory:
    """Persistent download history using SQLite.

    Features:
    - Tracks files by Telegram's file_unique_id (stable, content-unique)
    - WAL mode for concurrent access with CursorStore
    - Retry logic for "database is locked" errors
    - Integrity checking on initialization
    """

    def __init__(self, db_path: str, *, ephemeral: bool = False):
        """Initialize SQLite connection with WAL mode.

        Args:
            db_path: Path to SQLite database file
            ephemeral: If true, use an in-memory clone and do not write the file

        Raises:
            StateError: If database is corrupted or initialization fails
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._connection = open_sqlite(db_path, ephemeral=ephemeral)

        # Create table if not exists
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS download_history (
                file_unique_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                source_key TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._connection.commit()

    def contains(self, file_unique_id: str) -> bool:
        """Check if a file has been previously downloaded.

        Args:
            file_unique_id: Telegram's stable unique file identifier

        Returns:
            True if file was previously downloaded
        """
        if not self._connection:
            raise StateError("Database connection is closed")

        cursor = self._connection.execute(
            "SELECT 1 FROM download_history WHERE file_unique_id = ?",
            (file_unique_id,)
        )
        return cursor.fetchone() is not None

    def record(
        self,
        file_unique_id: str,
        file_name: str,
        file_size: int,
        source_key: str,
        message_id: int,
    ) -> None:
        """Record a downloaded file in history.

        Uses UPSERT to handle re-recording the same file gracefully.
        Implements retry logic for database locking errors.

        Args:
            file_unique_id: Telegram's stable unique file identifier
            file_name: Original filename
            file_size: File size in bytes
            source_key: Source cursor key (e.g., "chat_123:topic_5")
            message_id: Telegram message ID

        Raises:
            StateError: If all retry attempts exhausted or other database error
        """
        if not self._connection:
            raise StateError("Database connection is closed")

        max_retries = 3
        delays = [0.1, 0.2, 0.4]  # Exponential backoff

        for attempt in range(max_retries):
            try:
                self._connection.execute("BEGIN")
                self._connection.execute("""
                    INSERT INTO download_history
                        (file_unique_id, file_name, file_size, source_key, message_id, downloaded_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(file_unique_id) DO UPDATE SET
                        file_name = excluded.file_name,
                        file_size = excluded.file_size,
                        source_key = excluded.source_key,
                        message_id = excluded.message_id,
                        downloaded_at = CURRENT_TIMESTAMP
                """, (file_unique_id, file_name, file_size, source_key, message_id))
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
                raise StateError(f"Unexpected error during record: {e}")

        raise StateError(f"Failed to record download after {max_retries} retries (database locked)")

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
