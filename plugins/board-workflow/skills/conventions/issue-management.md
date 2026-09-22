# Issue Management

GitHub Projects + `gh` CLI. Issues describe WHAT and WHY, never HOW — implementation is decided at pickup.

## Reading the board — never `gh project item-list`

`gh project item-list` costs **~1.2 GraphQL points per item**: on a 400-item board
that is ~500 points a call, so eight calls drain the entire 5,000/hr budget and
every parallel session grinds to a halt. It happened on 2026-08-09 — two sessions
made 8 calls in 9 minutes and took the whole hour down.

Use these instead. All three are cheap or free:

| You need | Command | Cost |
|---|---|---|
| The whole board, ranked | `python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --list` | **0 GraphQL pts** — ported to the Projects v2 REST API 2026-09-19; ~5 requests on the separate `core` pool |
| One item's `ITEM_ID` for a field edit | `python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --item-id <N>` | **0** — reads the cached id-map |
| The `ITEM_ID` of an issue you just added | `gh project item-add … --format json -q .id` already returns it | free, you were calling it anyway |
| Open issue titles/bodies (dupe check, `Depends-on` grep) | `gh issue list --state open --limit 500 --json number,title,body` | ~5 pts |

If `--item-id` misses, run bare `resolve-next.py` once to refresh the id-map —
still far cheaper than one `item-list`. When reading raw issue data, prefer REST
(`gh api repos/…/issues`) — it draws on a separate 5,000/hr pool that board work
never touches.

Check the budget with `gh api rate_limit --jq .resources.graphql` (free). Board reads no longer
touch that pool at all — the resolver uses REST (`core`). GraphQL is left only as a fallback, and
for the one operation REST has no endpoint for: adding an option to an existing single-select
field (`updateProjectV2Field`).

## Findings: fix or file

A **work request** is something the owner asked for — that always gets an issue before work starts.
A **finding** is something you discover mid-work. Findings never silently widen the issue, and the
default disposition is **fix**, not file. Noting it in the PR body is not a disposition.

| The finding is… | Do |
|---|---|
| a regression THIS change introduced | **Fix it. Never file it.** The work isn't done, and the completion check re-runs after — even past the round cap |
| small AND pertains to the issue at hand | **Fix it now**, note it in the PR body |
| too big, substantial, or unrelated | **File it — ask first** |

**Asking:** never mid-flight. Collect candidates, ask ONCE at the end, batched — one line each plus
a placement choice. Owner unreachable → file at Back Burner P3 and say so in the ship summary.

**Filed findings default to Back Burner P3.** The test: *does launch break without this?* If no, it's
lower-tier however interesting. Placing one in an active epic or above P3 is the owner's call.

## Priority & Devs

The board is a **scheduler, not a ranked list**. `/pickup`'s resolver (`resolve-next.py`) walks it
mechanically — these are the values it reads, not a procedure to follow by hand.

- **Epic Rank** (numeric, lower first) orders epics **among their siblings**; sparse tens (10, 20, 30)
  so new epics slot between. Unranked = invisible to `/pickup` = a creation defect.
- **Priority** on a child issue is scheduler state: **P0** running/next · **P1** ready · **P2** blocked
  or waiting its epic's turn · **P3** opportunistic, never scheduled.
- **Nine devs** — Makayla, Beau, Amy, Gartay, Nehn, Mien, AJ, Aubrey, Jackson (seniority = fill
  order, not skill). One issue each. The `Dev` field is set at pickup and **never cleared** — it's
  permanent attribution. `DEVS` in `resolve-next.py` is the source of truth; every name must also
  exist as a `Dev` option on each board the resolver serves.
- **Available** = every `Depends-on` shipped + not In Progress + collision-free with in-flight work.
  "Shipped" = merged to staging.
- **Devs must not overlap on files.** Pure simultaneity, never ownership — no one owns a chain across
  time. Collision is checked at dispatch, never stored.
- **The live board is the only dispatch truth.** Never dispatch from a queue table in an epic body.
  In Progress = claimed; route around it.
- **No ownership exceptions.** If work must wait, that's a `Depends-on` edge or a collision — never a
  person.
- **Standing containers** hold epic-less issues: **⚡ Express Lane** (do now) · **Odds & Ends**
  (scheduled) · **Back Burner** (low). Choosing the container IS the priority decision.

