"""
Configuration loader with environment variable and YAML support.

Supports two configuration methods:
1. Environment variables with TDL_ prefix (preferred for Docker)
2. YAML configuration file (fallback)

Environment variable format:
- TDL_API_ID=12345
- TDL_API_HASH=abc123
- TDL_TEST_MODE=true (connects to Telegram test servers)
- TDL_SOURCES_0_URL=https://t.me/channel
- TDL_SOURCES_0_FILTERS_EXTENSIONS=.pdf,.epub,.mobi
- TDL_DAEMON_ENABLED=true
"""
import os
import re
from pathlib import Path
from typing import Any

import yaml

from .schema import Config


class ConfigError(Exception):
    """User-friendly configuration error."""
    pass


# Fields that should be parsed as comma-separated lists
LIST_FIELDS = {
    "extensions",
    "archive_exts",
    "include_patterns",
    "exclude_patterns",
    "topics",
    "ebook_exts",
}

# Fields that should be parsed as booleans
BOOL_FIELDS = {
    "enabled",
    "allow_archives",
    "test_mode",
    "track_downloads",
}

# Full field names that should be parsed as integers
INT_FIELDS = {
    "api_id",
    "chat_id",
    "topic_id",
    "check_interval",
    "throttle_seconds",
    "max_concurrent_downloads",
    "max_downloads_per_run",
    "max_retries",
    "base_delay",
    "max_delay",
}

# Field name endings that indicate integers (for nested fields)
INT_SUFFIXES = {"_id", "_interval", "_seconds", "_downloads", "_retries", "_delay", "_timeout"}

# Top-level fields that should NOT be nested (underscore is part of name)
FLAT_FIELDS = {
    "api_id",
    "api_hash",
    "phone_number",
    "test_mode",
    "download_dir",
    "session_dir",
    "log_file",
    "state_file",
    "verbosity",
    "max_concurrent_downloads",
    "max_downloads_per_run",
    "max_retries",
    "base_delay",
    "max_delay",
    "chat_id",
    "chat_username",
    "chat_title_hint",
    "topics",
    "ebook_exts",
    "allow_archives",
    "archive_exts",
    "track_downloads",
    "post_download_hook",
    "post_download_hook_timeout",
}

# Two-level nested fields (parent_child format)
NESTED_MAPPINGS = {
    "daemon_enabled": ("daemon", "enabled"),
    "daemon_check_interval": ("daemon", "check_interval"),
    "daemon_health_file": ("daemon", "health_file"),
    "daemon_log_level": ("daemon", "log_level"),
    "notifications_enabled": ("notifications", "enabled"),
    "notifications_detail_level": ("notifications", "detail_level"),
    "notifications_throttle_seconds": ("notifications", "throttle_seconds"),
    "notifications_discord_webhook_url": ("notifications", "discord_webhook_url"),
    "notifications_discord_username": ("notifications", "discord_username"),
    "notifications_generic_webhook_url": ("notifications", "generic_webhook_url"),
    "global_filters_extensions": ("global_filters", "extensions"),
    "global_filters_allow_archives": ("global_filters", "allow_archives"),
    "global_filters_archive_exts": ("global_filters", "archive_exts"),
    "global_filters_min_size": ("global_filters", "min_size"),
    "global_filters_max_size": ("global_filters", "max_size"),
}


def _parse_value(key: str, value: str) -> Any:
    """Parse string value to appropriate type based on field name."""
    # Get the last part of the key for simple field matching
    field_name = key.split("_")[-1].lower()

    # Check if it's a list field
    if field_name in LIST_FIELDS:
        return [v.strip() for v in value.split(",") if v.strip()]

    # Check if it's a boolean field
    if field_name in BOOL_FIELDS or key in BOOL_FIELDS:
        return value.lower() in ("true", "1", "yes", "on")

    # Check if it's an integer field (full match or suffix match)
    if key in INT_FIELDS or any(key.endswith(suffix) for suffix in INT_SUFFIXES):
        try:
            return int(value)
        except ValueError:
            raise ConfigError(f"Invalid integer value for {key}: {value}")

    return value


def _set_nested(data: dict, keys: list[str], value: Any) -> None:
    """Set a value in a nested dictionary structure, handling arrays."""
    for i, key in enumerate(keys[:-1]):
        # Check if next key is numeric (array index)
        if keys[i + 1].isdigit():
            if key not in data:
                data[key] = []
            data = data[key]
            # Ensure list is long enough
            idx = int(keys[i + 1])
            while len(data) <= idx:
                data.append({})
            # Skip to array element
            continue

        # Current key is numeric (we're indexing into array)
        if key.isdigit():
            data = data[int(key)]
            continue

        # Regular nested dict
        if key not in data:
            data[key] = {}
        data = data[key]

    # Set the final value
    final_key = keys[-1]
    if final_key.isdigit():
        # Setting array element directly (shouldn't happen often)
        data[int(final_key)] = value
    else:
        data[final_key] = value


