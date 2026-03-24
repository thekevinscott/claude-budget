"""Unit tests for the file-based usage cache."""

import json
import time

import pytest

from claude_budget.usage import UsageStatus, _read_cache, _write_cache, CACHE_PATH


def _sample_status():
    return UsageStatus(
        available=True,
        five_hour=0.30,
        seven_day=0.87,
    )


def _rate_limited_status():
    return UsageStatus(
        available=False,
        retry_after_seconds=1800,
        reset_timestamp=time.time() + 1800,
    )


# ── _write_cache / _read_cache round-trip ─────────────────────────


def test_write_then_read_returns_cached_status(tmp_path):
    cache_file = tmp_path / "usage.json"
    status = _sample_status()
    _write_cache(str(cache_file), status)
    cached = _read_cache(str(cache_file), max_age=30)
    assert cached is not None
    assert cached.available is True
    assert cached.five_hour == pytest.approx(0.30)
    assert cached.seven_day == pytest.approx(0.87)


def test_read_cache_returns_none_when_file_missing(tmp_path):
    cache_file = tmp_path / "nonexistent.json"
    assert _read_cache(str(cache_file), max_age=30) is None


def test_read_cache_returns_none_when_expired(tmp_path):
    cache_file = tmp_path / "usage.json"
    status = _sample_status()
    _write_cache(str(cache_file), status)

    # Backdate the cache entry
    data = json.loads(cache_file.read_text())
    data["timestamp"] = time.time() - 60
    cache_file.write_text(json.dumps(data))

    assert _read_cache(str(cache_file), max_age=30) is None


def test_read_cache_returns_none_on_corrupt_json(tmp_path):
    cache_file = tmp_path / "usage.json"
    cache_file.write_text("not valid json{{{")
    assert _read_cache(str(cache_file), max_age=30) is None


def test_read_cache_returns_none_on_missing_fields(tmp_path):
    cache_file = tmp_path / "usage.json"
    cache_file.write_text(json.dumps({"timestamp": time.time()}))
    assert _read_cache(str(cache_file), max_age=30) is None


def test_cache_preserves_rate_limited_status(tmp_path):
    cache_file = tmp_path / "usage.json"
    status = _rate_limited_status()
    _write_cache(str(cache_file), status)
    cached = _read_cache(str(cache_file), max_age=30)
    assert cached is not None
    assert cached.available is False
    assert cached.retry_after_seconds == 1800


def test_cache_preserves_error_status(tmp_path):
    cache_file = tmp_path / "usage.json"
    status = UsageStatus(available=False, error="Connection refused")
    _write_cache(str(cache_file), status)
    cached = _read_cache(str(cache_file), max_age=30)
    assert cached is not None
    assert cached.error == "Connection refused"


def test_write_cache_is_atomic(tmp_path):
    """Write should use temp+rename so a concurrent reader never sees partial data."""
    cache_file = tmp_path / "usage.json"
    status = _sample_status()
    _write_cache(str(cache_file), status)

    # File should exist and be valid JSON
    data = json.loads(cache_file.read_text())
    assert "timestamp" in data
    assert "status" in data


# ── check_usage_sync with cache ───────────────────────────────────


def test_check_usage_sync_returns_cached_on_hit(tmp_path):
    """check_usage_sync should return cached result without hitting network."""
    from unittest.mock import patch

    cache_file = tmp_path / "usage.json"
    status = _sample_status()
    _write_cache(str(cache_file), status)

    with patch("claude_budget.usage.httpx.get") as mock_get:
        from claude_budget.usage import check_usage_sync
        result = check_usage_sync(
            token="test-token",
            cache_path=str(cache_file),
            cache_ttl=30,
        )
        mock_get.assert_not_called()

    assert result.five_hour == pytest.approx(0.30)


def test_check_usage_sync_fetches_on_cache_miss(tmp_path):
    """check_usage_sync should fetch when cache is missing."""
    from unittest.mock import patch
    import httpx

    cache_file = tmp_path / "nonexistent.json"

    mock_resp = httpx.Response(
        status_code=200,
        json={"five_hour": {"utilization": 50.0}, "seven_day": {"utilization": 60.0}},
        request=httpx.Request("GET", "https://test.example.com/usage"),
    )

    with patch("claude_budget.usage.httpx.get", return_value=mock_resp) as mock_get:
        from claude_budget.usage import check_usage_sync
        result = check_usage_sync(
            token="test-token",
            cache_path=str(cache_file),
            cache_ttl=30,
        )
        mock_get.assert_called_once()

    assert result.five_hour == pytest.approx(0.50)
    # Should have written cache
    assert cache_file.exists()


def test_check_usage_sync_skips_cache_when_ttl_zero(tmp_path):
    """cache_ttl=0 should bypass cache entirely."""
    from unittest.mock import patch
    import httpx

    cache_file = tmp_path / "usage.json"
    _write_cache(str(cache_file), _sample_status())

    mock_resp = httpx.Response(
        status_code=200,
        json={"five_hour": {"utilization": 99.0}, "seven_day": {"utilization": 60.0}},
        request=httpx.Request("GET", "https://test.example.com/usage"),
    )

    with patch("claude_budget.usage.httpx.get", return_value=mock_resp) as mock_get:
        from claude_budget.usage import check_usage_sync
        result = check_usage_sync(
            token="test-token",
            cache_path=str(cache_file),
            cache_ttl=0,
        )
        mock_get.assert_called_once()

    assert result.five_hour == pytest.approx(0.99)


# ── check_usage (async) with cache ────────────────────────────────


async def test_check_usage_returns_cached_on_hit(tmp_path):
    """Async check_usage should return cached result without hitting network."""
    from unittest.mock import patch

    cache_file = tmp_path / "usage.json"
    _write_cache(str(cache_file), _sample_status())

    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        from claude_budget.usage import check_usage
        result = await check_usage(
            token="test-token",
            cache_path=str(cache_file),
            cache_ttl=30,
        )
        MockClient.return_value.__aenter__.return_value.get.assert_not_called()

    assert result.five_hour == pytest.approx(0.30)


async def test_check_usage_fetches_on_cache_miss(tmp_path):
    """Async check_usage should fetch and write cache on miss."""
    from unittest.mock import patch
    import httpx

    cache_file = tmp_path / "nonexistent.json"

    mock_resp = httpx.Response(
        status_code=200,
        json={"five_hour": {"utilization": 50.0}, "seven_day": {"utilization": 60.0}},
        request=httpx.Request("GET", "https://test.example.com/usage"),
    )

    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.return_value = mock_resp
        from claude_budget.usage import check_usage
        result = await check_usage(
            token="test-token",
            cache_path=str(cache_file),
            cache_ttl=30,
        )
        client.get.assert_called_once()

    assert result.five_hour == pytest.approx(0.50)
    assert cache_file.exists()
