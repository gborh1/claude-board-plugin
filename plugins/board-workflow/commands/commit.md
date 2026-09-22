---
description: Commit staged or all recent changes with a descriptive message
---

Commit changes with a well-crafted commit message.

## Process

1. Check `git status` for staged and unstaged changes
2. If no files are staged, stage the relevant changed files first
3. Create the commit with a descriptive message

## Commit Message Format

- Use conventional commit prefixes: `feat`, `fix`, `chore`, `refactor`, `docs`, `style`, `test`, `perf`
- First line: concise summary (50 chars or less ideal)
- If multiple changes: add bullet points for details after a blank line

**Example:**
```
feat: add responsive text wrapping to dashboard header

- Update max-width from 2xl to 3xl
- Add text-wrap balance for better line distribution
```

## Rules

- Do NOT include "Generated with Claude Code" or any AI signature
- Do NOT include "Co-Authored-By" lines
- Keep it clean and professional - just the commit message
