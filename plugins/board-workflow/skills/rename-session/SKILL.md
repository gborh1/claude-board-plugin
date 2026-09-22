---
name: rename-session
description: Rename generically-titled sessions (usually "Pickup") to what each is actually working on, resolved from the board's claim comments rather than guessed. Use whenever the user asks to rename sessions, update session names, or says several sessions are all called the same thing.
---

# /rename-session — name each session after its real work

Sessions started by a slash command inherit that command's name, so a fleet of
parallel pickups all read **"Pickup"** and become indistinguishable. This
renames them from evidence, never from inference.

**Scope:** only sessions with a generic title (`Pickup`, `Board`, `Code review`,
…). Leave user-authored titles alone — `set_session_title` preserves them
anyway, but don't waste the call. The current session cannot be renamed.

---

## Step 1 — list

```
mcp__ccd_session_mgmt__list_sessions   (limit 40)
```

Note each candidate's `sessionId`, `cwd` (the **worktree name** is the last path
segment — this is the join key), `branch`, and `isRunning`.

## Step 2 — resolve worktree → issue from the claim comments (the reliable path)

**Do not read transcripts first.** Every `/pickup` writes a claim comment on its
issue containing the worktree name, so the mapping is a lookup, not a guess:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --list | grep -i 'In Progress'
```

Then, for each In Progress issue, pull the marker:

```bash
for n in <issues>; do echo -n "#$n → "; \
  gh issue view $n --repo <OWNER>/<REPO> --json comments -q '.comments[].body' \
  | grep -oE 'pickup:claim dev=[A-Za-z]+ wt=[A-Za-z0-9-]+' | tail -1; echo; done
```

`wt=<worktree>` joins straight to the session's `cwd`. Use the **last** marker —
an issue may have been re-claimed. This also yields the dev name for free.

## Step 3 — fall back to the transcript only when the join fails

A session with no matching claim (not a pickup, claim never written, different
repo) needs its subject read directly:

```
mcp__ccd_session_mgmt__list_events   (session_id, limit ~10)
```

Recent events are often bare tool calls. Page backwards with `before_uuid`, or
search across sessions for a distinguishing term:

```
mcp__ccd_session_mgmt__search_session_transcripts   (query: "<term>")
```

**If a session has no identifiable subject — interrupted before claiming
anything, or zero substantive turns — leave it named as-is and say so.** Never
invent a subject to satisfy the format.

## Step 4 — rename

```
mcp__ccd_session_mgmt__set_session_title   (session_id, title)
```

Send them in one message when renaming several.

**Title shape:** `<what the work does> (#N)` — 3–6 words, sentence case, the
issue number last. The title is a spine label, so lead with the distinguishing
noun.

- `Deterministic last-updated date (#462)` · `Re-check schedule + early stop (#491)`
- A lead + rider on one branch → both numbers: `Verify fit-rejections + audit trail (#492/#494)`
- Planning-KIND issue → keep the `Plan:` prefix: `Plan: dashboard content review (#432)`
- Not `Pickup #462`, not the issue title verbatim, not the branch name.

## Step 5 — report, and surface what the mapping revealed

A compact table: worktree → new title → dev.

Then flag anything the join exposed, because this procedure reads the live board
and routinely catches things nobody was looking for:

- **A dev on 2+ In Progress issues** — a double-booking (see `/board` Step 1b and
  pickup Phase 1.2b). Offer to reassign the later claim.
- **Issues that shipped** since the last look, or a bucket that has rolled over.
- **A session with no claim at all** — either not a pickup, or a pickup that ran
  unclaimed, which is worth saying out loud.

## Errors

- **Renaming the current session** → not possible; skip it and say so.
- **`list_events` returns only tool calls** → page back with `before_uuid`; if
  still opaque after ~2 pages, use `search_session_transcripts`.
- **Session in a different repo** → resolve against *that* repo's board, or fall
  back to Step 3. Never map a worktree to an issue in the wrong repo.
