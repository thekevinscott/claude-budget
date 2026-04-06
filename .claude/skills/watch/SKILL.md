---
name: claude-budget:watch
description: Monitor Anthropic usage and alert when a utilization target is reached. Run alongside background pipelines to stop them before budget is exhausted.
---

# Watch Usage

Run a budget watchdog alongside a background pipeline. The watchdog blocks until the 5-hour utilization reaches the target, then exits.

## Arguments

- `$ARGUMENTS` - Target utilization threshold as a percentage (e.g., `85` for 85%). Optional poll interval in seconds (e.g., `85 30` for 85% checked every 30s). Defaults to 85% polled every 60s.

## Usage

Parse `$ARGUMENTS` to extract target and optional poll interval. Convert the percentage to a fraction (divide by 100).

```bash
uvx --from git+https://github.com/thekevinscott/claude-budget claude-budget watch --target <fraction> --poll <seconds>
```

When the command exits, it means the target was reached. Take appropriate action (e.g., kill background pipelines, notify the user).

Every poll is logged as JSONL to `/tmp/claude-budget-watch.jsonl` (override with `--log <path>`). If something goes wrong, read the log for post-mortem analysis.

## Example Agent Workflow

1. Start the pipeline in the background
2. Start the watchdog in the background: `claude-budget watch --target 0.85 --poll 60`
3. When the watchdog exits, kill the pipeline
4. Report results to the user (read `/tmp/claude-budget-watch.jsonl` if needed for diagnostics)
