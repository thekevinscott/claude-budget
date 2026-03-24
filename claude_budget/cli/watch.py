"""claude-budget watch -- block until usage reaches a target threshold."""

import sys
import time
from typing import Annotated

from cyclopts import Parameter

from claude_budget.cli import app
from claude_budget.usage import check_usage_sync, format_reset_time


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


@app.command
def watch(
    target: Annotated[float, Parameter(name=["--target", "-t"], help="5h utilization threshold (0.0-1.0)")],
    poll: Annotated[int, Parameter(name=["--poll", "-p"])] = 60,
):
    """Block until 5h utilization reaches the target.

    Polls the usage endpoint every POLL seconds. Exits 0 when the 5-hour
    utilization reaches or exceeds TARGET. Status updates go to stderr;
    the final utilization value goes to stdout.

    Examples:
        claude-budget watch --target 0.85
        claude-budget watch -t 0.85 -p 30
    """
    print(f"Watching usage. Will exit when 5h >= {target * 100:.0f}%. Polling every {poll}s.", file=sys.stderr)

    while True:
        try:
            status = check_usage_sync()
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(1)

        if status.error:
            print(f"Warning: {status.error}", file=sys.stderr)
            time.sleep(poll)
            continue

        if not status.available:
            print(f"BUDGET EXCEEDED (rate limited). {format_reset_time(status)}", file=sys.stderr)
            print("exceeded")
            raise SystemExit(0)

        if status.five_hour is not None and status.five_hour >= target:
            pct = status.five_hour * 100
            print(f"TARGET REACHED: 5h at {pct:.1f}% (target: {target * 100:.0f}%)", file=sys.stderr)
            print(f"{pct:.1f}")
            raise SystemExit(0)

        print(f"  {_format_status_line(status)}", file=sys.stderr)
        time.sleep(poll)
