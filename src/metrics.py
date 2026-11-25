"""Opt-in Prometheus metrics for telegram-downloader (issue #63).

The HTTP server is off by default. Call configure(enabled=True, port=...)
to start /metrics, then increment through the recorder returned by
get_metrics() (or the configure() result). When disabled, those calls
are no-ops.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)
from wsgiref.simple_server import WSGIServer


# Skip reasons that map 1:1 onto the run-summary counters in src/main.py.
# "filter" is included so files_skipped_total sums to the run-summary
# skip count. The issue named duplicate, tracked, and error; filter is
# the fourth reason the summary already reports.
SKIP_REASON_KEYS = {
    "skipped_duplicate": "duplicate",
    "skipped_tracked": "tracked",
    "skipped_error": "error",
    "skipped_filter": "filter",
}

# Check durations run from seconds to the daemon timeout (often 10 minutes).
_CHECK_DURATION_BUCKETS = (
    1.0,
    5.0,
    15.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    1200.0,
    3600.0,
)


class Metrics:
    """Prometheus registry plus the /metrics HTTP server."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.port: Optional[int] = None
        self._httpd: Optional[WSGIServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.registry = CollectorRegistry()

        self._files_downloaded = Counter(
            "telegram_downloader_files_downloaded_total",
            "Files downloaded successfully",
            ["source"],
            registry=self.registry,
        )
        self._bytes_downloaded = Counter(
            "telegram_downloader_bytes_downloaded_total",
            "Bytes downloaded successfully",
            ["source"],
            registry=self.registry,
        )
        self._files_failed = Counter(
            "telegram_downloader_files_failed_total",
            "Files that failed to download",
            ["source"],
            registry=self.registry,
        )
        self._files_skipped = Counter(
            "telegram_downloader_files_skipped_total",
            "Files skipped during a check",
            ["source", "reason"],
            registry=self.registry,
        )
        self._pending_queue_size = Gauge(
            "telegram_downloader_pending_queue_size",
            "Messages waiting in the pending download queue",
            ["source"],
            registry=self.registry,
        )
        self._last_check_timestamp = Gauge(
            "telegram_downloader_last_check_timestamp_seconds",
            "Unix timestamp of the last completed check",
            registry=self.registry,
        )
        self._check_duration = Histogram(
            "telegram_downloader_check_duration_seconds",
            "Duration of each download check",
            buckets=_CHECK_DURATION_BUCKETS,
            registry=self.registry,
        )
        self._floodwait_seconds = Counter(
            "telegram_downloader_floodwait_seconds_total",
            "Seconds of FloodWait requested by Telegram",
            registry=self.registry,
        )
        self._up = Gauge(
            "telegram_downloader_up",
            "1 when the metrics endpoint is running",
            registry=self.registry,
        )

    def start(self, port: int, addr: str = "0.0.0.0") -> int:
        """Start the Prometheus HTTP server and return the bound port."""
        with self._lock:
            if self._httpd is not None:
                return self.port if self.port is not None else port
            httpd, thread = start_http_server(port, addr=addr, registry=self.registry)
            self._httpd = httpd
            self._thread = thread
            self.port = httpd.server_address[1]
            self._up.set(1)
            return self.port

    def stop(self) -> None:
        """Stop the HTTP server if it is running."""
        with self._lock:
            httpd = self._httpd
            thread = self._thread
            self._httpd = None
            self._thread = None
            self.port = None
        if httpd is None:
            return
        self._up.set(0)
        httpd.shutdown()
        httpd.server_close()
        if thread is not None:
            thread.join(timeout=2)

    def record_downloaded(self, source: str, count: int = 1, bytes_count: int = 0) -> None:
        if count:
            self._files_downloaded.labels(source=source).inc(count)
        if bytes_count:
            self._bytes_downloaded.labels(source=source).inc(bytes_count)

    def record_failed(self, source: str, count: int = 1) -> None:
        if count:
            self._files_failed.labels(source=source).inc(count)

    def record_skipped(self, source: str, reason: str, count: int = 1) -> None:
        if count:
            self._files_skipped.labels(source=source, reason=reason).inc(count)

    def set_pending_queue_size(self, source: str, size: int) -> None:
        self._pending_queue_size.labels(source=source).set(size)

    def record_check(
        self,
        duration_seconds: float,
        timestamp: Optional[float] = None,
        *,
        completed: bool = True,
    ) -> None:
        self._check_duration.observe(duration_seconds)
        if completed:
            self._last_check_timestamp.set(
                time.time() if timestamp is None else timestamp
            )

    def record_floodwait(self, seconds: float) -> None:
        if seconds:
            self._floodwait_seconds.inc(seconds)

class _DisabledMetrics:
    """No-op recorder used when metrics are off (the default)."""

    enabled = False
    port: Optional[int] = None

    def start(self, port: int, addr: str = "0.0.0.0") -> Optional[int]:
        return None

    def stop(self) -> None:
        return None

    def record_downloaded(self, source: str, count: int = 1, bytes_count: int = 0) -> None:
        return None

    def record_failed(self, source: str, count: int = 1) -> None:
        return None

    def record_skipped(self, source: str, reason: str, count: int = 1) -> None:
        return None

    def set_pending_queue_size(self, source: str, size: int) -> None:
        return None

    def record_check(
        self,
        duration_seconds: float,
        timestamp: Optional[float] = None,
        *,
        completed: bool = True,
    ) -> None:
        return None

    def record_floodwait(self, seconds: float) -> None:
        return None

_current: Metrics | _DisabledMetrics = _DisabledMetrics()


def get_metrics() -> Metrics | _DisabledMetrics:
    """Return the process-wide recorder (a no-op when metrics are off)."""
    return _current


def shutdown() -> None:
    """Stop the HTTP server and restore the disabled recorder."""
    global _current
    _current.stop()
    _current = _DisabledMetrics()


def configure(
    enabled: bool, port: int = 9184, addr: str = "0.0.0.0"
) -> Metrics | _DisabledMetrics:
    """Enable or disable process-wide metrics, starting /metrics when on."""
    global _current
    shutdown()
    if not enabled:
        _current = _DisabledMetrics()
        return _current
    metrics = Metrics(enabled=True)
    metrics.start(port, addr=addr)
    _current = metrics
    return _current


def source_label(source_config, display_name: str) -> str:
    """Stable-enough label: config name, else the display name used in logs."""
    name = getattr(source_config, "name", None)
    if name:
        return str(name)
    return display_name
