"""claude-budget CLI."""

from cyclopts import App

app = App(
    name="claude-budget",
    help="Anthropic usage budget management.",
)


def main():
    app()


# Import commands to register them
from claude_budget.cli import usage, watch  # noqa: E402, F401
