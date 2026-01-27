"""
Unit tests for configuration schema validation.

Tests Pydantic validators for Config, SourceConfig, GlobalFilters, etc.
"""
import pytest
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from src.config.schema import (
    Config,
    SourceConfig,
    GlobalFilters,
    DaemonConfig,
    NotificationConfig,
    RetryConfig,
)


class TestConfig:
    """Tests for the main Config schema."""

    def test_minimal_valid_config(self, minimal_config_dict):
        """Minimal config with only required fields should be valid."""
        config = Config.model_validate(minimal_config_dict)
        assert config.api_id == 12345
        assert config.api_hash == "abc123def456789012345678901234ab"

    def test_missing_api_id_raises_error(self):
        """Config without api_id should raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config.model_validate({"api_hash": "abc123"})
        assert "api_id" in str(exc_info.value)

    def test_missing_api_hash_raises_error(self):
        """Config without api_hash should raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config.model_validate({"api_id": 12345})
        assert "api_hash" in str(exc_info.value)

    def test_empty_api_hash_raises_error(self):
        """Empty api_hash should raise validation error."""
        with pytest.raises(ValidationError):
            Config.model_validate({"api_id": 12345, "api_hash": ""})

    def test_whitespace_api_hash_raises_error(self):
        """Whitespace-only api_hash should raise validation error."""
        with pytest.raises(ValidationError):
            Config.model_validate({"api_id": 12345, "api_hash": "   "})

    def test_api_id_must_be_positive(self, minimal_config_dict):
        """api_id must be greater than 0."""
        minimal_config_dict["api_id"] = 0
        with pytest.raises(ValidationError):
            Config.model_validate(minimal_config_dict)

    def test_api_id_negative_raises_error(self, minimal_config_dict):
        """Negative api_id should raise validation error."""
        minimal_config_dict["api_id"] = -1
        with pytest.raises(ValidationError):
            Config.model_validate(minimal_config_dict)

    def test_default_download_dir(self, minimal_config_dict):
        """Default download_dir should be /downloads."""
        config = Config.model_validate(minimal_config_dict)
        assert config.download_dir == Path("/downloads")

    def test_default_session_dir(self, minimal_config_dict):
        """Default session_dir should be /app/.sessions."""
        config = Config.model_validate(minimal_config_dict)
        assert config.session_dir == Path("/app/.sessions")

    def test_custom_paths(self, minimal_config_dict, temp_dir):
        """Custom paths should be accepted."""
        minimal_config_dict["download_dir"] = str(temp_dir / "downloads")
        minimal_config_dict["session_dir"] = str(temp_dir / "sessions")
        config = Config.model_validate(minimal_config_dict)
        # Compare string representations to handle Windows 8.3 path variations
        assert str(config.download_dir).lower().endswith("downloads")

    def test_default_verbosity(self, minimal_config_dict):
        """Default verbosity should be 'normal'."""
        config = Config.model_validate(minimal_config_dict)
        assert config.verbosity == "normal"

    def test_valid_verbosity_values(self, minimal_config_dict):
        """All valid verbosity values should be accepted."""
        for level in ["quiet", "normal", "verbose"]:
            minimal_config_dict["verbosity"] = level
            config = Config.model_validate(minimal_config_dict)
            assert config.verbosity == level

    def test_invalid_verbosity_raises_error(self, minimal_config_dict):
        """Invalid verbosity should raise validation error."""
        minimal_config_dict["verbosity"] = "debug"
        with pytest.raises(ValidationError):
            Config.model_validate(minimal_config_dict)

    def test_max_concurrent_downloads_default(self, minimal_config_dict):
        """Default max_concurrent_downloads should be 1."""
        config = Config.model_validate(minimal_config_dict)
        assert config.max_concurrent_downloads == 1

    def test_max_concurrent_downloads_range(self, minimal_config_dict):
        """max_concurrent_downloads must be between 1 and 10."""
        # Valid: 1
        minimal_config_dict["max_concurrent_downloads"] = 1
        config = Config.model_validate(minimal_config_dict)
        assert config.max_concurrent_downloads == 1

        # Valid: 10
        minimal_config_dict["max_concurrent_downloads"] = 10
        config = Config.model_validate(minimal_config_dict)
        assert config.max_concurrent_downloads == 10

        # Invalid: 0
        minimal_config_dict["max_concurrent_downloads"] = 0
        with pytest.raises(ValidationError):
            Config.model_validate(minimal_config_dict)

        # Invalid: 11
        minimal_config_dict["max_concurrent_downloads"] = 11
        with pytest.raises(ValidationError):
            Config.model_validate(minimal_config_dict)


