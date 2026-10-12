"""
Configuration schema with pydantic validation.
"""
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class RetryConfig(BaseModel):
    """Retry configuration for failed operations."""
    max_retries: int = Field(default=2, ge=0)
    base_delay: int = Field(default=2, ge=1)
    max_delay: int = Field(default=60, ge=1)


class DaemonConfig(BaseModel):
    """Daemon mode configuration for continuous operation."""
    enabled: bool = Field(default=False)
    check_interval: int = Field(default=300, ge=60, le=86400)
    health_file: Path = Field(default=Path("/app/health_status.txt"))
    log_level: Optional[str] = None

    @field_validator("check_interval")
    @classmethod
    def validate_check_interval(cls, v: int) -> int:
        """Validate check interval is within reasonable range."""
        # Allow low values for testing but would warn if <300 in production
        if v < 60:
            raise ValueError("check_interval must be at least 60 seconds")
        if v > 86400:
            raise ValueError("check_interval must not exceed 86400 seconds (24 hours)")
        return v


class NotificationConfig(BaseModel):
    """Notification delivery configuration."""
    enabled: bool = Field(default=False)
    detail_level: Literal["minimal", "summary", "detailed"] = Field(default="summary")
    throttle_seconds: int = Field(default=60, ge=10, le=3600)

    # Discord webhook
    discord_webhook_url: Optional[HttpUrl] = None
    discord_username: str = Field(default="Telegram Downloader")

    # Generic webhook
    generic_webhook_url: Optional[HttpUrl] = None


class FilterConfig(BaseModel):
    """File filtering configuration (legacy, use GlobalFilters)."""
    ebook_exts: list[str] = Field(default=[".epub", ".mobi", ".pdf"])
    allow_archives: bool = Field(default=False)
    archive_exts: list[str] = Field(default=[".zip", ".rar", ".7z"])


class GlobalFilters(BaseModel):
    """Global filter defaults for all sources."""
    extensions: list[str] = Field(default=[".pdf", ".epub", ".mobi"])
    allow_archives: bool = Field(default=False)
    archive_exts: list[str] = Field(default=[".zip", ".rar", ".7z"])
    min_size: Optional[str] = None  # e.g., "1KB", "5MB"
    max_size: Optional[str] = None  # e.g., "2GB"
    only_after: Optional[datetime] = None
    only_before: Optional[datetime] = None
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    """Source configuration for Telegram chats (multi-source format)."""
    url: Optional[str] = None  # t.me URL
    chat_id: Optional[int] = None  # Numeric ID (alternative to URL)
    name: Optional[str] = None  # Display name override
    filters: Optional[GlobalFilters] = None  # Per-source filter overrides

    # Legacy fields for backward compatibility (will be removed)
    chat_username: Optional[str] = None
    chat_title_hint: Optional[str] = None
    topic_id: Optional[int] = None

    @field_validator("chat_id")
    @classmethod
    def validate_identifier(cls, v, info):
        """Ensure at least one of url or chat_id is provided."""
        # Only validate when processing sources list (not legacy fields)
        # Check after all fields are set, only on chat_id validation (runs last)
        if info.data.get("url") is None and v is None:
            raise ValueError("Either url or chat_id must be provided")
        return v


class Config(BaseModel):
    """Main configuration schema."""
    # Telegram API credentials (required)
    api_id: int = Field(..., gt=0)
    api_hash: str = Field(..., min_length=1)
    phone_number: Optional[str] = None

    # Test mode - connects to Telegram's test servers (DC2: 149.154.167.40:443)
    # Use for debugging authentication issues without affecting production sessions
    test_mode: bool = Field(default=False)

    # Paths
    download_dir: Path = Field(default=Path("/downloads"))
    session_dir: Path = Field(default=Path("/app/.sessions"))
    log_file: Optional[Path] = None

    # Storage structure
    flat_structure: bool = Field(default=False)

    # Download tracking
    track_downloads: bool = Field(default=True)

    # Logging
    verbosity: Literal["quiet", "normal", "verbose"] = Field(default="normal")

    # Multi-source configuration
    sources: list[SourceConfig] = Field(default_factory=list)
    global_filters: GlobalFilters = Field(default_factory=GlobalFilters)
    max_concurrent_downloads: int = Field(default=1, ge=1, le=10)

    # Scheduling: only run download checks inside these windows (daemon mode).
    # 24h format, comma-separated, may cross midnight: "02:00-08:00,22:00-23:59"
    # Empty means no restriction.
    schedule_active_hours: str = Field(default="")

    # Bandwidth: cap aggregate download speed ("500KB", "5MB").
    # Empty means unlimited.
    max_download_speed: str = Field(default="")

    # Daemon mode configuration
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)

    # Notification configuration
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)

    # Legacy fields (DEPRECATED - for backward compatibility with existing downloader.py)
    chat_id: Optional[int] = None
    chat_username: Optional[str] = None
    chat_title_hint: Optional[str] = None
    topics: Optional[list[int]] = None
    state_file: Optional[Path] = None
    max_downloads_per_run: int = Field(default=0, ge=0)

    # Filters (DEPRECATED - use global_filters instead)
    ebook_exts: list[str] = Field(default=[".epub", ".mobi", ".pdf"])
    allow_archives: bool = Field(default=False)
    archive_exts: list[str] = Field(default=[".zip", ".rar", ".7z"])

    # Retry configuration
    max_retries: int = Field(default=2, ge=0)
    base_delay: int = Field(default=2, ge=1)
    max_delay: int = Field(default=60, ge=1)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: list[SourceConfig]) -> list[SourceConfig]:
        """Ensure sources list is not empty if provided."""
        # Allow empty list for backward compatibility with legacy config
        return v

    @field_validator("schedule_active_hours")
    @classmethod
    def validate_schedule_active_hours(cls, v: str) -> str:
        """Fail fast on malformed active-hours windows."""
        if v:
            # Function-level import to avoid a config <-> daemon import cycle
            from src.daemon.schedule import parse_active_hours
            try:
                parse_active_hours(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v

    @field_validator("max_download_speed")
    @classmethod
    def validate_max_download_speed(cls, v: str) -> str:
        """Fail fast on malformed download speed values."""
        if v:
            # Function-level import to avoid a config <-> client import cycle
            from src.client.ratelimit import parse_rate
            try:
                parse_rate(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v

    @field_validator("api_hash")
    @classmethod
    def validate_api_hash(cls, v: str) -> str:
        """Ensure api_hash is non-empty."""
        if not v or not v.strip():
            raise ValueError("api_hash must be a non-empty string")
        return v.strip()

    @field_validator("download_dir", "session_dir", "log_file", "state_file")
    @classmethod
    def validate_paths(cls, v: Optional[Path]) -> Optional[Path]:
        """Ensure paths are absolute or resolve to absolute."""
        if v is None:
            return None
        if not v.is_absolute():
            v = v.resolve()
        return v
