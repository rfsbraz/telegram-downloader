"""
Configuration module for telegram-downloader.
"""
from .loader import ConfigError, load_config
from .schema import Config, FilterConfig, GlobalFilters, RetryConfig, SourceConfig
from .source_parser import parse_sources, validate_source_access
from .url_parser import parse_telegram_url

__all__ = [
    "Config",
    "ConfigError",
    "FilterConfig",
    "GlobalFilters",
    "RetryConfig",
    "SourceConfig",
    "load_config",
    "parse_sources",
    "parse_telegram_url",
    "validate_source_access",
]
