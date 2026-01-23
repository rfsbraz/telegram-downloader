"""
Smoke tests for configuration validation.

Validates that sample configurations parse correctly.
"""
import pytest
from pathlib import Path

from src.config.schema import Config, GlobalFilters, DaemonConfig
from src.config.loader import load_config, ConfigError


@pytest.mark.smoke
class TestMinimalConfigValidation:
    """Test minimal configuration validation."""

    def test_minimal_config_validates(self):
        """Minimal configuration should validate."""
        config = Config.model_validate({
            "api_id": 12345,
            "api_hash": "abc123def456789012345678901234ab",
        })

        assert config.api_id == 12345
        assert config.api_hash is not None

    def test_default_values_populated(self):
        """Default values should be populated correctly."""
        config = Config.model_validate({
            "api_id": 12345,
            "api_hash": "abc123def456789012345678901234ab",
        })

        # Check defaults
        assert config.download_dir == Path("/downloads")
        assert config.session_dir == Path("/app/.sessions")
        assert config.verbosity == "normal"
        assert config.max_concurrent_downloads == 3
        assert config.daemon.enabled is False
        assert config.notifications.enabled is False


@pytest.mark.smoke
class TestGlobalFiltersValidation:
    """Test GlobalFilters configuration."""

    def test_default_filters(self):
        """Default global filters should be valid."""
        filters = GlobalFilters.model_validate({})

        assert filters.extensions == [".pdf", ".epub", ".mobi"]
        assert filters.allow_archives is False
        assert filters.min_size is None
        assert filters.max_size is None

    def test_custom_filters(self):
        """Custom filters should validate."""
        filters = GlobalFilters.model_validate({
            "extensions": [".pdf", ".djvu", ".fb2"],
            "allow_archives": True,
            "archive_exts": [".zip", ".rar", ".7z"],
            "min_size": "100KB",
            "max_size": "500MB",
            "include_patterns": ["*ebook*", "*book*"],
            "exclude_patterns": ["*sample*"],
        })

        assert ".djvu" in filters.extensions
        assert filters.allow_archives is True
        assert "100KB" == filters.min_size


@pytest.mark.smoke
class TestDaemonConfigValidation:
    """Test daemon configuration."""

    def test_daemon_disabled_by_default(self):
        """Daemon should be disabled by default."""
        config = DaemonConfig.model_validate({})
        assert config.enabled is False

    def test_daemon_config_with_all_options(self):
        """Full daemon configuration should validate."""
        config = DaemonConfig.model_validate({
            "enabled": True,
            "check_interval": 600,
            "health_file": "/app/health.txt",
            "log_level": "DEBUG",
        })

        assert config.enabled is True
        assert config.check_interval == 600


@pytest.mark.smoke
class TestExampleConfigFiles:
    """Test that example config files would validate."""

    def test_example_yaml_structure(self, temp_dir):
        """Example YAML structure should be valid."""
        # Create a typical example config
        example_yaml = temp_dir / "config.yaml"
        example_yaml.write_text("""
api_id: 12345
api_hash: your_api_hash_here

sources:
  - url: https://t.me/example_channel
    name: Example Channel
    filters:
      extensions: [".pdf", ".epub"]
      min_size: "1MB"

global_filters:
  extensions: [".pdf", ".epub", ".mobi"]
  allow_archives: true

daemon:
  enabled: false
  check_interval: 300

notifications:
  enabled: false
""")

        config = load_config(str(example_yaml))
        assert config.api_id == 12345
        assert len(config.sources) == 1
        assert config.global_filters.allow_archives is True
