"""claude-budget usage -- query and print current Anthropic usage."""

import json
import sys
from typing import Annotated

from cyclopts import Parameter

from claude_budget.cli import app
from claude_budget.usage import check_usage_sync, format_reset_time


@app.command
def usage(
    raw: Annotated[bool, Parameter(name=["--raw", "-r"], help="Print raw JSON response")] = False,
):
    """Query current Anthropic usage and print the result.

    Examples:
        claude-budget usage
        claude-budget usage --raw
    """
    try:
        status = check_usage_sync(cache_ttl=0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if raw and status.raw_response:
        print(json.dumps(status.raw_response, indent=2, default=str))
        raise SystemExit(0)

    if status.error:
        print(f"Error: {status.error}", file=sys.stderr)
        raise SystemExit(1)

    if not status.available:
        print(f"Usage endpoint unavailable. {format_reset_time(status)}", file=sys.stderr)
        raise SystemExit(1)

    if status.five_hour is not None:
        print(f"5h utilization: {status.five_hour * 100:.1f}%")
    if status.seven_day is not None:
        print(f"7d utilization: {status.seven_day * 100:.1f}%")
    print(format_reset_time(status))
