---
name: conventions
description: The standing rules the board workflow runs on — how issues are created and scheduled, how testing is paced and scoped, and how Supabase migrations are applied. Read the file for the area you are working in; /pickup, /create-issue and /board cite these by name.
---

# Conventions

Three reference documents. They were user-level rules (`~/.claude/rules/`), which
never reach a cloud session — a thread clones repositories, not your home
directory. They ship inside this plugin so the skills that cite them can actually
reach them, locally and in a thread alike.

| Read this | When |
|---|---|
| [`issue-management.md`](./issue-management.md) | Creating, scheduling or dispatching issues. Holds the Birth Protocol, the Connections block, priority and dev semantics, and the board-reading cost rules |
| [`testing-standards.md`](./testing-standards.md) | Deciding what to test and when. Holds the cadence rule (full suite once, at ship), the tiers, test integrity, and user-flow verification |
| [`supabase-migrations.md`](./supabase-migrations.md) | Writing or applying a migration. Holds the hard bans and the parallel-worktree ledger repair |

**These are rules, not suggestions.** A skill that cites a section by name —
"`conventions` → *Findings: fix or file*" — means the rule decides, not your
judgment in the moment.

**Repo-specific rules live in the repository**, in its `CLAUDE.md` and
`.claude/rules/`. When a repo rule and one of these disagree, the repo wins for
that repo: these cover how work is organised, the repo covers how its own code
behaves.
