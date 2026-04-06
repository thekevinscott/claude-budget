# claude-budget

CLI watchdog for Anthropic usage budget monitoring.

## Quick start

Query your current usage with `uvx` (no install required):

```bash
uvx --from 'claude-budget @ git+ssh://git@github.com/thekevinscott/claude-budget.git' claude-budget usage
```

Get the raw JSON response:

```bash
uvx --from 'claude-budget @ git+ssh://git@github.com/thekevinscott/claude-budget.git' claude-budget usage --raw
```

## Commands

### `usage`

Query and print current Anthropic usage.

```
claude-budget usage [--raw]
```

- `--raw` / `-r` -- Print the full JSON response from the API

### `watch`

Block until 5-hour utilization reaches a target threshold. Useful as a watchdog alongside long-running pipelines.

```
claude-budget watch --target 0.85 [--poll 60] [--log /tmp/claude-budget-watch.jsonl]
```

- `--target` / `-t` -- 5h utilization threshold (0.0-1.0)
- `--poll` / `-p` -- Polling interval in seconds (default: 60)
- `--log` / `-l` -- JSONL log file path

## Requirements

- Python >= 3.12
- Claude Code OAuth credentials at `~/.claude/.credentials.json` (created automatically when you authenticate Claude Code)

## Install (optional)

If you prefer a persistent install:

```bash
uv tool install 'claude-budget @ git+ssh://git@github.com/thekevinscott/claude-budget.git'
```

Then run directly:

```bash
claude-budget usage
claude-budget watch -t 0.85
```
