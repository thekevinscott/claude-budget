---
name: claude-budget:usage
description: Show current Anthropic usage budget status (5h, 7d, extra usage).
---

# Check Usage

Run the following command and present the results to the user:

```bash
uv run --project /home/duncan/work/code/projects/claude-budget claude-budget usage
```

Present the output clearly. If the 5-hour utilization is above 80%, warn that usage is high.