def _load_from_env() -> dict | None:
    """
    Load configuration from TDL_ prefixed environment variables.

    Returns:
        Configuration dict or None if no TDL_ vars found
    """
    prefix = "TDL_"
    env_vars = {k: v for k, v in os.environ.items() if k.startswith(prefix)}

    if not env_vars:
        return None

    data = {}

    for key, value in env_vars.items():
        # Remove prefix and convert to lowercase
        key_path = key[len(prefix):].lower()

        # Parse the value based on field type
        parsed_value = _parse_value(key_path, value)

        # Check if it's a flat top-level field
        if key_path in FLAT_FIELDS:
            data[key_path] = parsed_value
            continue

        # Check if it's a known nested mapping
        if key_path in NESTED_MAPPINGS:
            parent, child = NESTED_MAPPINGS[key_path]
            if parent not in data:
                data[parent] = {}
            data[parent][child] = parsed_value
            continue

        # Handle sources array: sources_0_url, sources_0_filters_extensions, etc.
        if key_path.startswith("sources_"):
            parts = key_path.split("_")
            # sources_0_url -> ['sources', '0', 'url']
            # sources_0_filters_extensions -> ['sources', '0', 'filters', 'extensions']
            if len(parts) >= 3 and parts[1].isdigit():
                if "sources" not in data:
                    data["sources"] = []

                idx = int(parts[1])
                while len(data["sources"]) <= idx:
                    data["sources"].append({})

                # Remaining parts after sources_N_
                remaining = "_".join(parts[2:])

                # Handle nested filters
                if remaining.startswith("filters_"):
                    filter_field = remaining[8:]  # Remove "filters_"
                    if "filters" not in data["sources"][idx]:
                        data["sources"][idx]["filters"] = {}
                    data["sources"][idx]["filters"][filter_field] = parsed_value
                else:
                    data["sources"][idx][remaining] = parsed_value
                continue

        # Fallback: treat as simple key
        data[key_path] = parsed_value

    # Compact the sources list: gaps in TDL_SOURCES_N_* numbering (e.g. a
    # commented-out source in the middle) leave empty placeholder entries
    # behind, which would otherwise fail validation with a confusing
    # "Either url or chat_id must be provided" error. Drop them and keep
    # the remaining sources in their original order.
    if "sources" in data:
        original_count = len(data["sources"])
        data["sources"] = [s for s in data["sources"] if s]
        dropped = original_count - len(data["sources"])
        if dropped:
            import logging
            logging.getLogger(__name__).warning(
                f"Ignoring {dropped} gap(s) in TDL_SOURCES_N_* numbering; "
                f"{len(data['sources'])} source(s) configured"
            )

    return data


def _substitute_env_vars(data: Any) -> Any:
    """
    Recursively substitute ${VAR} syntax with environment variables.
    """
    if isinstance(data, dict):
        return {k: _substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_env_vars(item) for item in data]
    elif isinstance(data, str):
        # Replace ${VAR} or ${VAR:-default} with environment variable
        pattern = r'\$\{([^}:]+)(?::[-]([^}]*))?\}'
        def replacer(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(var_name, default_value)
        return re.sub(pattern, replacer, data)
    return data


def _load_from_yaml(path: str) -> dict:
    """Load configuration from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    if raw_data is None:
        raise ConfigError(f"Configuration file is empty: {path}")

    # Substitute environment variables in YAML values
    return _substitute_env_vars(raw_data)


def load_config(path: str = "/app/config.yaml") -> Config:
    """
    Load configuration from environment variables or YAML file.

    Priority:
    1. TDL_ prefixed environment variables (if any exist)
    2. YAML configuration file

    Args:
        path: Path to YAML configuration file (fallback)

    Returns:
        Validated Config instance

    Raises:
        ConfigError: If configuration is invalid or cannot be loaded
    """
    # Try environment variables first
    data = _load_from_env()

    if data is None:
        # Fall back to YAML file
        try:
            data = _load_from_yaml(path)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML syntax: {e}")
        except ConfigError:
            raise
        except Exception as e:
            raise ConfigError(f"Failed to read configuration file: {e}")

    # Apply legacy environment variable overrides (for backward compatibility)
    if "API_ID" in os.environ and "api_id" not in data:
        try:
            data["api_id"] = int(os.environ["API_ID"])
        except ValueError:
            raise ConfigError("Environment variable API_ID must be a valid integer")

    if "API_HASH" in os.environ and "api_hash" not in data:
        data["api_hash"] = os.environ["API_HASH"]

    if "DOWNLOAD_DIR" in os.environ and "download_dir" not in data:
        data["download_dir"] = os.environ["DOWNLOAD_DIR"]

    # Validate with pydantic
    try:
        config = Config.model_validate(data)
        return config
    except Exception as e:
        error_msg = str(e)

        # Extract the most relevant error information
        if "validation error" in error_msg.lower():
            lines = error_msg.split("\n")
            field_errors = []
            for line in lines:
                if "Field required" in line:
                    field_errors.append(line.strip())
                elif "Input should be" in line:
                    field_errors.append(line.strip())
                elif "should be greater than" in line:
                    field_errors.append(line.strip())

            if field_errors:
                raise ConfigError(f"Configuration validation failed:\n" + "\n".join(field_errors))

        raise ConfigError(f"Configuration validation failed: {error_msg}")
