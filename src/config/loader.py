"""
Configuration loader with YAML parsing and environment variable support.
"""
import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

from .schema import Config


class ConfigError(Exception):
    """User-friendly configuration error."""
    pass


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


def load_config(path: str) -> Config:
    """
    Load configuration from YAML file with validation.

    Args:
        path: Path to YAML configuration file

    Returns:
        Validated Config instance

    Raises:
        ConfigError: If configuration is invalid or file cannot be loaded
    """
    # Load YAML file
    try:
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigError(f"Configuration file not found: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        if raw_data is None:
            raise ConfigError(f"Configuration file is empty: {path}")

    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML syntax: {e}")
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"Failed to read configuration file: {e}")

    # Substitute environment variables
    data = _substitute_env_vars(raw_data)

    # Apply environment variable overrides
    if "API_ID" in os.environ:
        try:
            data["api_id"] = int(os.environ["API_ID"])
        except ValueError:
            raise ConfigError("Environment variable API_ID must be a valid integer")

    if "API_HASH" in os.environ:
        data["api_hash"] = os.environ["API_HASH"]

    if "DOWNLOAD_DIR" in os.environ:
        data["download_dir"] = os.environ["DOWNLOAD_DIR"]

    # Validate with pydantic
    try:
        config = Config.model_validate(data)
        return config
    except Exception as e:
        # Parse pydantic validation errors to show user-friendly messages
        error_msg = str(e)

        # Extract the most relevant error information
        if "validation error" in error_msg.lower():
            lines = error_msg.split("\n")
            # Find lines that describe specific field errors
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

        # Fallback to simplified error message
        raise ConfigError(f"Configuration validation failed: {error_msg}")
