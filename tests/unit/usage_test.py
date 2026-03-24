"""Unit tests for usage limit checking."""

import json
import time
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from claude_budget.usage import (
    UsageStatus,
    check_usage,
    check_usage_sync,
    format_reset_time,
    load_token,
    parse_usage_response,
    _parse_retry_after,
)


SAMPLE_RESPONSE = {
    "five_hour": {
        "utilization": 30.0,
        "resets_at": "2026-03-24T22:00:00.060506+00:00",
    },
    "seven_day": {
        "utilization": 87.0,
        "resets_at": "2026-03-27T17:00:00.060523+00:00",
    },
    "seven_day_oauth_apps": None,
    "seven_day_opus": None,
    "seven_day_sonnet": {"utilization": 0.0, "resets_at": None},
    "seven_day_cowork": None,
    "iguana_necktie": None,
    "extra_usage": {
        "is_enabled": True,
        "monthly_limit": 15000,
        "used_credits": 14580.0,
        "utilization": 97.2,
    },
}


def _mock_response(status_code=200, json_data=None, headers=None):
    """Build a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        headers=headers or {},
        request=httpx.Request("GET", "https://test.example.com/usage"),
    )


# ── _parse_retry_after ─────────────────────────────────────────────


def test_parse_retry_after_integer():
    headers = httpx.Headers({"retry-after": "3600"})
    assert _parse_retry_after(headers) == 3600


def test_parse_retry_after_missing():
    headers = httpx.Headers({})
    assert _parse_retry_after(headers) is None


def test_parse_retry_after_non_integer():
    headers = httpx.Headers({"retry-after": "not-a-number"})
    assert _parse_retry_after(headers) is None


# ── parse_usage_response ───────────────────────────────────────────


def test_parse_usage_response_full():
    status = parse_usage_response(SAMPLE_RESPONSE)
    assert status.available is True
    assert status.five_hour == pytest.approx(0.30)
    assert status.seven_day == pytest.approx(0.87)
    assert status.five_hour_resets_at is not None
    assert status.seven_day_resets_at is not None
    assert status.extra_usage == SAMPLE_RESPONSE["extra_usage"]
    assert status.raw_response == SAMPLE_RESPONSE
    assert status.error is None


def test_parse_usage_response_converts_percentage_to_fraction():
    data = {"five_hour": {"utilization": 50.0}, "seven_day": {"utilization": 100.0}}
    status = parse_usage_response(data)
    assert status.five_hour == pytest.approx(0.50)
    assert status.seven_day == pytest.approx(1.0)


def test_parse_usage_response_missing_windows():
    status = parse_usage_response({})
    assert status.available is True
    assert status.five_hour is None
    assert status.seven_day is None


def test_parse_usage_response_parses_resets_at():
    status = parse_usage_response(SAMPLE_RESPONSE)
    assert status.five_hour_resets_at == datetime(
        2026, 3, 24, 22, 0, 0, 60506, tzinfo=timezone.utc,
    )


# ── load_token ─────────────────────────────────────────────────────


def test_load_token_valid(tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps({
        "claudeAiOauth": {"accessToken": "test-token-123", "refreshToken": "rt"}
    }))
    assert load_token(str(creds_file)) == "test-token-123"


def test_load_token_missing_file():
    assert load_token("/nonexistent/path/credentials.json") is None


def test_load_token_malformed(tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text("not json")
    assert load_token(str(creds_file)) is None


def test_load_token_missing_oauth_key(tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps({"other": "data"}))
    assert load_token(str(creds_file)) is None


# ── check_usage (async) ───────────────────────────────────────────


async def test_check_usage_available():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.return_value = _mock_response(200, SAMPLE_RESPONSE)
        status = await check_usage(token="test-token")
    assert status.available is True
    assert status.five_hour == pytest.approx(0.30)
    assert status.seven_day == pytest.approx(0.87)


async def test_check_usage_sends_auth_headers():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.return_value = _mock_response(200, SAMPLE_RESPONSE)
        await check_usage(token="my-token")
        _, kwargs = client.get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer my-token"
        assert kwargs["headers"]["anthropic-beta"] == "oauth-2025-04-20"


async def test_check_usage_rate_limited():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.return_value = _mock_response(429, headers={"retry-after": "1800"})
        status = await check_usage(token="test-token")
    assert status.available is False
    assert status.retry_after_seconds == 1800
    assert status.error is None


async def test_check_usage_rate_limited_no_retry_after():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.return_value = _mock_response(429)
        status = await check_usage(token="test-token")
    assert status.available is False
    assert status.retry_after_seconds is None


async def test_check_usage_server_error():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.return_value = _mock_response(500)
        status = await check_usage(token="test-token")
    assert status.available is False
    assert "500" in status.error


async def test_check_usage_connection_error():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.side_effect = httpx.ConnectError("refused")
        status = await check_usage(token="test-token")
    assert status.available is False
    assert status.error is not None


async def test_check_usage_timeout():
    with patch("claude_budget.usage.httpx.AsyncClient") as MockClient:
        client = MockClient.return_value.__aenter__.return_value
        client.get.side_effect = httpx.TimeoutException("timed out")
        status = await check_usage(token="test-token")
    assert status.available is False
    assert status.error is not None


async def test_check_usage_no_token_raises():
    with pytest.raises(RuntimeError, match="No OAuth token found"):
        await check_usage(token=None, credentials_path="/nonexistent/path")


# ── check_usage_sync ──────────────────────────────────────────────


def test_check_usage_sync_available():
    with patch("claude_budget.usage.httpx.get") as mock_get:
        mock_get.return_value = _mock_response(200, SAMPLE_RESPONSE)
        status = check_usage_sync(token="test-token")
    assert status.available is True
    assert status.five_hour == pytest.approx(0.30)


def test_check_usage_sync_no_token_raises():
    with pytest.raises(RuntimeError, match="No OAuth token found"):
        check_usage_sync(token=None, credentials_path="/nonexistent/path")


# ── format_reset_time ──────────────────────────────────────────────


def test_format_with_resets_at():
    resets = datetime(2026, 3, 24, 22, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 3, 24, 20, 30, 0, tzinfo=timezone.utc)
    with patch("claude_budget.usage.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat
        status = UsageStatus(available=True, five_hour_resets_at=resets)
        assert format_reset_time(status) == "Resets in 1h 30m"


def test_format_available():
    status = UsageStatus(available=True)
    assert format_reset_time(status) == "Available now"


def test_format_retry_after_minutes():
    status = UsageStatus(available=False, retry_after_seconds=1800)
    assert format_reset_time(status) == "Resets in 30m"


def test_format_retry_after_hours():
    status = UsageStatus(available=False, retry_after_seconds=5400)
    assert format_reset_time(status) == "Resets in 1h 30m"


def test_format_unknown():
    status = UsageStatus(available=False)
    assert format_reset_time(status) == "Unknown reset time"
