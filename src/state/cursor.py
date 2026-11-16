"""SQLite-based cursor store for download state management.

Replaces YAML with SQLite for better concurrency, reliability, and crash recovery.
Uses WAL mode for concurrent access and implements retry logic for database locking.
"""

import shutil
import sqlite3
import tempfile
import time
import yaml
from pathlib import Path
from typing import Optional


class StateError(Exception):
    """Exception raised for state-related failures (corruption, locking, etc.)."""
    pass


def open_sqlite(db_path: str, *, ephemeral: bool = False) -> sqlite3.Connection:
    """Open a SQLite connection, optionally as an in-memory clone.

    When ephemeral is true, the on-disk file is opened read-only (if it
    exists) and copied into memory. The session directory, state.db, and
    WAL files are never created or written.
    """
    if ephemeral:
        # Copy the file and any WAL/SHM sidecars to a temp dir, then open the
        # copy. Opening the original with mode=ro can still create sidecars.
        conn = sqlite3.connect(":memory:")
        path = Path(db_path)
        if path.is_file():
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / path.name
                shutil.copyfile(path, dest)
                for suffix in ("-wal", "-shm"):
                    side = Path(str(path) + suffix)
                    if side.is_file():
                        shutil.copyfile(side, Path(str(dest) + suffix))
                src = sqlite3.connect(dest)
                try:
                    src.backup(conn)
                finally:
                    src.close()
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")

    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result[0] != "ok":
        raise StateError(f"Database integrity check failed: {result[0]}")
    return conn


class CursorStore:
    """SQLite-based state tracking with atomic operations and crash recovery.

    Features:
    - WAL mode for concurrent access
    - Atomic transactions for updates
    - Retry logic for "database is locked" errors
    - Integrity checking on initialization
    - YAML migration support for existing state files
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
        """Advance cursor value for a source with atomic transaction.

        The cursor is monotonic: setting a value lower than the stored one is
        a no-op. Downloads complete out of order under concurrency, so without
        this guard the last writer would win and the cursor could move
        backwards, causing already-processed messages to be rescanned.
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
                        last_message_id = MAX(last_message_id, excluded.last_message_id),
                        updated_at = CASE
                            WHEN excluded.last_message_id > last_message_id
                            THEN CURRENT_TIMESTAMP
                            ELSE updated_at
                        END
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
