"""
Unit tests for PendingDownloads (resumable download queue).

Tests SQLite operations, WAL mode, context manager, coexistence with
CursorStore/DownloadHistory on the same database.
"""
import pytest
from pathlib import Path

from src.state.cursor import CursorStore, StateError
from src.state.history import DownloadHistory
from src.state.pending import PendingDownloads


class TestPendingDownloadsBasics:
    """Basic PendingDownloads operations."""

    def test_create_pending(self, history_db):
        """PendingDownloads should create database file."""
        pending = PendingDownloads(history_db)
        assert Path(history_db).exists()
        pending.close()

    def test_creates_parent_directory(self, temp_dir):
        """PendingDownloads should create parent directories if needed."""
        nested_path = temp_dir / "nested" / "dir" / "pending.db"
        pending = PendingDownloads(str(nested_path))
        assert nested_path.exists()
        pending.close()

    def test_add_and_get_oldest(self, history_db):
        """add_batch + get_oldest should return IDs in ascending order."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [300, 100, 200])
            result = pending.get_oldest("src_1", 10)
            assert result == [100, 200, 300]

    def test_get_oldest_respects_limit(self, history_db):
        """get_oldest should return at most `limit` IDs."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [10, 20, 30, 40, 50])
            result = pending.get_oldest("src_1", 3)
            assert result == [10, 20, 30]

    def test_idempotent_add(self, history_db):
        """Adding the same IDs twice should not create duplicates."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [1, 2, 3])
            pending.add_batch("src_1", [2, 3, 4])
            result = pending.get_oldest("src_1", 100)
            assert result == [1, 2, 3, 4]

    def test_remove_batch(self, history_db):
        """remove_batch should delete specified IDs."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [10, 20, 30, 40])
            pending.remove_batch("src_1", [10, 30])
            result = pending.get_oldest("src_1", 100)
            assert result == [20, 40]

    def test_count(self, history_db):
        """count() should return the number of pending entries."""
        with PendingDownloads(history_db) as pending:
            assert pending.count("src_1") == 0
            pending.add_batch("src_1", [1, 2, 3])
            assert pending.count("src_1") == 3
            pending.remove_batch("src_1", [2])
            assert pending.count("src_1") == 2

    def test_has_pending(self, history_db):
        """has_pending() should reflect whether entries exist."""
        with PendingDownloads(history_db) as pending:
            assert pending.has_pending("src_1") is False
            pending.add_batch("src_1", [1])
            assert pending.has_pending("src_1") is True
            pending.remove_batch("src_1", [1])
            assert pending.has_pending("src_1") is False

    def test_get_max_message_id(self, history_db):
        """get_max_message_id() should return the highest ID."""
        with PendingDownloads(history_db) as pending:
            assert pending.get_max_message_id("src_1") == 0
            pending.add_batch("src_1", [10, 50, 30])
            assert pending.get_max_message_id("src_1") == 50

    def test_empty_batch_operations(self, history_db):
        """Empty lists should be no-ops."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [])
            assert pending.count("src_1") == 0
            pending.remove_batch("src_1", [])
            assert pending.count("src_1") == 0


class TestPendingDownloadsAttempts:
    """Attempt accounting and dead-lettering of repeatedly failing entries."""

    def test_new_entries_have_zero_attempts(self, history_db):
        """Fresh entries should be eligible regardless of max_attempts."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [1, 2, 3])
            assert pending.get_oldest("src_1", 10, max_attempts=1) == [1, 2, 3]

    def test_increment_attempts(self, history_db):
        """increment_attempts should only affect the given IDs."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [1, 2, 3])
            pending.increment_attempts("src_1", [2])

            # ID 2 now has 1 attempt, excluded when max_attempts=1
            assert pending.get_oldest("src_1", 10, max_attempts=1) == [1, 3]
            # Still included with a higher limit
            assert pending.get_oldest("src_1", 10, max_attempts=2) == [1, 2, 3]

    def test_exhausted_entries_excluded_from_get_oldest(self, history_db):
        """Entries at the attempt limit must not be scheduled again."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [10, 20])
            for _ in range(3):
                pending.increment_attempts("src_1", [10])

            assert pending.get_oldest("src_1", 10, max_attempts=3) == [20]
            # Exhausted entry remains in the table
            assert pending.count("src_1") == 2
            assert pending.count("src_1", max_attempts=3) == 1
            assert pending.count_exhausted("src_1", 3) == 1

    def test_increment_attempts_empty_list_is_noop(self, history_db):
        """Empty list should be a no-op."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [1])
            pending.increment_attempts("src_1", [])
            assert pending.get_oldest("src_1", 10, max_attempts=1) == [1]

    def test_increment_attempts_isolated_per_source(self, history_db):
        """Attempts on one source must not affect another."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_a", [1])
            pending.add_batch("src_b", [1])
            pending.increment_attempts("src_a", [1])

            assert pending.get_oldest("src_a", 10, max_attempts=1) == []
            assert pending.get_oldest("src_b", 10, max_attempts=1) == [1]

    def test_migrates_legacy_table_without_attempts_column(self, history_db):
        """Databases created before the attempts column should be upgraded."""
        import sqlite3

        # Simulate a legacy database (no attempts column)
        conn = sqlite3.connect(history_db)
        conn.execute("""
            CREATE TABLE pending_downloads (
                cursor_key TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (cursor_key, message_id)
            )
        """)
        conn.execute(
            "INSERT INTO pending_downloads (cursor_key, message_id) VALUES (?, ?)",
            ("src_1", 42),
        )
        conn.commit()
        conn.close()

        with PendingDownloads(history_db) as pending:
            # Legacy rows get attempts=0 and stay eligible
            assert pending.get_oldest("src_1", 10, max_attempts=5) == [42]
            pending.increment_attempts("src_1", [42])
            assert pending.count_exhausted("src_1", 1) == 1


