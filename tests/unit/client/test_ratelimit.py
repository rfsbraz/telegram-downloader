"""
Unit tests for bandwidth rate limiting (issue #36).

Covers rate string parsing and token-bucket throttling behavior.
"""
import time

import pytest

from src.client.ratelimit import RateLimiter, parse_rate


class TestParseRate:
    """Tests for rate string parsing."""

    def test_megabytes(self):
        assert parse_rate("5MB") == 5 * 1024 ** 2

    def test_kilobytes(self):
        assert parse_rate("500KB") == 500 * 1024

    def test_fractional(self):
        assert parse_rate("1.5MB") == int(1.5 * 1024 ** 2)

    def test_per_second_suffix(self):
        assert parse_rate("5MB/s") == 5 * 1024 ** 2

    def test_lowercase(self):
        assert parse_rate("5mb") == 5 * 1024 ** 2

    def test_bare_number_is_bytes(self):
        assert parse_rate("1024") == 1024

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid download speed"):
            parse_rate("fast")

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown speed unit"):
            parse_rate("5XB")

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            parse_rate("0MB")


class TestRateLimiter:
    """Tests for token-bucket throttling."""

    async def test_burst_within_allowance_does_not_sleep(self):
        limiter = RateLimiter(rate=1024 ** 2)  # 1 MB/s
        start = time.monotonic()
        await limiter.throttle(1024)  # 1 KB, well within the 1s burst
        assert time.monotonic() - start < 0.1

    async def test_over_allowance_sleeps(self):
        limiter = RateLimiter(rate=10_000)  # 10 KB/s
        # First call drains the 1s burst; second forces a deficit sleep
        await limiter.throttle(10_000)
        start = time.monotonic()
        await limiter.throttle(5_000)  # 0.5s worth of deficit
        elapsed = time.monotonic() - start
        assert elapsed >= 0.4

    async def test_zero_bytes_is_noop(self):
        limiter = RateLimiter(rate=1)
        start = time.monotonic()
        await limiter.throttle(0)
        assert time.monotonic() - start < 0.1
