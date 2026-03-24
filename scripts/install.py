"""Install claude-budget skills into ~/.claude/skills/ via symlinks.

Usage:
    uv run python scripts/install.py
"""

from pathlib import Path

PROJECT_SKILLS = Path(__file__).resolve().parent.parent / ".claude" / "skills"
USER_SKILLS = Path.home() / ".claude" / "skills"


def main():
    USER_SKILLS.mkdir(parents=True, exist_ok=True)

    for src in PROJECT_SKILLS.iterdir():
        if not src.is_dir():
            continue
        dest = USER_SKILLS / src.name
        if dest.is_symlink() or dest.exists():
            dest.unlink() if dest.is_symlink() else None
            if dest.exists():
                print(f"Skipping {dest} (already exists and is not a symlink)")
                continue
        dest.symlink_to(src)
        print(f"Linked {dest} -> {src}")

    print("\nInstalled. Skill available as /claude-budget:usage")


if __name__ == "__main__":
    main()
