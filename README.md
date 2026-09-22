# gborh-board

A Claude Code plugin marketplace holding one plugin, **board-workflow**: the
board-driven development lifecycle that used to live in `~/.claude/`.

## Why this exists

User-level config (`~/.claude/CLAUDE.md`, `~/.claude/rules/`, `~/.claude/skills/`)
**never reaches a cloud session**. A Claude Code cloud session — including every
thread in a Claude Project — clones repositories, not your home directory. Skills
that only exist on one Mac are invisible there.

Packaging them as a plugin fixes that and versions them at the same time.

## What's in it

| Skill | Does |
|---|---|
| `pickup` | The full issue lifecycle: resolver → drift audit → plan → Brief gate → execute → verify → ship |
| `board` | Renders the priority board, open work only, epics in rank order |
| `create-issue` | The Birth Protocol — an issue born surveyed, fielded, parented and connected |
| `orchestrate` | Dispatches parallel work across the free devs |
| `rename-session` | Names sessions from claim comments rather than guesswork |
| `conventions` | The three standing rules the above cite: issue management, testing standards, Supabase migrations |

Plus three agents (`code-sweeper`, `codebase-analyzer`, `context-gatherer`) and
two commands (`/code-review`, `/commit`).

## Install

```bash
claude plugin marketplace add gborh1/claude-board-plugin
claude plugin install board-workflow@gborh-board
```

For a Claude Project, add it under **Project settings → Plugins** so every new
thread loads it.

## Notes for anyone editing this

- **Paths use `${CLAUDE_PLUGIN_ROOT}`**, never `~/.claude`. The variable resolves
  in skill and agent markdown; it does **not** expand inside Bash commands or
  Python, so scripts must derive their own paths.
- **`resolve-next.py` reads the board over the Projects v2 REST API** (version
  header `2026-03-10`), not GraphQL. That costs zero GraphQL points and is the
  only path that has any chance of working through a cloud session's GitHub
  proxy, which 403s Projects v2 GraphQL regardless of the token supplied.
- **One operation still needs GraphQL**: adding an option to an existing
  single-select field (`updateProjectV2Field`). There is no REST endpoint. It
  comes up when you add a dev, a module, or a priority level — never during a
  pickup.
- **Caches** live in `$PICKUP_CACHE_DIR` → `$XDG_CACHE_HOME/claude-pickup` →
  `~/.cache/claude-pickup`. Not in the plugin directory, which is not guaranteed
  writable.
