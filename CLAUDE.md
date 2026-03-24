# claude-budget

Usage budget management for the Anthropic Agent SDK.

## Permissions & Sandbox

- **Write ALL scripts to `/tmp`** using the Write tool, then run with Bash. Never use `cat > heredoc` or `python -c`. `/tmp` is whitelisted.
- **`ls` commands require permission** — use `Glob` tool instead.

## Testing

Tests use pytest with `asyncio_mode = "auto"`. Run with:

```bash
uv run pytest tests/unit/ -v
```

## Development Process

Use red/green TDD: write failing tests first, then implement. Unit tests mock everything except the module under test. Always write tests freely — never ask permission.

## Credential Isolation

Never read `~/.gitconfig`, SSH private keys, credential files, or shell config. Never echo environment variables containing secrets.
