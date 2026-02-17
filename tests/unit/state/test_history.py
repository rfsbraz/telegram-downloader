"""
Unit tests for DownloadHistory (persistent download deduplication).

Tests SQLite operations, WAL mode, context manager, coexistence with CursorStore.
"""
import pytest
from pathlib import Path

from src.state.cursor import CursorStore, StateError
from src.state.history import DownloadHistory


class TestDownloadHistoryBasics:
    """Basic DownloadHistory operations."""

    def test_create_history(self, history_db):
        """DownloadHistory should create database file."""
        history = DownloadHistory(history_db)
        assert Path(history_db).exists()
        history.close()

    def test_creates_parent_directory(self, temp_dir):
        """DownloadHistory should create parent directories if needed."""
        nested_path = temp_dir / "nested" / "dir" / "history.db"
        history = DownloadHistory(str(nested_path))
        assert nested_path.exists()
        history.close()

    def test_contains_returns_false_for_unknown(self, history_db):
        """contains() should return False for unknown file_unique_id."""
        with DownloadHistory(history_db) as history:
            assert history.contains("unknown_id") is False

    def test_contains_returns_true_after_record(self, history_db):
        """contains() should return True after recording a file."""
        with DownloadHistory(history_db) as history:
            history.record("unique_123", "test.pdf", 1024, "chat_1:topic_0", 42)
            assert history.contains("unique_123") is True

    def test_record_and_check_multiple_files(self, history_db):
        """Should handle multiple independent file records."""
        with DownloadHistory(history_db) as history:
            history.record("id_a", "file_a.pdf", 100, "src_1", 1)
            history.record("id_b", "file_b.epub", 200, "src_1", 2)
            history.record("id_c", "file_c.mobi", 300, "src_2", 3)

            assert history.contains("id_a") is True
            assert history.contains("id_b") is True
            assert history.contains("id_c") is True
            assert history.contains("id_d") is False

    def test_idempotent_re_recording(self, history_db):
        """Recording the same file_unique_id twice should update, not fail."""
        with DownloadHistory(history_db) as history:
            history.record("unique_1", "old_name.pdf", 100, "src_1", 1)
            # Re-record with different metadata (e.g., from a different source)
            history.record("unique_1", "new_name.pdf", 100, "src_2", 5)
            assert history.contains("unique_1") is True


class TestDownloadHistoryContextManager:
    """Context manager functionality."""

    def test_context_manager_closes_connection(self, history_db):
        """Context manager should close connection on exit."""
        with DownloadHistory(history_db) as history:
            history.record("test_id", "test.pdf", 100, "src", 1)
        assert history._connection is None

    def test_operations_after_close_raise_error(self, history_db):
        """Operations after close should raise StateError."""
        history = DownloadHistory(history_db)
        history.close()

        with pytest.raises(StateError):
            history.contains("test")

        with pytest.raises(StateError):
            history.record("test", "f.pdf", 100, "src", 1)


class TestDownloadHistoryPersistence:
    """Data persistence across sessions."""

    def test_data_persists_across_sessions(self, history_db):
        """Data should persist when history is reopened."""
        # First session: record download
        with DownloadHistory(history_db) as history:
            history.record("persist_id", "persist.pdf", 500, "src_1", 10)

        # Second session: check it's still there
        with DownloadHistory(history_db) as history:
            assert history.contains("persist_id") is True
            assert history.contains("other_id") is False


class TestDownloadHistoryCoexistence:
    """Coexistence with CursorStore on the same database."""

    def test_shares_database_with_cursor_store(self, history_db):
        """DownloadHistory and CursorStore can use the same database file."""
        # Both open connections to the same DB
        cursor_store = CursorStore(history_db)
        history = DownloadHistory(history_db)

        # Both should work independently
        cursor_store.set("source_1", 100)
        history.record("file_1", "test.pdf", 1024, "source_1", 100)

        assert cursor_store.get("source_1") == 100
        assert history.contains("file_1") is True

        cursor_store.close()
        history.close()


class TestDownloadHistoryIntegrity:
    """Database integrity and edge cases."""

    def test_wal_mode_enabled(self, history_db):
        """WAL mode should be enabled for concurrent access."""
        with DownloadHistory(history_db) as history:
            cursor = history._connection.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"

    def test_special_characters_in_filename(self, history_db):
        """Should handle special characters in filenames."""
        with DownloadHistory(history_db) as history:
            special_names = [
                "file with spaces.pdf",
                "file'with'quotes.epub",
                'file"double"quotes.mobi',
                "файл_юникод.pdf",
                "日本語ファイル.pdf",
                "file (1) [copy].pdf",
            ]
            for i, name in enumerate(special_names):
                uid = f"special_{i}"
                history.record(uid, name, 100, "src", i)
                assert history.contains(uid) is True
