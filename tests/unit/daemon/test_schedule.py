"""
Unit tests for download scheduling (issue #36).

Covers window parsing (single, multiple, cross-midnight) and the
active-hours check, plus the daemon gate.
"""
from datetime import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.daemon.schedule import parse_active_hours, is_within_active_hours
from src.daemon.service import DaemonService


class TestParseActiveHours:
    """Tests for active-hours spec parsing."""

    def test_single_window(self):
        assert parse_active_hours("02:00-08:00") == [(time(2, 0), time(8, 0))]

    def test_multiple_windows(self):
        assert parse_active_hours("02:00-08:00,22:00-23:59") == [
            (time(2, 0), time(8, 0)),
            (time(22, 0), time(23, 59)),
        ]

    def test_cross_midnight_window(self):
        assert parse_active_hours("23:00-06:00") == [(time(23, 0), time(6, 0))]

    def test_whitespace_tolerated(self):
        assert parse_active_hours(" 02:00-08:00 , 22:00-23:59 ") == [
            (time(2, 0), time(8, 0)),
            (time(22, 0), time(23, 59)),
        ]

    def test_empty_spec_means_no_windows(self):
        assert parse_active_hours("") == []

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid active hours"):
            parse_active_hours("2am-8am")

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="Invalid active hours"):
            parse_active_hours("25:00-08:00")


class TestIsWithinActiveHours:
    """Tests for the active-hours check."""

    def test_no_windows_always_active(self):
        assert is_within_active_hours([], time(12, 0)) is True

    def test_inside_normal_window(self):
        windows = parse_active_hours("02:00-08:00")
        assert is_within_active_hours(windows, time(5, 0)) is True

    def test_outside_normal_window(self):
        windows = parse_active_hours("02:00-08:00")
        assert is_within_active_hours(windows, time(12, 0)) is False

    def test_window_boundaries_inclusive(self):
        windows = parse_active_hours("02:00-08:00")
        assert is_within_active_hours(windows, time(2, 0)) is True
        assert is_within_active_hours(windows, time(8, 0)) is True

    def test_cross_midnight_late_evening(self):
        windows = parse_active_hours("23:00-06:00")
        assert is_within_active_hours(windows, time(23, 30)) is True

    def test_cross_midnight_early_morning(self):
        windows = parse_active_hours("23:00-06:00")
        assert is_within_active_hours(windows, time(3, 0)) is True

    def test_cross_midnight_daytime_inactive(self):
        windows = parse_active_hours("23:00-06:00")
        assert is_within_active_hours(windows, time(12, 0)) is False

    def test_multiple_windows_any_match(self):
        windows = parse_active_hours("02:00-08:00,22:00-23:59")
        assert is_within_active_hours(windows, time(22, 30)) is True
        assert is_within_active_hours(windows, time(15, 0)) is False


class TestDaemonScheduleGate:
    """The daemon skips checks outside active hours."""

    async def test_check_skipped_outside_window(self, tmp_path, monkeypatch):
        check = AsyncMock()
        service = DaemonService(
            check_function=check,
            check_interval=300,
            health_file=tmp_path / "health.txt",
            active_hours="02:00-03:00",
        )
        # Force "now" outside the window
        monkeypatch.setattr(
            "src.daemon.service.is_within_active_hours", lambda windows: False
        )

        await service.run_check()

        check.assert_not_awaited()
        assert service.iteration == 0

    async def test_check_runs_inside_window(self, tmp_path, monkeypatch):
        check = AsyncMock()
        service = DaemonService(
            check_function=check,
            check_interval=300,
            health_file=tmp_path / "health.txt",
            active_hours="02:00-03:00",
        )
        monkeypatch.setattr(
            "src.daemon.service.is_within_active_hours", lambda windows: True
        )

        await service.run_check()

        check.assert_awaited_once()
        assert service.iteration == 1

    async def test_no_schedule_always_runs(self, tmp_path):
        check = AsyncMock()
        service = DaemonService(
            check_function=check,
            check_interval=300,
            health_file=tmp_path / "health.txt",
        )

        await service.run_check()

        check.assert_awaited_once()
