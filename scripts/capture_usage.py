"""Capture response from the Anthropic usage endpoint.

Uses Claude Code's stored OAuth credentials to authenticate.
Saves the full response to output/ as timestamped JSON files.

Usage:
    uv run python scripts/capture_usage.py [--label LABEL]

Examples:
    uv run python scripts/capture_usage.py --label extra-usage-on
    uv run python scripts/capture_usage.py --label after-reset
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from claude_budget.usage import USAGE_ENDPOINT, _build_headers, load_token

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def capture(token: str) -> dict:
    """Hit the usage endpoint and capture everything."""
    try:
        resp = httpx.get(
            USAGE_ENDPOINT,
            headers=_build_headers(token),
            timeout=15,
        )
        result = {
            "status": resp.status_code,
            "headers": dict(resp.headers),
        }
        try:
            result["body"] = resp.json()
        except Exception:
            result["body"] = resp.text
        return result
    except Exception as e:
        return {
            "status": None,
            "error_type": type(e).__name__,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Capture Anthropic usage endpoint response")
    parser.add_argument("--label", type=str, default=None, help="Label suffix for the output file")
    args = parser.parse_args()

    token = load_token()
    if token is None:
        print("Error: No OAuth token found in ~/.claude/.credentials.json")
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{args.label}" if args.label else ""
    filename = f"usage-{timestamp}{suffix}.json"

    result = capture(token)
    result["captured_at"] = now.isoformat()

    out_path = OUTPUT_DIR / filename
    out_path.write_text(json.dumps(result, indent=2, default=str) + "\n")

    print(f"Status: {result.get('status')}")
    if "headers" in result:
        retry = result["headers"].get("retry-after")
        if retry:
            print(f"Retry-After: {retry}s")
    print(f"Saved to: {out_path}")
    print(json.dumps(result.get("body", result), indent=2, default=str))


if __name__ == "__main__":
    main()
