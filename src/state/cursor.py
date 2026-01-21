"""SQLite-based cursor store for download state management.

Replaces YAML with SQLite for better concurrency, reliability, and crash recovery.
Uses WAL mode for concurrent access and implements retry logic for database locking.
"""

import sqlite3
import time
import yaml
from pathlib import Path
from typing import Optional


class StateError(Exception):
    """Exception raised for state-related failures (corruption, locking, etc.)."""
    pass


class CursorStore:
    """SQLite-based state tracking with atomic operations and crash recovery.

    Features:
    - WAL mode for concurrent access
    - Atomic transactions for updates
    - Retry logic for "database is locked" errors
    - Integrity checking on initialization
    - YAML migration support for existing state files
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
            CREATE TABLE IF NOT EXISTS cursors (
                source_key TEXT PRIMARY KEY,
                last_message_id INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._connection.commit()

    def get(self, source_key: str, default: int = 0) -> int:
        """Get cursor value for a source.

        Args:
            source_key: Unique identifier for source (e.g., "chat_123:topic_5")
            default: Value to return if key not found

        Returns:
            Cursor value (message ID) or default if not found
        """
        if not self._connection:
            raise StateError("Database connection is closed")

        cursor = self._connection.execute(
            "SELECT last_message_id FROM cursors WHERE source_key = ?",
            (source_key,)
        )
        row = cursor.fetchone()
        return row[0] if row else default

    def set(self, source_key: str, message_id: int) -> None:
        """Set cursor value for a source with atomic transaction.

        Uses UPSERT (INSERT OR REPLACE) to handle both new and existing keys.
        Implements retry logic for database locking errors.

        Args:
            source_key: Unique identifier for source
            message_id: Message ID to store as cursor

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
                    INSERT INTO cursors (source_key, last_message_id, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_key) DO UPDATE SET
                        last_message_id = excluded.last_message_id,
                        updated_at = CURRENT_TIMESTAMP
                """, (source_key, message_id))
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
                raise StateError(f"Unexpected error during set: {e}")

        raise StateError(f"Failed to set cursor after {max_retries} retries (database locked)")

    def migrate_from_yaml(self, yaml_path: str) -> None:
        """Import existing YAML state into SQLite.

        Reads YAML file with structure like:
            {"123:5": 999, "456:7": 1234}

        And imports each key-value pair into the database.

        Args:
            yaml_path: Path to existing YAML state file

        Raises:
            StateError: If YAML file cannot be read or migration fails
        """
        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            return  # Nothing to migrate

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            raise StateError(f"Failed to read YAML file: {e}")

        if not isinstance(data, dict):
            raise StateError(f"YAML file must contain a dictionary, got {type(data)}")

        # Import each entry
        for source_key, message_id in data.items():
            try:
                self.set(str(source_key), int(message_id))
            except (ValueError, TypeError) as e:
                raise StateError(f"Invalid data in YAML for key '{source_key}': {e}")

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
