"""Check Anthropic usage limits via the OAuth usage endpoint.

Reads OAuth credentials from Claude Code's local config
(~/.claude/.credentials.json) and hits the usage endpoint with
Bearer auth. Falls back gracefully when credentials or the
endpoint are unavailable.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
REQUEST_TIMEOUT = 10


@dataclass
class UsageStatus:
    """Current usage limit status."""

    available: bool
    five_hour: float | None = None  # 0.0-1.0 utilization
    five_hour_resets_at: datetime | None = None
    seven_day: float | None = None  # 0.0-1.0 utilization
    seven_day_resets_at: datetime | None = None
    extra_usage: dict | None = None
    retry_after_seconds: int | None = None
    reset_timestamp: float | None = None
    raw_response: dict | None = None
    error: str | None = None


def load_token(credentials_path: str = CREDENTIALS_PATH) -> str | None:
    """Load OAuth access token from Claude Code's credentials file."""
    try:
        with open(credentials_path) as f:
            creds = json.load(f)
        return creds.get("claudeAiOauth", {}).get("accessToken")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _parse_resets_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_retry_after(headers: httpx.Headers) -> int | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_usage_response(data: dict) -> UsageStatus:
    """Parse a 200 response from the usage endpoint."""
    five_hour = data.get("five_hour") or {}
    seven_day = data.get("seven_day") or {}

    five_hour_util = five_hour.get("utilization")
    seven_day_util = seven_day.get("utilization")

    fh = five_hour_util / 100.0 if isinstance(five_hour_util, (int, float)) else None
    sd = seven_day_util / 100.0 if isinstance(seven_day_util, (int, float)) else None

    fh_resets = _parse_resets_at(five_hour.get("resets_at"))
    sd_resets = _parse_resets_at(seven_day.get("resets_at"))

    return UsageStatus(
        available=True,
        five_hour=fh,
        five_hour_resets_at=fh_resets,
        seven_day=sd,
        seven_day_resets_at=sd_resets,
        extra_usage=data.get("extra_usage"),
        raw_response=data,
    )


def _parse_rate_limited(headers: httpx.Headers) -> UsageStatus:
    import time

    retry_after = _parse_retry_after(headers)
    reset_ts = time.time() + retry_after if retry_after is not None else None
    return UsageStatus(
        available=False,
        retry_after_seconds=retry_after,
        reset_timestamp=reset_ts,
    )


def _build_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    }


def _resolve_token(token: str | None, credentials_path: str) -> str:
    if token is None:
        token = load_token(credentials_path)
    if token is None:
        raise RuntimeError(
            f"No OAuth token found. Expected Claude Code credentials at {credentials_path}"
        )
    return token


def _handle_response(resp: httpx.Response) -> UsageStatus:
    if resp.status_code == 429:
        return _parse_rate_limited(resp.headers)
    if resp.status_code >= 400:
        return UsageStatus(
            available=False,
            error=f"HTTP {resp.status_code}: {resp.reason_phrase}",
        )
    return parse_usage_response(resp.json())


async def check_usage(
    endpoint: str = USAGE_ENDPOINT,
    timeout: int = REQUEST_TIMEOUT,
    token: str | None = None,
    credentials_path: str = CREDENTIALS_PATH,
) -> UsageStatus:
    """Check current Anthropic usage status.

    Reads OAuth token from Claude Code's credentials file and hits the
    usage endpoint. Returns UsageStatus; never raises (except for missing credentials).
    """
    token = _resolve_token(token, credentials_path)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                endpoint,
                headers=_build_headers(token),
                timeout=timeout,
            )
            return _handle_response(resp)
    except Exception as e:
        return UsageStatus(available=False, error=str(e))


def check_usage_sync(
    endpoint: str = USAGE_ENDPOINT,
    timeout: int = REQUEST_TIMEOUT,
    token: str | None = None,
    credentials_path: str = CREDENTIALS_PATH,
) -> UsageStatus:
    """Synchronous version of check_usage for scripts and non-async contexts."""
    token = _resolve_token(token, credentials_path)
    try:
        resp = httpx.get(
            endpoint,
            headers=_build_headers(token),
            timeout=timeout,
        )
        return _handle_response(resp)
    except Exception as e:
        return UsageStatus(available=False, error=str(e))


def format_reset_time(status: UsageStatus) -> str:
    """Format the reset time as a human-readable string."""
    if status.five_hour_resets_at is not None:
        now = datetime.now(timezone.utc)
        delta = status.five_hour_resets_at - now
        total_seconds = max(0, int(delta.total_seconds()))
        minutes = total_seconds // 60
        if minutes >= 60:
            hours = minutes // 60
            remaining_mins = minutes % 60
            return f"Resets in {hours}h {remaining_mins}m"
        return f"Resets in {minutes}m"
    if status.available:
        return "Available now"
    if status.retry_after_seconds is not None:
        minutes = status.retry_after_seconds // 60
        if minutes >= 60:
            hours = minutes // 60
            remaining_mins = minutes % 60
            return f"Resets in {hours}h {remaining_mins}m"
        return f"Resets in {minutes}m"
    return "Unknown reset time"
