"""E2E tests for `claude-budget watch` command."""

from collections.abc import Callable

from curtaincall import Terminal, expect


def describe_claude_budget_watch():

    def it_exits_immediately_when_already_above_target(terminal: Callable[..., Terminal]):
        """With target=0.01, should trigger immediately since usage > 1%."""
        term = terminal("claude-budget watch --target 0.01 --poll 5")
        expect(term).to_have_exited(timeout=15)
        assert term.exit_code == 0
        expect(term.get_by_text("TARGET REACHED")).to_be_visible()

    def it_shows_help(terminal: Callable[..., Terminal]):
        term = terminal("claude-budget watch --help")
        expect(term).to_have_exited(timeout=10)
        assert term.exit_code == 0
        expect(term.get_by_text("target")).to_be_visible()

    def it_requires_target_flag(terminal: Callable[..., Terminal]):
        term = terminal("claude-budget watch")
        expect(term).to_have_exited(timeout=10)
        assert term.exit_code != 0
