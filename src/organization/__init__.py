"""
File organization module for destination path building and duplicate detection.

Provides:
- Per-source folder structure (ORG-01)
- Path safety validation (ORG-02)
- Duplicate detection and conflict resolution (ORG-03)
"""

from src.organization.path_builder import build_destination_path
from src.organization.deduplicator import is_duplicate, resolve_conflict

__all__ = [
    "build_destination_path",
    "is_duplicate",
    "resolve_conflict",
]
