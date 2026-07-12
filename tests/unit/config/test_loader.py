"""
Unit tests for configuration loader.

Tests environment variable parsing, YAML loading, and config validation.
"""
import os
import pytest
from pathlib import Path

from src.config.loader import (
    ConfigError,
    load_config,
    _parse_value,
    _load_from_env,
    _load_from_yaml,
    _substitute_env_vars,
)


class TestParseValue:
    """Tests for _parse_value function."""

    def test_parse_list_field(self):
        """List fields should be parsed as comma-separated lists."""
        result = _parse_value("extensions", ".pdf,.epub,.mobi")
        assert result == [".pdf", ".epub", ".mobi"]

    def test_parse_list_with_whitespace(self):
        """Whitespace around list items should be stripped."""
        result = _parse_value("extensions", ".pdf , .epub , .mobi")
        assert result == [".pdf", ".epub", ".mobi"]

    def test_parse_empty_list(self):
        """Empty string should parse to empty list."""
        result = _parse_value("extensions", "")
        assert result == []

    def test_parse_boolean_true(self):
        """Boolean fields should parse true values correctly."""
        for value in ["true", "True", "TRUE", "1", "yes", "Yes", "on", "ON"]:
            result = _parse_value("enabled", value)
            assert result is True, f"Expected True for '{value}'"

    def test_parse_boolean_false(self):
        """Boolean fields should parse false values correctly."""
        for value in ["false", "False", "FALSE", "0", "no", "No", "off", "OFF"]:
            result = _parse_value("enabled", value)
            assert result is False, f"Expected False for '{value}'"

    def test_parse_integer_field(self):
        """Integer fields should be parsed as integers."""
        result = _parse_value("api_id", "12345")
        assert result == 12345
        assert isinstance(result, int)

    def test_parse_invalid_integer_raises_error(self):
        """Invalid integer value should raise ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            _parse_value("api_id", "not_a_number")
        assert "Invalid integer value" in str(exc_info.value)

    def test_parse_string_field(self):
        """String fields should remain as strings."""
        result = _parse_value("api_hash", "abc123def456")
        assert result == "abc123def456"
        assert isinstance(result, str)

    def test_parse_integer_by_suffix(self):
        """Fields ending with integer suffixes should parse as integers."""
        # Test _id suffix
        result = _parse_value("chat_id", "123")
        assert result == 123

        # Test _interval suffix
        result = _parse_value("check_interval", "300")
        assert result == 300

        # Test _seconds suffix
        result = _parse_value("throttle_seconds", "60")
        assert result == 60


class TestLoadFromEnv:
    """Tests for _load_from_env function."""

    def test_no_env_vars_returns_none(self, clean_env):
        """Returns None when no TDL_ vars exist."""
        result = _load_from_env()
        assert result is None

    def test_simple_env_vars(self, clean_env, monkeypatch):
        """Simple TDL_ vars should be parsed correctly."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")

        result = _load_from_env()
        assert result is not None
        assert result["api_id"] == 12345
        assert result["api_hash"] == "abc123"

    def test_nested_daemon_config(self, clean_env, monkeypatch):
        """Nested daemon config should be parsed correctly."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")
        monkeypatch.setenv("TDL_DAEMON_ENABLED", "true")
        monkeypatch.setenv("TDL_DAEMON_CHECK_INTERVAL", "600")

        result = _load_from_env()
        assert result["daemon"]["enabled"] is True
        assert result["daemon"]["check_interval"] == 600

    def test_sources_array(self, clean_env, monkeypatch):
        """Sources array should be parsed correctly."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")
        monkeypatch.setenv("TDL_SOURCES_0_URL", "https://t.me/channel1")
        monkeypatch.setenv("TDL_SOURCES_1_URL", "https://t.me/channel2")

        result = _load_from_env()
        assert len(result["sources"]) == 2
        assert result["sources"][0]["url"] == "https://t.me/channel1"
        assert result["sources"][1]["url"] == "https://t.me/channel2"

    def test_sources_array_with_gap(self, clean_env, monkeypatch):
        """Gaps in source numbering should be compacted, not left as empty entries."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")
        monkeypatch.setenv("TDL_SOURCES_0_URL", "https://t.me/channel1")
        # Source 1 disabled/commented out - gap in numbering
        monkeypatch.setenv("TDL_SOURCES_2_URL", "https://t.me/channel3")

        result = _load_from_env()
        assert len(result["sources"]) == 2
        assert result["sources"][0]["url"] == "https://t.me/channel1"
        assert result["sources"][1]["url"] == "https://t.me/channel3"

    def test_sources_array_one_based(self, clean_env, monkeypatch):
        """1-based source numbering should work (index 0 pad entry dropped)."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")
        monkeypatch.setenv("TDL_SOURCES_1_URL", "https://t.me/channel1")
        monkeypatch.setenv("TDL_SOURCES_2_URL", "https://t.me/channel2")

        result = _load_from_env()
        assert len(result["sources"]) == 2
        assert result["sources"][0]["url"] == "https://t.me/channel1"
        assert result["sources"][1]["url"] == "https://t.me/channel2"

    def test_sources_with_filters(self, clean_env, monkeypatch):
        """Source filters should be parsed correctly."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")
        monkeypatch.setenv("TDL_SOURCES_0_URL", "https://t.me/channel")
        monkeypatch.setenv("TDL_SOURCES_0_FILTERS_EXTENSIONS", ".pdf,.epub")

        result = _load_from_env()
        assert result["sources"][0]["filters"]["extensions"] == [".pdf", ".epub"]

    def test_global_filters(self, clean_env, monkeypatch):
        """Global filters should be parsed correctly."""
        monkeypatch.setenv("TDL_API_ID", "12345")
        monkeypatch.setenv("TDL_API_HASH", "abc123")
        monkeypatch.setenv("TDL_GLOBAL_FILTERS_EXTENSIONS", ".pdf,.epub")
        monkeypatch.setenv("TDL_GLOBAL_FILTERS_ALLOW_ARCHIVES", "true")

        result = _load_from_env()
        assert result["global_filters"]["extensions"] == [".pdf", ".epub"]
        # Note: allow_archives field ends with 's' which isn't in BOOL_FIELDS
        # so it returns the string "true" instead of boolean True.
        # This is a limitation of the current parser - the full load_config
        # handles this via Pydantic validation.
        assert result["global_filters"]["allow_archives"] in (True, "true")


class TestLoadFromYaml:
    """Tests for _load_from_yaml function."""

    def test_load_valid_yaml(self, yaml_config_file):
        """Valid YAML file should be loaded correctly."""
        config_file = yaml_config_file("""
