"""E2E tests for `claude-budget usage` command."""

from collections.abc import Callable

from curtaincall import Terminal, expect


def describe_claude_budget_usage():

    def it_exits_0_and_shows_utilization(terminal: Callable[..., Terminal]):
        term = terminal("claude-budget usage")
        expect(term).to_have_exited(timeout=15)
        assert term.exit_code == 0
        expect(term.get_by_text("5h:")).to_be_visible()

    def it_shows_7d_utilization(terminal: Callable[..., Terminal]):
        term = terminal("claude-budget usage")
        expect(term).to_have_exited(timeout=15)
        expect(term.get_by_text("7d:")).to_be_visible()

    def it_shows_help(terminal: Callable[..., Terminal]):
        term = terminal("claude-budget usage --help")
        expect(term).to_have_exited(timeout=10)
        assert term.exit_code == 0
        expect(term.get_by_text("usage")).to_be_visible()
