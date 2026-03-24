"""Unit tests for usage limit checking."""

import time
import urllib.error
from unittest.mock import MagicMock, patch

from claude_budget.usage import (
    UsageStatus,
    check_usage,
    format_reset_time,
    parse_rate_limited_response,
    parse_retry_after,
    parse_usage_response,
)


# ── parse_retry_after ──────────────────────────────────────────────


def test_parse_retry_after_integer():
    assert parse_retry_after({"Retry-After": "3600"}) == 3600


def test_parse_retry_after_case_insensitive():
    assert parse_retry_after({"retry-after": "120"}) == 120


def test_parse_retry_after_missing():
    assert parse_retry_after({}) is None


def test_parse_retry_after_non_integer():
    assert parse_retry_after({"Retry-After": "not-a-number"}) is None


def test_parse_retry_after_none_value():
    assert parse_retry_after({"Retry-After": None}) is None


# ── parse_usage_response ──────────────────────────────────────────


def test_parse_usage_response_returns_available():
    data = {"five_hour": 0.3, "seven_day": 0.1}
    status = parse_usage_response(data)
    assert status.available is True
    assert status.retry_after_seconds is None
    assert status.reset_timestamp is None
    assert status.raw_response == data
    assert status.error is None


# ── parse_rate_limited_response ───────────────────────────────────


def test_parse_rate_limited_with_retry_after():
    headers = {"Retry-After": "3416"}
    status = parse_rate_limited_response(headers)
    assert status.available is False
    assert status.retry_after_seconds == 3416
    assert status.reset_timestamp is not None
    assert abs(status.reset_timestamp - (time.time() + 3416)) < 2
    assert status.error is None


def test_parse_rate_limited_without_retry_after():
    headers = {}
    status = parse_rate_limited_response(headers)
    assert status.available is False
    assert status.retry_after_seconds is None
    assert status.reset_timestamp is None


# ── check_usage ───────────────────────────────────────────────────


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen with configurable responses."""
    with patch("urllib.request.urlopen") as mock:

        def set_response(data: bytes):
            mock.reset_mock()
            resp = MagicMock()
            resp.read.return_value = data
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            mock.return_value = resp
            mock.side_effect = None

        def set_rate_limited(retry_after=None):
            mock.reset_mock()
            from email.message import Message
            hdrs = Message()
            if retry_after is not None:
                hdrs["Retry-After"] = str(retry_after)
            mock.side_effect = urllib.error.HTTPError(
                url="http://example.com", code=429,
                msg="Too Many Requests", hdrs=hdrs, fp=None,
            )

        def set_http_error(code, msg):
            mock.reset_mock()
            mock.side_effect = urllib.error.HTTPError(
                url="http://example.com", code=code,
                msg=msg, hdrs=None, fp=None,
            )

        def set_error(error):
            mock.reset_mock()
            mock.side_effect = error

        mock.set_response = set_response
        mock.set_rate_limited = set_rate_limited
        mock.set_http_error = set_http_error
        mock.set_error = set_error
        yield mock


import pytest


def test_check_usage_available(mock_urlopen):
    """200 response means API is available."""
    mock_urlopen.set_response(b'{"five_hour": 0.3, "seven_day": 0.1}')
    status = check_usage(endpoint="https://test.example.com/usage")
    assert status.available is True
    assert status.raw_response == {"five_hour": 0.3, "seven_day": 0.1}


def test_check_usage_rate_limited(mock_urlopen):
    """429 response means rate limited, parse Retry-After."""
    mock_urlopen.set_rate_limited(retry_after=1800)
    status = check_usage(endpoint="https://test.example.com/usage")
    assert status.available is False
    assert status.retry_after_seconds == 1800
    assert status.error is None


def test_check_usage_rate_limited_no_retry_after(mock_urlopen):
    """429 without Retry-After still reports unavailable."""
    mock_urlopen.set_rate_limited(retry_after=None)
    status = check_usage(endpoint="https://test.example.com/usage")
    assert status.available is False
    assert status.retry_after_seconds is None


def test_check_usage_server_error(mock_urlopen):
    """500 response returns error status, not exception."""
    mock_urlopen.set_http_error(500, "Internal Server Error")
    status = check_usage(endpoint="https://test.example.com/usage")
    assert status.available is False
    assert "500" in status.error


def test_check_usage_connection_error(mock_urlopen):
    """Network error returns error status, not exception."""
    mock_urlopen.set_error(ConnectionError("refused"))
    status = check_usage(endpoint="https://test.example.com/usage")
    assert status.available is False
    assert status.error is not None


def test_check_usage_timeout(mock_urlopen):
    """Timeout returns error status, not exception."""
    mock_urlopen.set_error(TimeoutError())
    status = check_usage(endpoint="https://test.example.com/usage")
    assert status.available is False
    assert status.error is not None


# ── format_reset_time ─────────────────────────────────────────────


def test_format_available():
    status = UsageStatus(available=True, retry_after_seconds=None, reset_timestamp=None, raw_response=None, error=None)
    assert format_reset_time(status) == "Available now"


def test_format_minutes():
    status = UsageStatus(available=False, retry_after_seconds=1800, reset_timestamp=None, raw_response=None, error=None)
    assert format_reset_time(status) == "Resets in 30m"


def test_format_hours_and_minutes():
    status = UsageStatus(available=False, retry_after_seconds=5400, reset_timestamp=None, raw_response=None, error=None)
    assert format_reset_time(status) == "Resets in 1h 30m"


def test_format_unknown():
    status = UsageStatus(available=False, retry_after_seconds=None, reset_timestamp=None, raw_response=None, error=None)
    assert format_reset_time(status) == "Unknown reset time"
