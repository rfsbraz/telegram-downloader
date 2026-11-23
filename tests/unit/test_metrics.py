"""Opt-in Prometheus /metrics endpoint (issue #63).

The endpoint is off by default. When TDL_METRICS_ENABLED is on, a scrape
of /metrics must expose the issue's named metrics, and run-summary
counters must show up on that scrape.
"""
import logging
import re
import socket
import urllib.error
import urllib.request
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.schema import SourceConfig
from src import main as main_module
from src.main import run_check


ISSUE_METRIC_NAMES = (
    "telegram_downloader_files_downloaded_total",
    "telegram_downloader_bytes_downloaded_total",
    "telegram_downloader_files_failed_total",
    "telegram_downloader_files_skipped_total",
    "telegram_downloader_pending_queue_size",
    "telegram_downloader_last_check_timestamp_seconds",
    "telegram_downloader_check_duration_seconds",
    "telegram_downloader_floodwait_seconds_total",
    "telegram_downloader_up",
)


def _metric_present(body: str, name: str) -> bool:
    """True if the scrape exposes this metric family, including histogram suffixes."""
    return any(
        line.startswith(name)
        for line in body.splitlines()
        if line and not line.startswith("#")
    ) or any(
        line.startswith(f"# TYPE {name} ") or line.startswith(f"# HELP {name} ")
        for line in body.splitlines()
    )


def _scrape(port: int) -> tuple[int, str]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as resp:
        return resp.status, resp.read().decode()


def _port_is_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _metric_value(body: str, name: str, labels: dict[str, str] | None = None) -> float:
    """Return the value of a single Prometheus sample."""
    if labels:
        inner = ",".join(f'{key}="{value}"' for key, value in labels.items())
        pattern = re.compile(
            rf"^{re.escape(name)}\{{{re.escape(inner)}\}} (\S+)$", re.MULTILINE
        )
    else:
        pattern = re.compile(rf"^{re.escape(name)} (\S+)$", re.MULTILINE)
    match = pattern.search(body)
    assert match, f"sample {name} {labels or ''} not found in scrape:\n{body}"
    return float(match.group(1))


@pytest.fixture
def metrics_server():
    from src.metrics import configure, shutdown

    server = configure(enabled=True, port=0, addr="127.0.0.1")
    try:
        yield server
    finally:
        shutdown()


class TestMetricsDisabledByDefault:
    def test_configure_off_does_not_listen(self):
        from src.metrics import configure, shutdown

        port = _unused_port()
        server = configure(enabled=False, port=port, addr="127.0.0.1")
        try:
            assert server.enabled is False
            assert _port_is_closed(port)
            with pytest.raises(urllib.error.URLError):
                _scrape(port)
        finally:
            shutdown()


class TestMetricsScrape:
    def test_scrape_exposes_issue_metrics(self, metrics_server):
        status, body = _scrape(metrics_server.port)
        assert status == 200
        missing = [name for name in ISSUE_METRIC_NAMES if not _metric_present(body, name)]
        assert missing == [], f"missing metrics: {missing}\n{body}"
        assert _metric_value(body, "telegram_downloader_up") == 1

    def test_recorded_counters_appear_on_scrape(self, metrics_server):
        metrics_server.record_downloaded("Books", count=2, bytes_count=4096)
        metrics_server.record_failed("Books", count=1)
        metrics_server.record_skipped("Books", "duplicate", count=3)
        metrics_server.record_skipped("Books", "tracked", count=4)
        metrics_server.record_skipped("Books", "error", count=1)
        metrics_server.set_pending_queue_size("Books", 7)
        metrics_server.record_check(duration_seconds=1.5, timestamp=1_700_000_000)
        metrics_server.record_floodwait(12)

        status, body = _scrape(metrics_server.port)
        assert status == 200
        source = {"source": "Books"}
        assert _metric_value(body, "telegram_downloader_files_downloaded_total", source) == 2
        assert _metric_value(body, "telegram_downloader_bytes_downloaded_total", source) == 4096
        assert _metric_value(body, "telegram_downloader_files_failed_total", source) == 1
        assert _metric_value(
            body, "telegram_downloader_files_skipped_total", {**source, "reason": "duplicate"}
        ) == 3
        assert _metric_value(
            body, "telegram_downloader_files_skipped_total", {**source, "reason": "tracked"}
        ) == 4
        assert _metric_value(
            body, "telegram_downloader_files_skipped_total", {**source, "reason": "error"}
        ) == 1
        assert _metric_value(body, "telegram_downloader_pending_queue_size", source) == 7
        assert _metric_value(body, "telegram_downloader_last_check_timestamp_seconds") == 1_700_000_000
        assert _metric_value(body, "telegram_downloader_floodwait_seconds_total") == 12
        # Histogram exports _count/_sum; the observed duration must be counted.
        assert _metric_value(body, "telegram_downloader_check_duration_seconds_count") == 1
        assert _metric_value(body, "telegram_downloader_check_duration_seconds_sum") == pytest.approx(1.5)


