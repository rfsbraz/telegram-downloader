"""
Unit tests for CursorStore (SQLite-based state management).

Tests SQLite operations, WAL mode, context manager, YAML migration.
"""
import pytest
import tempfile
from pathlib import Path

from src.state.cursor import CursorStore, StateError


class TestCursorStoreBasics:
    """Basic CursorStore operations."""

    def test_create_store(self, memory_db):
        """CursorStore should create database file."""
        store = CursorStore(memory_db)
        assert Path(memory_db).exists()
        store.close()

    def test_creates_parent_directory(self, temp_dir):
        """CursorStore should create parent directories if needed."""
        nested_path = temp_dir / "nested" / "dir" / "cursor.db"
        store = CursorStore(str(nested_path))
        assert nested_path.exists()
        store.close()

    def test_get_returns_default_for_missing_key(self, memory_db):
        """get() should return default when key doesn't exist."""
        with CursorStore(memory_db) as store:
            result = store.get("nonexistent_key", default=0)
            assert result == 0

    def test_get_returns_custom_default(self, memory_db):
        """get() should return custom default value."""
        with CursorStore(memory_db) as store:
            result = store.get("nonexistent_key", default=100)
            assert result == 100

    def test_set_and_get(self, memory_db):
        """set() should store value retrievable by get()."""
        with CursorStore(memory_db) as store:
            store.set("test_source", 12345)
            result = store.get("test_source")
            assert result == 12345

    def test_set_updates_existing(self, memory_db):
        """set() should update existing values (UPSERT)."""
        with CursorStore(memory_db) as store:
            store.set("test_source", 100)
            assert store.get("test_source") == 100

            store.set("test_source", 200)
            assert store.get("test_source") == 200

    def test_set_is_monotonic(self, memory_db):
        """set() must never move the cursor backwards.

        Concurrent downloads complete out of order; a lower message ID
        finishing last must not regress the cursor.
        """
        with CursorStore(memory_db) as store:
            store.set("test_source", 300)
            store.set("test_source", 100)
            assert store.get("test_source") == 300

            store.set("test_source", 400)
            assert store.get("test_source") == 400

    def test_multiple_sources(self, memory_db):
        """Should handle multiple source keys independently."""
        with CursorStore(memory_db) as store:
            store.set("source_1", 100)
            store.set("source_2", 200)
            store.set("source_3", 300)

            assert store.get("source_1") == 100
            assert store.get("source_2") == 200
            assert store.get("source_3") == 300


class TestCursorStoreContextManager:
    """Context manager functionality."""

    def test_context_manager_closes_connection(self, memory_db):
        """Context manager should close connection on exit."""
        with CursorStore(memory_db) as store:
            store.set("test", 123)
        # After context exit, connection should be closed
        assert store._connection is None

    def test_operations_after_close_raise_error(self, memory_db):
        """Operations after close should raise StateError."""
        store = CursorStore(memory_db)
        store.close()

        with pytest.raises(StateError):
            store.get("test")

        with pytest.raises(StateError):
            store.set("test", 123)


class TestCursorStorePersistence:
    """Data persistence across sessions."""

    def test_data_persists_across_sessions(self, memory_db):
        """Data should persist when store is reopened."""
        # First session: write data
        with CursorStore(memory_db) as store:
            store.set("persistent_key", 999)

        # Second session: read data
        with CursorStore(memory_db) as store:
            result = store.get("persistent_key")
            assert result == 999


class TestCursorStoreYamlMigration:
    """YAML migration functionality."""

    def test_migrate_from_yaml(self, temp_dir, memory_db):
        """Should import data from existing YAML file."""
        # Create YAML file with state data
        yaml_file = temp_dir / "state.yaml"
        yaml_file.write_text('{"source_1": 100, "source_2": 200}')

        with CursorStore(memory_db) as store:
            store.migrate_from_yaml(str(yaml_file))

            assert store.get("source_1") == 100
            assert store.get("source_2") == 200

    def test_migrate_nonexistent_yaml_is_noop(self, memory_db):
        """Migrating from nonexistent YAML should do nothing."""
        with CursorStore(memory_db) as store:
            # Should not raise
            store.migrate_from_yaml("/nonexistent/path/state.yaml")

    def test_migrate_invalid_yaml_raises_error(self, temp_dir, memory_db):
        """Invalid YAML format should raise StateError."""
        yaml_file = temp_dir / "invalid.yaml"
        yaml_file.write_text("not: valid: yaml: [")

        with CursorStore(memory_db) as store:
            with pytest.raises(StateError) as exc_info:
                store.migrate_from_yaml(str(yaml_file))
            assert "Failed to read YAML" in str(exc_info.value)

    def test_migrate_non_dict_yaml_raises_error(self, temp_dir, memory_db):
        """YAML that's not a dict should raise StateError."""
        yaml_file = temp_dir / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")

        with CursorStore(memory_db) as store:
            with pytest.raises(StateError) as exc_info:
                store.migrate_from_yaml(str(yaml_file))
            assert "must contain a dictionary" in str(exc_info.value)


class TestCursorStoreIntegrity:
    """Database integrity and error handling."""

    def test_wal_mode_enabled(self, memory_db):
        """WAL mode should be enabled for concurrent access."""
        with CursorStore(memory_db) as store:
            cursor = store._connection.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"

    def test_handles_special_characters_in_key(self, memory_db):
        """Should handle special characters in source keys."""
        with CursorStore(memory_db) as store:
            key = "chat_-1001234567890:topic_5"
            store.set(key, 999)
            assert store.get(key) == 999
