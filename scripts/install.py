"""Install claude-budget skills into ~/.claude/skills/ via symlinks.

Usage:
    uv run python scripts/install.py
"""

from pathlib import Path

PROJECT_SKILLS = Path(__file__).resolve().parent.parent / ".claude" / "skills"
USER_SKILLS = Path.home() / ".claude" / "skills"


def main():
    USER_SKILLS.mkdir(parents=True, exist_ok=True)

    installed = []
    for src in sorted(PROJECT_SKILLS.iterdir()):
        if not src.is_dir():
            continue
        dest = USER_SKILLS / src.name
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            print(f"Skipping {dest} (already exists and is not a symlink)")
            continue
        dest.symlink_to(src)
        installed.append(src.name)
        print(f"Linked {dest} -> {src}")

    if installed:
        print(f"\nInstalled {len(installed)} skill(s): {', '.join(installed)}")
    else:
        print("\nNo skills installed.")


if __name__ == "__main__":
    main()