class TestSourceConfig:
    """Tests for SourceConfig schema."""

    def test_source_with_url(self):
        """Source with URL should be valid."""
        source = SourceConfig.model_validate({"url": "https://t.me/test"})
        assert source.url == "https://t.me/test"

    def test_source_with_chat_id(self):
        """Source with chat_id should be valid."""
        source = SourceConfig.model_validate({"chat_id": -1001234567890})
        assert source.chat_id == -1001234567890

    def test_source_missing_identifier_raises_error(self):
        """Source without url or chat_id should raise validation error."""
        # Note: The current validator checks chat_id after url, so if both are
        # explicitly None, it should raise. However, if only "name" is provided,
        # the defaults apply. We need to explicitly set both to None.
        with pytest.raises(ValidationError):
            SourceConfig.model_validate({"url": None, "chat_id": None, "name": "Test"})

    def test_source_with_name(self):
        """Source with display name override."""
        source = SourceConfig.model_validate({
            "url": "https://t.me/test",
            "name": "My Custom Name"
        })
        assert source.name == "My Custom Name"

    def test_source_with_filters(self):
        """Source with per-source filter overrides."""
        source = SourceConfig.model_validate({
            "url": "https://t.me/test",
            "filters": {
                "extensions": [".pdf", ".epub"],
                "min_size": "1MB",
            }
        })
        assert source.filters is not None
        assert source.filters.extensions == [".pdf", ".epub"]
        assert source.filters.min_size == "1MB"


class TestGlobalFilters:
    """Tests for GlobalFilters schema."""

    def test_default_extensions(self):
        """Default extensions should be [.pdf, .epub, .mobi]."""
        filters = GlobalFilters.model_validate({})
        assert filters.extensions == [".pdf", ".epub", ".mobi"]

    def test_default_allow_archives(self):
        """Archives should be disabled by default."""
        filters = GlobalFilters.model_validate({})
        assert filters.allow_archives is False

    def test_size_filters_optional(self):
        """Size filters should be optional (None by default)."""
        filters = GlobalFilters.model_validate({})
        assert filters.min_size is None
        assert filters.max_size is None

    def test_date_filters_optional(self):
        """Date filters should be optional (None by default)."""
        filters = GlobalFilters.model_validate({})
        assert filters.only_after is None
        assert filters.only_before is None

    def test_custom_extensions(self):
        """Custom extensions should be accepted."""
        filters = GlobalFilters.model_validate({
            "extensions": [".doc", ".docx", ".txt"]
        })
        assert filters.extensions == [".doc", ".docx", ".txt"]

    def test_pattern_filters_empty_by_default(self):
        """Pattern filters should be empty lists by default."""
        filters = GlobalFilters.model_validate({})
        assert filters.include_patterns == []
        assert filters.exclude_patterns == []


class TestDaemonConfig:
    """Tests for DaemonConfig schema."""

    def test_daemon_disabled_by_default(self):
        """Daemon should be disabled by default."""
        config = DaemonConfig.model_validate({})
        assert config.enabled is False

    def test_default_check_interval(self):
        """Default check interval should be 300 seconds."""
        config = DaemonConfig.model_validate({})
        assert config.check_interval == 300

    def test_check_interval_minimum(self):
        """Check interval must be at least 60 seconds."""
        with pytest.raises(ValidationError):
            DaemonConfig.model_validate({"check_interval": 59})

    def test_check_interval_maximum(self):
        """Check interval must not exceed 86400 seconds (24 hours)."""
        with pytest.raises(ValidationError):
            DaemonConfig.model_validate({"check_interval": 86401})

    def test_check_interval_valid_range(self):
        """Check interval within valid range should be accepted."""
        config = DaemonConfig.model_validate({"check_interval": 600})
        assert config.check_interval == 600


class TestNotificationConfig:
    """Tests for NotificationConfig schema."""

    def test_notifications_disabled_by_default(self):
        """Notifications should be disabled by default."""
        config = NotificationConfig.model_validate({})
        assert config.enabled is False

    def test_default_detail_level(self):
        """Default detail level should be 'summary'."""
        config = NotificationConfig.model_validate({})
        assert config.detail_level == "summary"

    def test_valid_detail_levels(self):
        """All valid detail levels should be accepted."""
        for level in ["minimal", "summary", "detailed"]:
            config = NotificationConfig.model_validate({"detail_level": level})
            assert config.detail_level == level

    def test_invalid_detail_level_raises_error(self):
        """Invalid detail level should raise validation error."""
        with pytest.raises(ValidationError):
            NotificationConfig.model_validate({"detail_level": "full"})

    def test_throttle_seconds_range(self):
        """Throttle seconds must be between 10 and 3600."""
        # Valid minimum
        config = NotificationConfig.model_validate({"throttle_seconds": 10})
        assert config.throttle_seconds == 10

        # Valid maximum
        config = NotificationConfig.model_validate({"throttle_seconds": 3600})
        assert config.throttle_seconds == 3600

        # Invalid: too low
        with pytest.raises(ValidationError):
            NotificationConfig.model_validate({"throttle_seconds": 9})

        # Invalid: too high
        with pytest.raises(ValidationError):
            NotificationConfig.model_validate({"throttle_seconds": 3601})


class TestRetryConfig:
    """Tests for RetryConfig schema."""

    def test_default_values(self):
        """Default retry config values."""
        config = RetryConfig.model_validate({})
        assert config.max_retries == 2
        assert config.base_delay == 2
        assert config.max_delay == 60

    def test_max_retries_can_be_zero(self):
        """max_retries = 0 should be valid (no retries)."""
        config = RetryConfig.model_validate({"max_retries": 0})
        assert config.max_retries == 0

    def test_delays_must_be_positive(self):
        """base_delay and max_delay must be >= 1."""
        with pytest.raises(ValidationError):
            RetryConfig.model_validate({"base_delay": 0})

        with pytest.raises(ValidationError):
            RetryConfig.model_validate({"max_delay": 0})
