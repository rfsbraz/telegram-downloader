"""Duplicate detection and conflict resolution, including a dry-run overlay."""

from pathlib import Path

import pytest

from src.organization.deduplicator import is_duplicate, resolve_conflict


def test_overlay_treats_reserved_same_size_as_duplicate(tmp_path):
    dest = tmp_path / "book.pdf"
    overlay = {dest: 2048}
    assert is_duplicate(dest, 2048, overlay=overlay) is True
    assert is_duplicate(dest, 4096, overlay=overlay) is False
    assert dest.exists() is False


def test_overlay_suffixes_reserved_paths(tmp_path):
    dest = tmp_path / "book.pdf"
    overlay = {dest: 2048}
    assert resolve_conflict(dest, overlay=overlay) == tmp_path / "book_2.pdf"


def test_overlay_with_on_disk_file(tmp_path):
    dest = tmp_path / "book.pdf"
    dest.write_bytes(b"x" * 100)
    reserved = tmp_path / "book_2.pdf"
    overlay = {reserved: 200}
    assert resolve_conflict(dest, overlay=overlay) == tmp_path / "book_3.pdf"


def test_overlay_exhausted_names_raise(tmp_path):
    dest = tmp_path / "book.pdf"
    dest.write_bytes(b"x")
    overlay = {tmp_path / "book_2.pdf": 1}
    with pytest.raises(RuntimeError, match="Could not resolve filename conflict"):
        resolve_conflict(dest, max_attempts=1, overlay=overlay)