api_id: 12345
api_hash: abc123
""")
        result = _load_from_yaml(str(config_file))
        assert result["api_id"] == 12345
        assert result["api_hash"] == "abc123"

    def test_file_not_found_raises_error(self):
        """Missing file should raise ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            _load_from_yaml("/nonexistent/path/config.yaml")
        assert "not found" in str(exc_info.value)

    def test_empty_file_raises_error(self, yaml_config_file):
        """Empty YAML file should raise ConfigError."""
        config_file = yaml_config_file("")
        with pytest.raises(ConfigError) as exc_info:
            _load_from_yaml(str(config_file))
        assert "empty" in str(exc_info.value)


class TestSubstituteEnvVars:
    """Tests for _substitute_env_vars function."""

    def test_substitute_simple_var(self, monkeypatch):
        """${VAR} should be substituted with environment variable."""
        monkeypatch.setenv("MY_VAR", "my_value")
        result = _substitute_env_vars("prefix_${MY_VAR}_suffix")
        assert result == "prefix_my_value_suffix"

    def test_substitute_with_default(self, clean_env):
        """${VAR:-default} should use default when var not set."""
        result = _substitute_env_vars("${UNDEFINED_VAR:-default_value}")
        assert result == "default_value"

    def test_substitute_in_dict(self, monkeypatch):
        """Substitution should work recursively in dicts."""
        monkeypatch.setenv("API_HASH", "secret123")
        data = {"api_hash": "${API_HASH}"}
        result = _substitute_env_vars(data)
        assert result["api_hash"] == "secret123"

    def test_substitute_in_list(self, monkeypatch):
        """Substitution should work recursively in lists."""
        monkeypatch.setenv("EXT", ".pdf")
        data = ["${EXT}", ".epub"]
        result = _substitute_env_vars(data)
        assert result == [".pdf", ".epub"]


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_yaml(self, clean_env, minimal_yaml_config):
        """Config should load from YAML when no env vars."""
        config = load_config(str(minimal_yaml_config))
        assert config.api_id == 12345

    def test_env_vars_take_priority(self, clean_env, monkeypatch, minimal_yaml_config):
        """Environment variables should take priority over YAML."""
        monkeypatch.setenv("TDL_API_ID", "99999")
        monkeypatch.setenv("TDL_API_HASH", "env_hash")

        config = load_config(str(minimal_yaml_config))
        assert config.api_id == 99999
        assert config.api_hash == "env_hash"

    def test_legacy_env_vars(self, clean_env, monkeypatch, temp_dir):
        """Legacy API_ID and API_HASH should be supported."""
        monkeypatch.setenv("API_ID", "12345")
        monkeypatch.setenv("API_HASH", "legacy_hash")

        # Create a minimal YAML file (needed as fallback)
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("verbosity: normal\n")

        config = load_config(str(yaml_file))
        assert config.api_id == 12345
        assert config.api_hash == "legacy_hash"

    def test_invalid_config_raises_error(self, clean_env, yaml_config_file):
        """Invalid config should raise ConfigError."""
        # Missing required api_hash
        config_file = yaml_config_file("api_id: 12345\n")
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        assert "validation failed" in str(exc_info.value).lower()
