# Ready-Queue Dispatch — resolver re-architecture spec

> **⚠ SPEC ONLY — do not run the commands in this file.** Its cost premise was
> superseded 2026-07-26: `load_board()` now hand-pages the ProjectV2 query 100
> items at a time for **~7 points total**, which already beats this document's
> ~102-pt target by 15×. Every `gh project item-list` below is illustrative of
> the *old* model. To read the board, run `resolve-next.py --list`. The
> queue-shape ideas (Todo = ready, Backlog = reservoir) may still be worth
> adopting; the query mechanism is obsolete.

Goal: cut the GraphQL cost of "what's next" from a full board pull to a single
one-page filtered pull, keeping the board **live** (no cache). Measured against
the real board 2026-07-21.

## Measured cost model (live)
- ~100 GraphQL points per 100-item page; ~100-pt floor per query.
- Full board (~500 items): **506 pts**
- `-status:Done` (all open, 193 items, 2 pp): **203 pts**
- `status:Todo,"In Progress"` (37 items, 1 pp): **~102 pts**  ← target
- `parent-issue:#<epic> -status:Done` (45 items, 1 pp): 102 pts

## The design
- **Todo = the live ready-queue.** Bounded to a "healthy amount" (~2–3× dev
  count ≈ 6–10). Every Todo item is deps-clear (see promotion) and in priority
  order.
- **Backlog = reservoir.** Never pulled at dispatch.
- **On-Staging / Done = shipped.** Never pulled at dispatch (shipped is
  established at promotion, not re-derived here).

### Dispatch read (per pickup) — one live query, ~102 pts
`gh project item-list 1 --owner gborh1 --query 'status:Todo,"In Progress"' --format json`
Carries: candidates (with `module`, `priority`), busy devs (`dev` on In-Progress),
and item ids (for the id-map). Pick highest-priority Todo that is collision-free
with the live In-Progress modules. No dep re-check (Todo is ready by construction).

### Writes — already optimal, unchanged
id-map reuse (`write_idmap`/`--item-id`) → claim + ship mutate by cached id,
zero re-pull. Bodies via REST, off GraphQL.

## The two gaps and their fixes
1. **Epic rank not in a Todo pull.** Fix: mirror rank into each epic body as
   `Epic-Rank: N`; resolver reads rank from the REST bodies it already loads.
   One-time migration of the ranked epics. (Without this, you need a 2nd
   `label:epic` query and the cost is ~204 = no better than `-status:Done`.)
2. **Dep-shipped needs On-Staging.** Fix: **promotion owns the dep-check.** An
   item becomes Todo only when all its `Depends-on` are shipped. Dispatch then
   trusts Todo = ready. Dep-graph work happens at ship time for the specific
   dependents of what just shipped.

## Changes required
1. **Migration (one-time, REST, reversible):** write `Epic-Rank: <n>` into each
   ranked epic body. Ranks already captured from the last board pull.
2. **Resolver (`resolve-next.py`):**
   - `load_board()` → `--query 'status:Todo,"In Progress"'`.
   - Read `rank` from `Epic-Rank:` body line instead of the board field.
   - `available()` drops the dep-check (Todo is ready by construction); keeps
     the live collision check against In-Progress modules.
   - `--board`/`--list` (the /board view) still needs the full picture → keep a
     separate `-status:Done` path for display only (203 pts), not on the
     dispatch hot path.
3. **Pickup skill Phase 7 (ship):** add **promotion** — after graduating
   dependents, promote the next dep-clear Backlog item(s) (in epic-body
   checklist order) into Todo to refill the queue to its healthy size.
4. **Bound Todo** to ~6–10 (curate current 37 down over time; not blocking).

## Test plan (before swap)
- Build resolver as a side file; run read-only against the live board.
- Assert: dispatch target + free-dev + collision decisions are **identical** to
  the current full-pull resolver, at ~102 vs ~506 pts (measure both).
- Verify epic walk order matches after rank→body migration.

## Swap + rollback
- Migrate ranks → verify /board still renders identically (current resolver
  ignores the new body line) → swap resolver atomically → keep old file as
  `.bak` for instant rollback.
- Risk: global file used by live parallel sessions. Do the swap when no session
  is mid-resolve, or accept that the next resolve in each session picks up the
  new logic (which is why it must be tested identical first).
