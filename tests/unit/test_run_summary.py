"""
Unit tests for the run summary statistics (issue #34).

Covers byte formatting and the daemon merging the check function's
summary dict into the success notification details.
"""
from pathlib import Path
from unittest.mock import AsyncMock

from src.main import format_bytes
from src.daemon.service import DaemonService


class TestFormatBytes:
    """Tests for format_bytes helper."""

    def test_bytes(self):
        assert format_bytes(0) == "0 B"
        assert format_bytes(512) == "512 B"

    def test_kilobytes(self):
        assert format_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        assert format_bytes(int(142.5 * 1024 ** 2)) == "142.5 MB"

    def test_gigabytes(self):
        assert format_bytes(3 * 1024 ** 3) == "3.0 GB"


class TestDaemonSummaryNotification:
    """The daemon merges a dict returned by the check function into details."""

    async def test_summary_merged_into_success_notification(self, tmp_path):
        summary = {
            "sources_checked": 3,
            "files_downloaded": 12,
            "files_failed": 1,
            "bytes_downloaded": "142.5 MB",
        }
        check = AsyncMock(return_value=summary)
        manager = AsyncMock()

        service = DaemonService(
            check_function=check,
            check_interval=300,
            health_file=tmp_path / "health.txt",
            notification_manager=manager,
        )

        await service.run_check()

        manager.notify.assert_awaited_once()
        details = manager.notify.await_args.kwargs["details"]
        for key, value in summary.items():
            assert details[key] == value
        assert details["iteration"] == 1

    async def test_none_result_keeps_basic_details(self, tmp_path):
        check = AsyncMock(return_value=None)
        manager = AsyncMock()

        service = DaemonService(
            check_function=check,
            check_interval=300,
            health_file=tmp_path / "health.txt",
            notification_manager=manager,
        )

        await service.run_check()

        details = manager.notify.await_args.kwargs["details"]
        assert set(details.keys()) == {"iteration", "duration"}