class TestPendingDownloadsSourceIsolation:
    """Different cursor_keys should be independent."""

    def test_independent_sources(self, history_db):
        """Operations on one source should not affect another."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_a", [1, 2, 3])
            pending.add_batch("src_b", [10, 20])

            assert pending.count("src_a") == 3
            assert pending.count("src_b") == 2
            assert pending.get_max_message_id("src_a") == 3
            assert pending.get_max_message_id("src_b") == 20

            pending.remove_batch("src_a", [1, 2, 3])
            assert pending.has_pending("src_a") is False
            assert pending.has_pending("src_b") is True
            assert pending.get_oldest("src_b", 10) == [10, 20]


class TestPendingDownloadsContextManager:
    """Context manager functionality."""

    def test_context_manager_closes_connection(self, history_db):
        """Context manager should close connection on exit."""
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [1])
        assert pending._connection is None

    def test_operations_after_close_raise_error(self, history_db):
        """Operations after close should raise StateError."""
        pending = PendingDownloads(history_db)
        pending.close()

        with pytest.raises(StateError):
            pending.has_pending("src_1")

        with pytest.raises(StateError):
            pending.add_batch("src_1", [1])

        with pytest.raises(StateError):
            pending.get_oldest("src_1", 10)

        with pytest.raises(StateError):
            pending.remove_batch("src_1", [1])

        with pytest.raises(StateError):
            pending.count("src_1")

        with pytest.raises(StateError):
            pending.get_max_message_id("src_1")


class TestPendingDownloadsPersistence:
    """Data persistence across sessions."""

    def test_data_persists_across_sessions(self, history_db):
        """Data should persist when PendingDownloads is reopened."""
        # First session: add entries
        with PendingDownloads(history_db) as pending:
            pending.add_batch("src_1", [10, 20, 30])

        # Second session: verify they're still there
        with PendingDownloads(history_db) as pending:
            assert pending.count("src_1") == 3
            assert pending.get_oldest("src_1", 10) == [10, 20, 30]
            assert pending.get_max_message_id("src_1") == 30


class TestPendingDownloadsCoexistence:
    """Coexistence with CursorStore and DownloadHistory on the same database."""

    def test_shares_database_with_cursor_and_history(self, history_db):
        """All three state classes can use the same database file."""
        cursor_store = CursorStore(history_db)
        history = DownloadHistory(history_db)
        pending = PendingDownloads(history_db)

        # All should work independently
        cursor_store.set("source_1", 100)
        history.record("file_1", "test.pdf", 1024, "source_1", 100)
        pending.add_batch("source_1", [101, 102, 103])

        assert cursor_store.get("source_1") == 100
        assert history.contains("file_1") is True
        assert pending.count("source_1") == 3
        assert pending.get_oldest("source_1", 2) == [101, 102]

        cursor_store.close()
        history.close()
        pending.close()


class TestPendingDownloadsIntegrity:
    """Database integrity and edge cases."""

    def test_wal_mode_enabled(self, history_db):
        """WAL mode should be enabled for concurrent access."""
        with PendingDownloads(history_db) as pending:
            cursor = pending._connection.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"

    def test_large_batch(self, history_db):
        """Should handle large batches efficiently."""
        with PendingDownloads(history_db) as pending:
            ids = list(range(1, 1001))
            pending.add_batch("src_1", ids)
            assert pending.count("src_1") == 1000
            assert pending.get_oldest("src_1", 5) == [1, 2, 3, 4, 5]
            assert pending.get_max_message_id("src_1") == 1000
