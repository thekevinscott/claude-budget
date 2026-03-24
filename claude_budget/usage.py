"""Check Anthropic API usage limits.

Hits the undocumented OAuth usage endpoint to determine remaining quota
and reset time. Falls back gracefully when the endpoint is unavailable.
"""

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
REQUEST_TIMEOUT = 10


@dataclass
class UsageStatus:
    """Current usage limit status."""

    available: bool  # True if calls can be made right now
    retry_after_seconds: int | None  # Seconds until limit resets (None if available)
    reset_timestamp: float | None  # Unix timestamp of reset (None if available)
    raw_response: dict | None  # Full response body if available
    error: str | None  # Error message if the check itself failed


def parse_retry_after(headers: dict) -> int | None:
    """Extract Retry-After value from response headers."""
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_usage_response(data: dict) -> UsageStatus:
    """Parse a successful usage endpoint response into UsageStatus."""
    return UsageStatus(
        available=True,
        retry_after_seconds=None,
        reset_timestamp=None,
        raw_response=data,
        error=None,
    )


def parse_rate_limited_response(headers: dict) -> UsageStatus:
    """Parse a 429 response into UsageStatus with retry timing."""
    retry_after = parse_retry_after(headers)
    reset_ts = time.time() + retry_after if retry_after is not None else None
    return UsageStatus(
        available=False,
        retry_after_seconds=retry_after,
        reset_timestamp=reset_ts,
        raw_response=None,
        error=None,
    )


def check_usage(endpoint: str = USAGE_ENDPOINT, timeout: int = REQUEST_TIMEOUT) -> UsageStatus:
    """Check current Anthropic API usage status.

    Returns UsageStatus indicating whether API calls can be made,
    and if not, when the limit resets.

    This hits an undocumented endpoint — it may break without notice.
    Failures are returned as UsageStatus with error set, never raised.
    """
    try:
        req = urllib.request.Request(endpoint, headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json
            data = json.loads(resp.read())
            return parse_usage_response(data)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return parse_rate_limited_response(dict(e.headers))
        return UsageStatus(
            available=False,
            retry_after_seconds=None,
            reset_timestamp=None,
            raw_response=None,
            error=f"HTTP {e.code}: {e.reason}",
        )
    except Exception as e:
        return UsageStatus(
            available=False,
            retry_after_seconds=None,
            reset_timestamp=None,
            raw_response=None,
            error=str(e),
        )


def format_reset_time(status: UsageStatus) -> str:
    """Format the reset time as a human-readable string."""
    if status.available:
        return "Available now"
    if status.retry_after_seconds is None:
        return "Unknown reset time"
    minutes = status.retry_after_seconds // 60
    if minutes >= 60:
        hours = minutes // 60
        remaining_mins = minutes % 60
        return f"Resets in {hours}h {remaining_mins}m"
    return f"Resets in {minutes}m"
