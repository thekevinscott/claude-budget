# claude-budget

Usage budget management for the Anthropic Agent SDK.

## Permissions & Sandbox

- **Write ALL scripts to `/tmp`** using the Write tool, then run with Bash. Never use `cat > heredoc` or `python -c`. `/tmp` is whitelisted.
- **`ls` commands require permission** — use `Glob` tool instead.

## Testing

### Red/Green Development

Follow **red/green** (test-first) methodology:

1. **Write the test first** — it must capture the desired behavior
2. **Run it and confirm it fails (RED)** — do NOT proceed until the test turns red reliably
3. **Make the minimal change to pass (GREEN)** — only then write the implementation
4. Refactor if needed, keeping tests green

Always write tests freely — never ask permission.

### TDD Order: Outside-In

Tests are written **before** implementation, starting from the outermost layer:

1. **E2E test first** — proves the feature works from the user's perspective (uses curtaincall for CLI testing)
2. **Integration test** — proves internal modules compose correctly, with mocked external dependencies
3. **Unit tests** — written as you implement each piece

### When to Write What

**Does the commit change the public-facing API (CLI, SDK, config)?**
- Yes → **e2e test + integration test required**, plus unit tests as you go
- No → Check if adequate e2e/integration coverage already exists:
  - Adequate → unit tests only
  - Gaps → add the missing e2e/integration tests, plus unit tests

**Always write unit tests.** The question is whether you also need e2e and integration tests.

### Test Locations

- **Unit tests**: `tests/unit/`
- **Integration tests**: `tests/integration/`
- **E2E tests**: `tests/e2e/`

### Running Tests

```bash
uv run pytest tests/unit/ -v          # Unit tests
uv run pytest tests/integration/ -v   # Integration tests
uv run pytest tests/e2e/ -v           # E2E tests (uses curtaincall)
```

### Test Infrastructure

- E2E tests use **curtaincall** (`Terminal`, `expect`) for PTY-based CLI testing
- Mock all imports in unit tests to establish isolated coverage
- Mock external dependencies in integration tests, but avoid mocking anything internal
- Do not mock anything in e2e tests
- Prefer `pytest.fixture` over inline `with patch(...)` — use `autouse=True` when the mock applies to all tests in scope
- Use `@pytest.mark.parametrize` when testing multiple inputs/outputs for the same logic
- Use readable multi-line strings for test fixtures, never escaped `\n` strings

## Credential Isolation

Never read `~/.gitconfig`, SSH private keys, credential files, or shell config. Never echo environment variables containing secrets.
