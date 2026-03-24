"""claude-budget usage -- show current usage status."""

import sys

from claude_budget.cli import app
from claude_budget.usage import check_usage_sync, format_reset_time


@app.command
def usage():
    """Show current Anthropic usage status."""
    try:
        status = check_usage_sync()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if status.error:
        print(f"Error: {status.error}", file=sys.stderr)
        raise SystemExit(1)

    if not status.available:
        retry = f" ({format_reset_time(status)})" if status.retry_after_seconds else ""
        print(f"Rate limited{retry}")
        raise SystemExit(0)

    lines = []
    if status.five_hour is not None:
        pct = status.five_hour * 100
        reset = ""
        if status.five_hour_resets_at:
            reset = f"  resets {status.five_hour_resets_at.strftime('%H:%M UTC')}"
        lines.append(f"5h:  {pct:5.1f}%{reset}")

    if status.seven_day is not None:
        pct = status.seven_day * 100
        reset = ""
        if status.seven_day_resets_at:
            reset = f"  resets {status.seven_day_resets_at.strftime('%Y-%m-%d %H:%M UTC')}"
        lines.append(f"7d:  {pct:5.1f}%{reset}")

    if status.extra_usage:
        eu = status.extra_usage
        enabled = "on" if eu.get("is_enabled") else "off"
        used = eu.get("used_credits", 0)
        limit = eu.get("monthly_limit", 0)
        util = eu.get("utilization", 0)
        lines.append(f"Extra usage: {enabled}  ${used:.0f}/${limit:.0f} ({util:.1f}%)")

    print("\n".join(lines))
