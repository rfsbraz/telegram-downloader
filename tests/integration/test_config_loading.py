"""
Integration tests for configuration loading workflow.

Tests the complete load_config() flow with YAML and environment variables.
"""
import pytest

from src.config.loader import load_config, ConfigError
from src.config.schema import Config


class TestFullConfigLoading:
    """Full configuration loading workflow."""

    def test_complete_yaml_config(self, temp_dir, yaml_config_file, clean_env):
        """Complete YAML config should load successfully."""
        # Use forward slashes for YAML paths (works cross-platform)
        download_path = str(temp_dir / "downloads").replace("\\", "/")
        session_path = str(temp_dir / "sessions").replace("\\", "/")

        config_content = f"""
api_id: 12345
api_hash: abc123def456789012345678901234ab
phone_number: '+1234567890'
download_dir: '{download_path}'
session_dir: '{session_path}'
verbosity: verbose
max_concurrent_downloads: 5

sources:
  - url: https://t.me/channel1
    name: Channel One
    filters:
      extensions: [".pdf", ".epub"]
      min_size: "1KB"
  - url: https://t.me/channel2
    name: Channel Two

global_filters:
  extensions: [".pdf", ".epub", ".mobi"]
  allow_archives: true
  archive_exts: [".zip", ".rar"]
  min_size: "10KB"
  max_size: "500MB"

daemon:
  enabled: true
  check_interval: 600

notifications:
  enabled: true
  discord_webhook_url: https://discord.com/api/webhooks/123/abc
"""
        config_file = yaml_config_file(config_content)
        config = load_config(str(config_file))

        assert config.api_id == 12345
        assert config.verbosity == "verbose"
        assert len(config.sources) == 2
        assert config.sources[0].name == "Channel One"
        assert config.global_filters.allow_archives is True
        assert config.daemon.enabled is True
        assert config.daemon.check_interval == 600

    def test_env_vars_complete_override(self, clean_env, monkeypatch, temp_dir):
        """Complete config from environment variables."""
        monkeypatch.setenv("TDL_API_ID", "99999")
        monkeypatch.setenv("TDL_API_HASH", "env_hash_value")
        monkeypatch.setenv("TDL_DOWNLOAD_DIR", str(temp_dir / "downloads"))
        monkeypatch.setenv("TDL_DAEMON_ENABLED", "true")
        monkeypatch.setenv("TDL_DAEMON_CHECK_INTERVAL", "1200")
        monkeypatch.setenv("TDL_SOURCES_0_URL", "https://t.me/env_channel")
        monkeypatch.setenv("TDL_SOURCES_0_FILTERS_EXTENSIONS", ".pdf,.epub")

        config = load_config("/nonexistent/path.yaml")  # Will be ignored

        assert config.api_id == 99999
        assert config.api_hash == "env_hash_value"
        assert config.daemon.enabled is True
        assert config.daemon.check_interval == 1200
        assert len(config.sources) == 1
        assert config.sources[0].filters.extensions == [".pdf", ".epub"]

    def test_yaml_with_env_substitution(self, clean_env, monkeypatch, yaml_config_file):
        """YAML with ${VAR} substitution."""
        monkeypatch.setenv("MY_API_ID", "12345")
        monkeypatch.setenv("MY_API_HASH", "secret_hash_value")

        config_content = """
api_id: ${MY_API_ID}
api_hash: ${MY_API_HASH}
download_dir: ${DOWNLOAD_PATH:-/downloads}
"""
        config_file = yaml_config_file(config_content)
        config = load_config(str(config_file))

        assert config.api_id == 12345
        assert config.api_hash == "secret_hash_value"


class TestConfigValidation:
    """Configuration validation errors."""

    def test_missing_required_field(self, clean_env, yaml_config_file):
        """Missing required field should raise ConfigError."""
        config_content = """
# Missing api_hash
api_id: 12345
"""
        config_file = yaml_config_file(config_content)
        with pytest.raises(ConfigError):
            load_config(str(config_file))

    def test_invalid_field_value(self, clean_env, yaml_config_file):
        """Invalid field value should raise ConfigError."""
        config_content = """
api_id: 12345
api_hash: valid_hash
max_concurrent_downloads: 100  # Invalid: max is 10
"""
        config_file = yaml_config_file(config_content)
        with pytest.raises(ConfigError):
            load_config(str(config_file))

    def test_invalid_yaml_syntax(self, clean_env, temp_file):
        """Invalid YAML syntax should raise ConfigError."""
        config_file = temp_file("config.yaml", "invalid: yaml: [syntax")
        with pytest.raises(ConfigError):
            load_config(str(config_file))


class TestLegacyCompatibility:
    """Legacy configuration field compatibility."""

    def test_legacy_ebook_exts(self, clean_env, yaml_config_file):
        """Legacy ebook_exts field should be supported."""
        config_content = """
api_id: 12345
api_hash: valid_hash
ebook_exts: [".pdf", ".djvu"]
"""
        config_file = yaml_config_file(config_content)
        config = load_config(str(config_file))

        assert config.ebook_exts == [".pdf", ".djvu"]

    def test_legacy_env_vars(self, clean_env, monkeypatch, temp_dir):
        """Legacy API_ID/API_HASH env vars should work."""
        monkeypatch.setenv("API_ID", "11111")
        monkeypatch.setenv("API_HASH", "legacy_hash")

        yaml_content = "verbosity: normal\n"
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text(yaml_content)

        config = load_config(str(yaml_file))
        assert config.api_id == 11111
        assert config.api_hash == "legacy_hash"