def _make_msg(msg_id, file_name, file_size, file_unique_id):
    msg = MagicMock()
    msg.id = msg_id
    msg.document.file_name = file_name
    msg.document.file_size = file_size
    msg.document.file_unique_id = file_unique_id
    msg.audio = msg.video = msg.animation = msg.voice = msg.video_note = msg.photo = None
    return msg


class TestMetricsFollowRunSummary:
    async def test_run_check_counters_appear_on_scrape(self, tmp_path, monkeypatch, metrics_server):
        async def fake_dest(download_dir, source, fname, source_config, flat):
            return download_dir / fname

        monkeypatch.setattr(main_module, "build_destination_path", fake_dest)
        monkeypatch.setattr(main_module, "collect_matching_ids", AsyncMock(return_value=[]))

        async def fake_download(*args, **kwargs):
            dest = args[2] if len(args) > 2 else kwargs.get("dest_path")
            if dest is not None and str(dest).endswith("bad.pdf"):
                return False
            return True

        monkeypatch.setattr(main_module, "download_media_with_retry", fake_download)

        cfg = MagicMock()
        cfg.dry_run = False
        cfg.min_free_space = ""
        cfg.flat_structure = True
        cfg.download_dir = tmp_path
        cfg.post_download_hook = None
        cfg.max_concurrent_downloads = 1
        cfg.max_downloads_per_run = 0
        cfg.max_download_attempts = 5

        ok = _make_msg(1, "ok.pdf", 1000, "u-ok")
        tracked = _make_msg(2, "old.pdf", 2000, "u-old")
        failed = _make_msg(3, "bad.pdf", 3000, "u-bad")

        source = MagicMock()
        source.chat_id = -100111
        source.get_cursor_key.return_value = "channel:-100111"
        source.get_display_name = AsyncMock(return_value="Books")

        source_config = SourceConfig(url="https://t.me/books", name="Books")
        pending = MagicMock()
        pending.has_pending.return_value = True
        pending.get_max_message_id.return_value = 3
        pending.get_oldest.side_effect = [[1, 2, 3], []]
        pending.count.return_value = 1
        pending.count_exhausted.return_value = 0

        client = MagicMock()
        client.get_messages = AsyncMock(return_value=[ok, tracked, failed])
        state = MagicMock()
        state.get.return_value = 0
        history = MagicMock()
        history.contains.side_effect = lambda uid: uid == "u-old"

        summary = await run_check(
            cfg,
            logging.getLogger("test-metrics"),
            state,
            client,
            [(source, MagicMock(), source_config)],
            history,
            pending,
        )

        assert summary["files_downloaded"] == 1
        assert summary["files_failed"] == 1
        assert summary["files_skipped"] >= 1

        status, body = _scrape(metrics_server.port)
        assert status == 200
        source_label = {"source": "Books"}
        assert _metric_value(body, "telegram_downloader_files_downloaded_total", source_label) == 1
        assert _metric_value(body, "telegram_downloader_bytes_downloaded_total", source_label) == 1000
        assert _metric_value(body, "telegram_downloader_files_failed_total", source_label) == 1
        assert _metric_value(
            body,
            "telegram_downloader_files_skipped_total",
            {**source_label, "reason": "tracked"},
        ) == 1
        assert _metric_value(body, "telegram_downloader_pending_queue_size", source_label) == 1
        assert _metric_value(body, "telegram_downloader_last_check_timestamp_seconds") > 0
        assert _metric_value(body, "telegram_downloader_check_duration_seconds_count") == 1

    async def test_dry_run_does_not_increment_download_counters(
        self, tmp_path, monkeypatch, metrics_server
    ):
        from tests.unit.test_dry_run import make_msg, make_run_args

        messages = [make_msg(10, "book.pdf", 2048, "u-dry")]
        args = make_run_args(tmp_path, messages, monkeypatch, dry_run=True)
        summary = await run_check(*args)
        assert summary["files_downloaded"] == 1
        assert summary["dry_run"] is True

        status, body = _scrape(metrics_server.port)
        assert status == 200
        # A dry-run still records that a check happened.
        assert _metric_value(body, "telegram_downloader_last_check_timestamp_seconds") > 0
        assert _metric_value(body, "telegram_downloader_check_duration_seconds_count") == 1
        # It must not count previewed files as real downloads.
        assert "telegram_downloader_files_downloaded_total" not in [
            line.split("{")[0].split(" ")[0]
            for line in body.splitlines()
            if line and not line.startswith("#")
        ] or all(
            not line.startswith("telegram_downloader_files_downloaded_total{")
            or line.endswith(" 0")
            or line.endswith(" 0.0")
            for line in body.splitlines()
        )


class TestFloodWaitMetric:
    def test_floodwait_cooldown_is_counted(self, metrics_server):
        from src.client.downloader import _start_cooldown

        _start_cooldown(12)
        status, body = _scrape(metrics_server.port)
        assert status == 200
        assert _metric_value(body, "telegram_downloader_floodwait_seconds_total") == 12
