"""Capture raw response from the Anthropic usage endpoint.

Saves status code, headers, and body to output/ as timestamped JSON files.
Run under different account states to map out the response format.

Usage:
    uv run python scripts/capture_usage.py [--label LABEL]

The --label flag adds a suffix to the filename, e.g.:
    uv run python scripts/capture_usage.py --label extra-usage-on
    uv run python scripts/capture_usage.py --label extra-usage-off
    uv run python scripts/capture_usage.py --label after-reset
"""

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def capture() -> dict:
    """Hit the usage endpoint and capture everything."""
    req = urllib.request.Request(USAGE_ENDPOINT, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body_raw = resp.read()
            try:
                body = json.loads(body_raw)
            except json.JSONDecodeError:
                body = body_raw.decode("utf-8", errors="replace")
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": body,
            }
    except urllib.error.HTTPError as e:
        body_raw = e.read()
        try:
            body = json.loads(body_raw)
        except (json.JSONDecodeError, Exception):
            body = body_raw.decode("utf-8", errors="replace")
        return {
            "status": e.code,
            "reason": e.reason,
            "headers": dict(e.headers),
            "body": body,
        }
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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{args.label}" if args.label else ""
    filename = f"usage-{timestamp}{suffix}.json"

    result = capture()
    result["captured_at"] = now.isoformat()

    out_path = OUTPUT_DIR / filename
    out_path.write_text(json.dumps(result, indent=2, default=str) + "\n")

    print(f"Status: {result.get('status')}")
    if "headers" in result:
        retry = result["headers"].get("Retry-After") or result["headers"].get("retry-after")
        if retry:
            print(f"Retry-After: {retry}s")
    print(f"Saved to: {out_path}")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
