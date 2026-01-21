"""
Security module for telegram-downloader.
"""
from .sanitizer import sanitize_filename, validate_path_safety

__all__ = [
    "sanitize_filename",
    "validate_path_safety",
]
