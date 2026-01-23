"""
Smoke tests for module imports.

Validates that all modules can be imported without errors.
"""
import pytest


@pytest.mark.smoke
class TestModuleImports:
    """Test that all modules can be imported."""

    def test_all_modules_import(self):
        """All main modules should import without error."""
        import_errors = []

        modules_to_import = [
            # Config module
            "src.config.schema",
            "src.config.loader",
            "src.config.url_parser",
            "src.config.source_parser",
            # State module
            "src.state.cursor",
            # Filters module
            "src.filters.base",
            "src.filters.extension",
            "src.filters.size",
            "src.filters.date",
            "src.filters.pattern",
            "src.filters.composite",
            # Security module
            "src.security.sanitizer",
            # Organization module
            "src.organization.path_builder",
            "src.organization.deduplicator",
            # Sources module
            "src.sources.base",
            "src.sources.factory",
            "src.sources.channel",
            "src.sources.group",
            "src.sources.forum_topic",
            "src.sources.private_chat",
            # Notifications module
            "src.notifications.webhook",
            # Daemon module
            "src.daemon.service",
            # Client module
            "src.client.factory",
        ]

        for module in modules_to_import:
            try:
                __import__(module)
            except ImportError as e:
                import_errors.append(f"{module}: {e}")

        if import_errors:
            pytest.fail(
                f"Failed to import {len(import_errors)} module(s):\n"
                + "\n".join(import_errors)
            )

    def test_config_schema_classes(self):
        """Config schema classes should be importable."""
        from src.config.schema import (
            Config,
            SourceConfig,
            GlobalFilters,
            DaemonConfig,
            NotificationConfig,
            RetryConfig,
        )

        # Basic sanity check
        assert Config is not None
        assert SourceConfig is not None
        assert GlobalFilters is not None

    def test_filter_classes(self):
        """Filter classes should be importable."""
        from src.filters.base import BaseFilter
        from src.filters.extension import ExtensionFilter
        from src.filters.size import SizeFilter
        from src.filters.date import DateFilter
        from src.filters.pattern import PatternFilter
        from src.filters.composite import CompositeFilter

        assert BaseFilter is not None
        assert ExtensionFilter is not None
        assert SizeFilter is not None
        assert DateFilter is not None
        assert PatternFilter is not None
        assert CompositeFilter is not None

    def test_cursor_store_importable(self):
        """CursorStore should be importable."""
        from src.state.cursor import CursorStore, StateError

        assert CursorStore is not None
        assert StateError is not None

    def test_security_functions_importable(self):
        """Security functions should be importable."""
        from src.security.sanitizer import sanitize_filename, validate_path_safety

        assert callable(sanitize_filename)
        assert callable(validate_path_safety)
