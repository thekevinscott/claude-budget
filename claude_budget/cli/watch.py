"""claude-budget watch -- block until usage reaches a target threshold."""

import json
import sys
import time
from typing import Annotated

from cyclopts import Parameter

from claude_budget.cli import app
from claude_budget.usage import check_usage_sync, format_reset_time

LOG_PATH = "/tmp/claude-budget-watch.jsonl"


def _format_status_line(status):
    """One-line summary of current usage."""
    parts = []
    if status.five_hour is not None:
        parts.append(f"5h: {status.five_hour * 100:.1f}%")
    if status.seven_day is not None:
        parts.append(f"7d: {status.seven_day * 100:.1f}%")
    if status.five_hour_resets_at:
        parts.append(f"resets {status.five_hour_resets_at.strftime('%H:%M UTC')}")
    return "  ".join(parts)


def _log_entry(log_file, event, status):
    """Append a JSONL entry to the log file."""
    if log_file is None:
        return
    entry = {
        "timestamp": time.time(),
        "event": event,
        "available": status.available,
        "five_hour": status.five_hour,
        "seven_day": status.seven_day,
        "error": status.error,
        "retry_after_seconds": status.retry_after_seconds,
    }
    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


@app.command
def watch(
    target: Annotated[float, Parameter(name=["--target", "-t"], help="5h utilization threshold (0.0-1.0)")],
    poll: Annotated[int, Parameter(name=["--poll", "-p"])] = 60,
    log: Annotated[str, Parameter(name=["--log", "-l"], help="JSONL log file path")] = LOG_PATH,
):
    """Block until 5h utilization reaches the target.

    Polls the usage endpoint every POLL seconds. Exits 0 when the 5-hour
    utilization reaches or exceeds TARGET. Status updates go to stderr;
    the final utilization value goes to stdout. Each poll is logged as
    JSONL to the log file for post-mortem analysis.

    Examples:
        claude-budget watch --target 0.85
        claude-budget watch -t 0.85 -p 30
    """
    print(f"Watching usage. Will exit when 5h >= {target * 100:.0f}%. Polling every {poll}s.", file=sys.stderr)
    print(f"Logging to {log}", file=sys.stderr)

    while True:
        try:
            status = check_usage_sync()
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(1)

        if status.error:
            _log_entry(log, "error", status)
            print(f"Warning: {status.error}", file=sys.stderr)
            time.sleep(poll)
            continue

        if not status.available:
            _log_entry(log, "rate_limited", status)
            print(f"Warning: rate limited on usage endpoint. {format_reset_time(status)}", file=sys.stderr)
            time.sleep(poll)
            continue

        if status.five_hour is not None and status.five_hour >= target:
            _log_entry(log, "target_reached", status)
            pct = status.five_hour * 100
            print(f"TARGET REACHED: 5h at {pct:.1f}% (target: {target * 100:.0f}%)", file=sys.stderr)
            print(f"{pct:.1f}")
            raise SystemExit(0)

        _log_entry(log, "poll", status)
        print(f"  {_format_status_line(status)}", file=sys.stderr)
        time.sleep(poll)
