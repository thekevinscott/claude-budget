"""Integration tests for the watch polling loop.

Tests the full watch flow with mocked usage endpoint responses,
verifying that the CLI correctly transitions between polling and exit.
"""

import json
import time
from unittest.mock import patch

import pytest

from claude_budget.usage import UsageStatus


def _make_status(five_hour=None, available=True, error=None, retry_after=None):
    reset_ts = time.time() + retry_after if retry_after is not None else None
    return UsageStatus(
        available=available,
        five_hour=five_hour,
        retry_after_seconds=retry_after,
        reset_timestamp=reset_ts,
        error=error,
    )


def describe_watch_polling():

    def it_exits_when_target_reached():
        """Watch should exit 0 when utilization >= target."""
        statuses = [_make_status(five_hour=0.50), _make_status(five_hour=0.90)]
        call_count = 0

        def mock_check():
            nonlocal call_count
            status = statuses[min(call_count, len(statuses) - 1)]
            call_count += 1
            return status

        with (
            patch("claude_budget.cli.watch.check_usage_sync", side_effect=mock_check),
            patch("claude_budget.cli.watch.time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            from claude_budget.cli.watch import watch
            watch(target=0.85, poll=1)

        assert exc_info.value.code == 0
        assert call_count == 2

    def it_treats_429_as_transient_and_keeps_polling():
        """Watch should not exit on 429 — it's a transient rate limit, not budget exhaustion."""
        statuses = [
            _make_status(available=False, retry_after=60),  # 429 on monitoring endpoint
            _make_status(available=False, retry_after=30),  # another 429
            _make_status(five_hour=0.90),                   # real reading above target
        ]
        call_count = 0

        def mock_check():
            nonlocal call_count
            status = statuses[min(call_count, len(statuses) - 1)]
            call_count += 1
            return status

        with (
            patch("claude_budget.cli.watch.check_usage_sync", side_effect=mock_check),
            patch("claude_budget.cli.watch.time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            from claude_budget.cli.watch import watch
            watch(target=0.85, poll=1)

        assert exc_info.value.code == 0
        assert call_count == 3  # polled through the 429s

    def it_continues_polling_on_error():
        """Watch should keep polling when endpoint returns an error."""
        statuses = [
            _make_status(error="Connection refused"),
            _make_status(error="Timeout"),
            _make_status(five_hour=0.90),
        ]
        call_count = 0

        def mock_check():
            nonlocal call_count
            status = statuses[min(call_count, len(statuses) - 1)]
            call_count += 1
            return status

        with (
            patch("claude_budget.cli.watch.check_usage_sync", side_effect=mock_check),
            patch("claude_budget.cli.watch.time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            from claude_budget.cli.watch import watch
            watch(target=0.85, poll=1)

        assert exc_info.value.code == 0
        assert call_count == 3

    def it_exits_1_on_missing_credentials():
        """Watch should exit 1 when credentials are missing."""
        with (
            patch("claude_budget.cli.watch.check_usage_sync", side_effect=RuntimeError("No token")),
            pytest.raises(SystemExit) as exc_info,
        ):
            from claude_budget.cli.watch import watch
            watch(target=0.85, poll=1)

        assert exc_info.value.code == 1

    def it_writes_jsonl_log_when_log_path_given(tmp_path):
        """Watch should write one JSONL entry per poll to the log file."""
        log_file = tmp_path / "watch.jsonl"
        statuses = [
            _make_status(five_hour=0.50),
            _make_status(available=False, retry_after=60),
            _make_status(five_hour=0.90),
        ]
        call_count = 0

        def mock_check():
            nonlocal call_count
            status = statuses[min(call_count, len(statuses) - 1)]
            call_count += 1
            return status

        with (
            patch("claude_budget.cli.watch.check_usage_sync", side_effect=mock_check),
            patch("claude_budget.cli.watch.time.sleep"),
            pytest.raises(SystemExit),
        ):
            from claude_budget.cli.watch import watch
            watch(target=0.85, poll=1, log=str(log_file))

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

        entries = [json.loads(line) for line in lines]
        assert entries[0]["event"] == "poll"
        assert entries[0]["five_hour"] == 0.50
        assert entries[1]["event"] == "rate_limited"
        assert entries[2]["event"] == "target_reached"
        assert entries[2]["five_hour"] == 0.90

        # Each entry should have a timestamp
        for entry in entries:
            assert "timestamp" in entry