**Recalibrate at transitions, not by vigilance:** at ship time (graduate unblocked dependents P2→P1,
advance the epic's order, flag drained epics) and at planning sessions. When a top-level epic closes,
announce the new top-ranked one for confirmation.

## Issue Template

```
Kind: <value>          ← only when Work Type is ambiguous; ALWAYS for Planning
### Problem / Goal     ← 1–3 sentences: what's broken/needed, why it matters
### Acceptance Criteria ← outcome checkboxes; no file paths, no implementation
### User Flow Requirements ← REQ-NNN checkboxes, only when the tier includes it
### Testing Tier
### Context            ← optional: links, reports
### Connections
```

**KIND** — `/pickup` reads it to decide how to run the work. Derives from Work Type where obvious
(Bug → Bug fix; Refactor/Chore/Test → Invisible; Feature → New feature *or* Change to existing).
Write an explicit `Kind:` line when ambiguous, and always for **Planning** (deliverable is a
decision — `/pickup` runs it as a walkthrough, no branch/PR).

## Connections Block

Every issue ends with one. **Declare one direction only** — the inverse is derived by grep, so
nothing is written twice and nothing drifts. Four line types, nothing else:

| Line | Meaning |
|---|---|
| `Parent: #N` | epic membership (mirrors the native sub-issue link) |
| `Depends-on: #N — <reason naming the contract>` | this issue consumes what #N produces |
| `Design: <doc path> (<section>)` | the governing design doc |
| `Group: lead of #A, #B` / `Group: rider of #N` | ships on one branch/PR; **riders never dispatch alone** |

Rules: include a line only when grounded — no grounded lines reads `_(none — standalone)_`, a healthy
state. The reason on `Depends-on` is mandatory. **Dependency = consumption, never proximity** — file
overlap is a dispatch-time collision, not a `Depends-on`; issues that must *ship together* get
`Group:`. `Relates to #N` is prose color with zero cascade duty. Bring an issue's block up to standard
whenever you touch it; never run a board-wide backfill.

**Find downstream consumers of #N:**
```bash
gh issue list --state open --limit 500 --json number,title,body \
  -q '.[] | select(.body | contains("Depends-on: #N")) | "#\(.number) \(.title)"'
```

## Epics

An epic is an issue titled `Epic: …` holding Problem/Goal, a sub-issue checklist (`- [ ] #N — desc`),
and Definition of Done. No acceptance criteria, no testing tier — its children do the work. It needs
an **Epic Rank** at creation or `/pickup` can't see it. Create one when 2+ issues solve the same
problem. Close it when its children are done.

Link children natively (the `Parent:` line mirrors this, it doesn't replace it):
```bash
gh api graphql -f query='mutation { addSubIssue(input: {issueId: "<PARENT_ID>", subIssueId: "<CHILD_ID>"}) { issue { id } } }'
```

## Creating an Issue (Birth Protocol)

`/create-issue` executes this. Every step is mandatory — a skipped one is a defect.

1. **Survey** the open board once before linking.
2. **Set ALL board fields** — Status, Priority, Work Type, Effort, Module. An unstatused item is
   invisible to every filtered view. Priority defaults: prod bug → P1; work inside an active
   initiative → P2; opportunistic → P3. Never P0 at birth.
3. **Link the native parent.**
4. **Place it in the order** — insert its line into the epic's checklist at the right position, or
   slot it into a standing container. Position IS the priority decision; ask if it isn't obvious.
5. **Write the Connections block.** Any relationship stated in an epic body's prose MUST also appear
   as a typed line on the child — the resolver reads only typed lines. An untyped relationship is a
   latent misroute.
6. **Reverse cascade** — if this changes another open issue's assumptions, comment there, dated.

## Branches, Commits, PRs

- Branch `<fix|feat|refactor|chore|test>/<short-name>` off `staging`.
- Commits in imperative mood, referencing the issue: `Fix date picker offset (#12)`.
- PR to `staging` with **`Relates to #N`** — links without closing. Build and tests pass first.
- Batch PR `staging` → `main` with **`Closes #N`** per resolved issue. `Closes` only fires on the
  default branch, which is why staging PRs use `Relates`.

## Status Transitions

| Column | When |
|---|---|
| Backlog | created, not prioritized |
| Todo | ready to pick up |
| In Progress | actively being worked |
| On Staging | merged to staging, awaiting the batch merge |
| Done | merged to main |

## Sizing

One issue = one session (1–3 hrs) = one testable PR. Larger → split and group under an epic.

## Multi-Repo

Parent issue in the primary repo; a sub-issue per repo, each with its own branch and PR.

---

Picking up an issue: **`/pickup`** — the canonical lifecycle (resolver → drift audit → plan → the
Brief, which is the ONE gate → execute → verify → ship). Don't add approval checkpoints.
Creating one: **`/create-issue`**. Both load their own procedure.
