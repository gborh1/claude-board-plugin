---
name: pickup
description: Pick up a GitHub issue and run the full lifecycle — branch through PR — with ONE user gate (the post-plan Brief). Pass an issue number, or nothing (or "next") to let the board's scheduler resolve the target mechanically.
argument-hint: "[issue-number | next]"
---

# /pickup — Issue Lifecycle

## The contract (governs every phase)

**The user decides direction; agents decide construction.** The user is
interrupted in exactly these cases and no others:

1. **The Brief** — once per pickup, after planning. The go/hold gate.
2. **A product fork** — the product could go two valid ways; the user picks.
   Folded into the Brief when planning surfaces it; a fork that emerges
   mid-execution stops work and asks.
3. **A tripwire / FLAG** — the work would change the product's direction.
4. **The filing question** — ONE batched ask per pickup, at the TOP of
   Phase 6 (construction done, verification not yet run — retimed 2026-08-09;
   it used to follow the done-check), and only when something genuinely
   file-able turned up (too big, substantial, or wholly unrelated). Never
   mid-flight, and never for something you should simply fix. A candidate
   that surfaces during verification itself files at Back Burner P3 by
   default and rides in the ship summary — never a second ask. See Phases
   5–6.
5. **The done-check cap** — the 3-round cap was reached and the done-check is
   still not clean. Say so and wait; never ship on an uncleared done-check by
   default (owner ruling 2026-07-29). See Phase 6.

Everything else is delegated or automatic. The ship summary at the end is a
**report, not a gate** — but it is only reached once the done-check is clean
or the owner has explicitly accepted what is outstanding.

**Writing rule for every user-facing message: consequences, never
mechanisms.** Say what changes about the product, never how it's built. No
file paths, function names, or library names in text addressed to the user.
A genuinely technical decision that needs the user is phrased by its product
consequences ("A loads instantly but can be a beat stale; B is always fresh
but slower — recommend A"). Brief ≤ 8 lines; ship summary ≤ 10. Details are
available on request, never volunteered.

**Escalation rule (standing).** Any hard mid-flight decision, any ambiguous
design call, Planning-mode analysis, and the Phase-6 **done-check** are
judgment moments: spawn with `model: "opus"` (Opus 5) at maximum reasoning
effort. Recon, browsing, and mechanical work stay on Sonnet per the global
tiering rules. **Hard questions go UP to a fresh max-effort spawn, not out to
the user.**

**The one exception: the Phase-3 plan runs on `model: "fable"`** (restored
2026-07-26 — see Phase 3). Everything else above stays on Opus 5: those are
refutation/correctness tasks judged against a diff, tests, and evidence, where
Opus 5 is equal to the job at half the price.

Escalate to `model: "fable"` elsewhere only when the call is one of *taste*
rather than correctness — a design/aesthetic judgment, or a product fork where
both directions are genuinely valid — or when the user asks for Fable by name.

**Every spawn in this skill names its model; none inherits (owner ruling
2026-09-05).** A subagent runs on its parent's model unless the spawn says
otherwise, so a pickup dispatched from a Fable orchestrator would otherwise run
its recon, browser walks, reviewer and done-checks on Fable. The table, for the
Agent tool's `model:` argument (aliases only):

| spawn | `model:` |
|---|---|
| Phase-3 plan | `"fable"` |
| done-check, every round; mid-flight escalation; Planning-mode analysis | `"opus"` |
| rules-compliance reviewer (`/code-review`) — pass it on if the skill asks | `"opus"` |
| recon / codebase search / browser and user-flow walks | `"sonnet"` |

The advisor is separate: it is a setting, not a spawn, and stays as configured.

---

## Phase 0 — Resolve the target

`/pickup <N>` → Phase 1. Bare `/pickup` (or `next`) →

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py
```

Use its `NEXT` as the target (it walks Epic Rank → epic-level Depends-on →
pickup order → availability → riders; read-only, live board only — never
dispatch from a queue table in an epic body). Notes:

- All three devs busy → print who's on what and STOP.
- **`⚠ collision flag` on the target is a hard gate.** The flag is a
  grep-level file-overlap hint against in-flight work; verify by reading
  both issues (and the code if they plausibly touch the same component). A
  real collision → append `Depends-on: #<in-progress issue> — <shared
  surface>` to the *candidate* (the one that must wait), then take the next
  candidate. This dispatch-time edge is the backstop for one missed at
  birth; it dissolves when the in-flight issue ships. Same reconcile for any
  prose-only relationship noticed while walking (encode the missing
  `Group:`/`Depends-on:` line as you pass).
- **The resolver skips candidates already in flight off-board** and lists them
  under `CLAIMED OFF-BOARD` — a branch/worktree names the issue, or it carries
  an unreleased `pickup:claim` comment, while the board still says pickable. If
  your surfaced target came at the cost of a skip, the board is stale:
  **reconcile it** (set the skipped issue to In Progress) as you pass, then
  proceed with the surfaced target. `NOTHING AVAILABLE that isn't already in
  flight` → every candidate is off-board-claimed; reconcile the board or wait.
- **One board pull per cycle — live, not cached.** The resolve pulls the board
  LIVE (dispatch must be priority-correct and see just-shipped work; a stale
  board picks the wrong-priority issue). That single pull (~300 GraphQL pts) is
  the whole cycle's board cost — it also **saves every item id** to an id-map
  file and loads issue bodies via REST. The on-disk board copy is an
  **outage-only** fallback: served (loudly) only if a live pull fails, never on
  a healthy one. **Never re-pull the full board later in the cycle.** To get
  another issue's board-item id, use `resolve-next.py --item-id <N>` (zero
  GraphQL, reads the id-map). To learn whether a specific issue changed, read
  THAT issue (`gh issue view <N>`), not the board.
- Resolver errors or the board looks off → fall back to the manual walk in
  `${CLAUDE_PLUGIN_ROOT}/skills/conventions/issue-management.md` → Priority & Devs.
- Nothing available anywhere → print the blocker graph and STOP; that
  report is the deliverable.

## Phase 1 — Claim first, then set up

**Claim BEFORE you read the body, branch, or audit.** The board is the only
dispatch truth, but it isn't true until you write it — every second between the
resolver's read and your claim is a window where a parallel `/pickup` takes the
same issue (the double-pickup race: 2026-07-17 #348, twice). Close the window by
claiming as the very first action; everything else waits behind it.

**⚠ Plan-mode tripwire (added 2026-07-22, after #217 ran unclaimed).** If the
harness has plan mode active, the claim writes (board edits + lock comment) are
BLOCKED — and a pickup must never proceed unclaimed in silence. STOP here,
before any reading/audit/planning, and surface the conflict to the user in one
short message: "plan mode blocks the claim, so #<N> stays open to a parallel
pickup while I plan — lift plan mode so I can claim first, or explicitly accept
the unclaimed-planning risk." Only continue read-only after the user chooses;
never silently defer the claim to post-approval.

1. **Claim (Phase 1.1) — the first action, using the resolver's item id** (do
   NOT re-pull the board):
   - Board → **In Progress**; **Dev** → most senior free dev, in the seniority
     order the resolver prints on its `devs` line (`DEVS` in `resolve-next.py`
     is the source of truth; solo session = the first name in it).
   - Post the **claim comment** — the authoritative lock (board field edits
     carry no visible author/timestamp; a comment does), one human line plus a
     hidden marker the resolver and your verify step read:
     ```
     🔒 Claimed by <Dev> · <worktree-name> · <UTC-timestamp> (pickup)
     <!-- pickup:claim dev=<Dev> wt=<worktree-name> -->
     ```
   - `/pickup <N>` (manual) claims identically. Not on the board → skip the
     field edit but STILL post the claim comment.
   - If you must (re)find the item id:
     `python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --item-id <N>` — zero
     GraphQL, it reads the id-map from the last board pull. Empty → run bare
     `resolve-next.py` once to refresh it.
     **NEVER `gh project item-list`** (~1.2 pts/item — 8 calls drained the whole
     hourly budget on 2026-08-09), and never the repository-GraphQL path
     (`issue.projectItems` returns silently empty when board owner ≠ repo owner).
2. **Verify the claim (optimistic lock) — TWO checks, different remedies.**
   Both races come from the same cause: a parallel `/pickup` read the board
   after you did but before your claim landed.

   **(a) Same-issue race.** Re-read the issue's comments. Another
   `pickup:claim` with an EARLIER timestamp and no later `pickup:release` → you
   lost: **release** (see *Releasing a claim*) and re-run the resolver for the
   next target. (The resolver already skips off-board-claimed candidates, so
   this only fires on true simultaneity.)

   **(b) Same-dev race — check this too; (a) cannot see it.** Every layer of
   the issue lock asks "is this issue taken?", never "is this dev already
   working?", so two *different* issues claimed by the same dev slip through
   all of them. Re-read the In Progress set
   (`python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --list | grep 'In Progress'`).
   If your dev now appears on another In Progress issue whose claim timestamp
   is EARLIER than yours, you double-booked that dev.
   **Remedy — do NOT release.** The work is fine and collision-safety was
   never impaired (the collision check reads each busy dev's current issue,
   which is still visible either way); only the label is wrong. Keep the
   issue, step down to the next free dev in seniority order (the resolver's
   `devs` line), update the board's **Dev** field, and post an amended claim:
   ```
   🔒 Re-claimed by <NewDev> · <worktree> · <UTC-timestamp> (pickup; was <OldDev>, double-booked)
   <!-- pickup:claim dev=<NewDev> wt=<worktree> -->
   ```
   No free dev remains → you genuinely have no capacity: release and stop.
   *(Added 2026-07-27 after #462 and #498 were both claimed as Makayla 94s
   apart. Cost of missing it is not lost work — it is a phantom-busy board that
   makes the next pickup STOP on "all three devs busy" while a dev sits idle.)*
3. `gh issue view <N>` — title, body, labels, acceptance criteria.
4. **Classify KIND** — drives everything downstream:
   - An explicit `Kind:` line in the body wins.
   - Else map the board's Work Type: Bug → **Bug fix** · Refactor / Chore /
     Test → **Invisible** · Feature → **New feature** or **Change to
     existing** (judge from the body).
   - **Planning issue ("let's figure out / decide / spec …") → Planning
     Mode** (last section). No branch, no PR.
5. **Branch** — `<fix|feat|chore|test>/<slug>` off fresh staging
   (`git checkout staging && git pull && git checkout -b …`). If already in
   a worktree: sync it FIRST (`git fetch origin staging && git merge
   --no-edit origin/staging`) and resolve conflicts now — worktrees are
   frequently cut from a stale ref; never skip this.

## Phase 2 — Drift audit + tripwire (silent unless tripped)

**Always runs — recency is no exemption** (owner ruling 2026-07-29): an issue
filed hours ago can be improperly written or void; the audit is what catches a
bad premise, not just a stale one.

Check what moved under the issue since it was written: `git log
--since=<createdAt>` on relevant paths, merged PRs, "(after #X)" caveats now
closed, renamed files/tools/playbooks. Map the cascade both ways: what this
issue depends on (its Connections block + `Design:` doc) and who depends on
it (grep open bodies for `Depends-on: #<N>`).

**Tripwire — the only pre-plan user stop.** Ask FIRST (≤5 lines,
consequences framing) only if the audit predicts a veto: the issue's premise
is stale (what it assumes no longer exists), it was machine-scaffolded and
the ground has shifted, or executing it would reverse a settled decision.
Otherwise say nothing and proceed.

## Phase 3 — Plan (Fable is the planner)

**Right-size first (declared, never asked — owner rule 2026-07-29).** A small
mechanical shape — one-file bug fix, chore, copy change, no design surface —
is planned INLINE by the main agent: no Plan spawn at all. The Brief declares
it (`PLAN inline — <one clause>`); the owner's veto is Hold. Anything with
genuine ambiguity or design surface gets the spawn below.

**The declaration tiers the whole back end (owner ruling 2026-08-09).** `PLAN
inline` is a classification, not just a planning shortcut: an inline-planned
pickup also gets the LIGHT verify path — single-agent code review (Phase 6.3)
and ONE done-check round with no loop (Phase 6.4). The efficiency audit that
produced this rule: a two-line CSS fix (#975) ran the full pipeline — two
review agents, three done-check rounds, ~850K subagent tokens, 2.5 hours — and
every finding after round 1 was in a guard test authored during the pickup, not
in the product change. The heavyweight loop exists for diffs with blast
radius; the Brief already knows which kind this is, so let it say so. If
execution reveals the classification was wrong (the diff grew real surface),
upgrade to the full path and say so in the ship summary — never the reverse.

Otherwise spawn the **Plan agent with `model: "fable"`** (max reasoning; fall back to
`opus` only if Fable errors) carrying: the issue, the drift audit, the cascade
map. **Tell it the handed ground truth is GIVEN, not hypothesis** (owner
ruling 2026-08-09): the drift audit's measurements — schema state, live
behavior, file contents already quoted — are settled; it verifies only what
it newly builds on. #970's planner re-measured nearly everything its prompt
had established and ran seven-plus minutes before returning, twice prodded.
It returns
the implementation plan — approach, files, test plan — plus three things it
must explicitly report: the **blast-radius enumeration** (below), any
**product fork** (two valid product directions), and any **FLAG** condition
(triggers in Phase 4).

> **Why Fable here and nowhere else** (restored 2026-07-26 after 3 days on
> Opus 5). Planning is the one step whose job is navigating ambiguity and
> deciding next steps — Fable's documented edge — and it is the highest-leverage
> spawn in the pickup: a weak plan makes every later phase busy but incoherent.
> It is also cheap to buy, being one spawn against a session of hundreds of
> messages. Measured from actual usage, Fable ran 11–16% of tokens / 20–27% of
> blended spend when it held *five* roles; as planner alone expect ~10–15%.
> **Revert trigger:** if rework doesn't visibly drop over ~10 pickups, the
> cause was the problem domain, not the model — put Phase 3 back on `opus`.

### The blast-radius enumeration (required section, usually empty)

**Trigger — ask once:** does this change introduce, alter, or retire a *state,
field, value, or record class that more than one place reads*? Adding a status
value, a column, a lifecycle state, a taxonomy member, a verdict enum, a shared
predicate — all yes. A one-file bug fix, a copy change, a self-contained
component — no, and the section is one line: `_(none — nothing shared changes)_`.
Most pickups land there and pay nothing.

**When it triggers, enumerate EXHAUSTIVELY and mechanically, never from memory:**
grep every read of the field/state, every rule keyed on the old values, and every
explicit column list, SQL projection, view, RPC, prompt, and skill template that
carries it. Give each site a verdict — *changes / already correct / deliberately
unchanged, because …*. A site nobody can account for is a plan defect, not a
detail.

**Why this is a plan output and not a review finding:** it is a *coverage*
question, and adversarial review samples rather than covers — N reviewers walk N
paths and each finds a different subset, which converges slowly and expensively.
(#488, 2026-07-26: five done-check rounds, and six of seven findings were the same
shape — "another rule that assumed the old state model." One was mechanically
derivable in thirty seconds by anyone who thought to look.) Enumeration is
exhaustive by construction, costs one pass, and *shapes* the diff instead of
auditing it afterward. It also gives Phase 6 something to verify against rather
than rediscover.

**The three shapes that hide best**, worth naming in the sweep: a rule keyed on a
state the new class never reaches (`WHERE status = 'Open'` when the new class is
never Open); a field specified at both ends of a pipeline and dropped in the
middle; and one write silently undone by another (a nightly job, a trigger, a
sweep).

### The vendor-claims enumeration (required when the pickup wires a dependency)

**Trigger:** the change introduces or reconfigures a third-party library whose
runtime behavior it depends on — an SDK, a client, a build wrapper. Most
pickups don't, and pay nothing.

**When it triggers, enumerate every behavioral claim the change makes about the
dependency** — each "the library does X" in a comment, each config value chosen
for what it supposedly controls — and verify each against the INSTALLED
package: read its source in node_modules, or run a throwaway probe. Settle the
list at plan time or first verify. **Adversarial rounds must never be the
discovery mechanism for this class** — they sample it one gap at a time.

**Why (2026-08-09, #1015):** five of nine done-check gaps across three rounds
were one class — a claim about SDK behavior the SDK did not implement. The
worst ("this flag keeps cookies out of events") shipped the signed-in user's
whole session cookie to the tracker, and no diff reviewer could catch it,
because the defect wasn't in the diff — it was in the gap between the diff's
assumptions and node_modules. A nine-claim probe script cost ~nothing and
terminated a loop that had already spent ~600K tokens sampling toward it. The
blast-radius enumeration covers OUR state; this one covers THEIRS.

Main agent sanity pass, no spawn: does the plan actually solve the issue? Is the
enumeration genuinely exhaustive, or a plausible-looking sample? fork? flag?
Route the answers into the Brief.

## Phase 4 — THE BRIEF (the one gate)

Print exactly this shape, then AskUserQuestion (options: **Go** / **Hold**,
plus the fork options when one exists):

```
#<N> — <short handle>

KIND      Bug fix | New feature | Change to existing | Invisible
PROBLEM   <1–2 sentences, user's side of the screen>
AFTER     <what the app does once this ships that it doesn't today;
           Invisible: "nothing visible changes — <one clause why it matters>">
FLAG      none | ⚠ <one sentence: which direction changes and why>
PLAN      <only when inline: "inline — <one clause why no spawn>">
FORK      <only if one exists: A vs B in consequences + recommendation>
```

**FLAG triggers — flag on these, nothing else:** reverses a settled/ratified
decision · changes a core pattern (data model, a signature surface, the
voice, pricing/credits) · hard to undo (destructive migration, data
deletion, external publish) · stale or machine-scaffolded premise (from
Phase 2) · true scope ≫ what the issue implies.

**Stop and wait.** Go → Phase 5. **Hold → release the claim** (see *Releasing a
claim*) and stop — a held pickup must not leave the issue locked. This is the
only checkpoint in a normal pickup — do not add others.

## Phase 5 — Execute

Implement the plan; write tests per testing-standards.

- **Test cadence (owner rule 2026-07-29): targeted tests only while iterating** —
  the tests mapping to the changed surface; prompt/skill/docs edits run zero
  code tests. The FULL suite runs exactly once, in Phase 6. See
  `${CLAUDE_PLUGIN_ROOT}/skills/conventions/testing-standards.md` → Cadence.

- **Hard decision mid-flight** → escalate per the contract above, not to
  the user.
- **Product fork mid-flight** → stop, ask the user, consequences framing.
- **Emergent problems — bias hard toward FIXING.** Full rule in
  `${CLAUDE_PLUGIN_ROOT}/skills/conventions/issue-management.md` → *Findings: fix or file*.
  **Dedup FIRST, before fixing or filing anything (owner ruling 2026-08-09):**
  one grep over the resolver's cached issue bodies
  (`~/.cache/claude-pickup/bodies-*.json`) for the finding's keywords,
  and `git log origin/staging --since=<claim time> -- <file>` on the touched
  surface. Seconds, and it catches the two parallel-session collisions that
  cost real work on 2026-08-09: a fix already merged to staging by another
  session (#1177 — this session fixed it again, then unwound it at merge), and
  an issue already filed hours earlier (#1181 — this session filed #1184, a
  duplicate, then paid the Birth Protocol AND the close-out). A hit on the
  fix → sync staging instead of fixing; a hit on the filing → comment anything
  new onto the existing issue instead of filing.
  **The same collision runs the other way (owner ruling 2026-08-09): a find
  that blocks EVERY session — a broken dev server, broken shared tooling — is
  an outage, not a finding.** File it to ⚡ Express Lane the moment you find
  it (the one exception to never-file-mid-flight), note you are fixing it in
  your PR, and close it when that merges. The filing is what the next
  session's dedup grep hits. #970 and #1177 each fixed the same all-worktrees
  dev-server break without knowing the other had it — the collision cost a
  merge conflict and a full extra CI cycle, and announcing it was free.
  In short:
  - **A regression this change introduced** → fix it, never file it, and
    always re-run the done-check afterwards (exempt from the Phase-6 cap —
    the cap is for polish churn, never for a regression).
  - **Small AND pertains to the issue at hand** → fix it now, even when the
    code lives outside what this change already touches, and note it in the
    PR body so it ships with this PR. If we'd want it finished soon, finish
    it now. Noting alone is never a disposition.
  - **Too big, substantial, or wholly unrelated** → it is file-able. **Do
    NOT file it mid-flight and do NOT decide its placement.** Add it to a
    filing-candidates list and keep working; ask once at Phase-6 entry (below).
- **The filing question (ONE batched ask, at the TOP of Phase 6 — retimed
  2026-08-09; it used to follow the done-check).** For each candidate give a
  one-line description and let the user choose: fold in now · file at
  priority · file to Back Burner. Then act on the answer, filing per the
  Birth Protocol (all board fields, parent, Connections). **Why the retiming:
  asked after the done-check, "fold in now" reopens execution at the one
  moment nothing re-verifies it.** #970's two ship-time fold-ins forced a
  fourth adversarial round (~163K tokens plus a full re-gate), and one of
  them introduced the bug that round caught. Asked before verification, a
  fold-in rides the same review, done-check and full-suite pass as the rest
  of the diff — the work costs the same; the verification comes free.
  **User unreachable / autonomous run** → file at Back Burner P3 and say so
  plainly in the ship summary. Never ask mid-flight — collect, then ask once.
- **Product fork mid-flight** → still stops work and asks (above); a filing
  candidate never does.

## Phase 6 — Verify (no gate)

0. **The filing question, if candidates accumulated** (contract item 4; the
   full rule lives in Phase 5). Ask NOW, before any verification runs, so a
   chosen fold-in is verified by the same review, done-check and full-suite
   pass as everything else. A candidate that surfaces BELOW — a review or
   done-check finding dispositioned as too big / substantial / unrelated —
   files at Back Burner P3 by default and is listed in the ship summary; it
   never buys a second ask, and never a fold-in (a fold-in this late is the
   reopen-after-verification trap the retiming closed).

1. Migrations per `${CLAUDE_PLUGIN_ROOT}/skills/conventions/supabase-migrations.md` (repair worktree
   ledger → `supabase migration up`). Then build, lint, and the FULL test
   suite — its one run per pickup (Cadence rule) — green, or fix until green
   (after 2 failed fix attempts: stop and ask). Fixes here re-run targeted
   tests; the full suite re-runs once more only after the last fix.
   **The cadence rule covers mutation testing too (owner ruling 2026-08-09):**
   when a guard is verified by mutating the code it protects, re-run only the
   mutation cases touching what changed while iterating; the FULL matrix runs
   once, at the end. #975 re-ran an 11–17 case matrix (a full vitest boot per
   case) after every guard edit — ~50 runs where ~20 were needed.
2. Browser-verify the change, scoped to the affected flow — not a general
   sweep (REQ checkboxes if the issue has them — every REQ, no skipping; else
   the golden path + obvious edges). The only valid skip is "no
   browser-observable surface: <reason>" — carried into the ship summary.
   **Verification scaffolding is built ONCE and torn down at ship
   (2026-08-09):** when proving a behavior needs a rig — a stub ingest server,
   a probe route, seeded state — stand it up in the scratchpad on first need
   and keep it through every later round; dismantle it in the final pass and
   prove the tree clean. #1015 built and tore down the same stub-collector rig
   four times (~20 min of dev-server cycles) for what became the session's best
   evidence — its two worst defects were visible only on the wire, in no test.
3. `/code-review` — at the tier the Brief declared (owner ruling 2026-08-09):
   an inline-planned pickup gets the skill's small-diff mode (one reviewer,
   both mandates). **A spawn-planned pickup runs ONE rules-compliance
   reviewer here; its bug-hunting mandate moves into the done-check's first
   round** (item 4 — second owner ruling, same date). The two agents were
   walking the same diff: on #970 the bug reviewer and done-check round 1
   independently found the same defect class, ~180K tokens of duplicated
   hunting, while the rules reviewer's findings (lockstep floors, PR-body
   duties, migration hygiene) overlapped with nothing. One lens each.
   **Fix every confirmed finding automatically — no approval
   sought.** Re-run targeted tests after fixes.
   **The done-check's disposition rule (item 4) applies here too:** fix
   regressions, AC breaks, breakage, and anything small that pertains to the
   issue at hand (noting it in the PR body); only what is too big, substantial
   or wholly unrelated becomes a late filing candidate (default-filed, per
   step 0).
4. **Done-check (adversarial completion recheck) — after review findings are
   fixed, before `/commit`.** Spawn a fresh agent per the escalation rule
   (`model: "opus"`, Opus 5 at max reasoning) charged to **refute the
   claim that this issue is done**. It exists to catch the class of error a
   diff review cannot: ACs satisfied in letter but not spirit, verification
   that exercises something *adjacent* to the claimed fix rather than the fix
   itself, evidence that proves a different proposition than the one asserted.
   (Owner-sanctioned 2026-07-18; made **permanent** 2026-07-24. It began as a
   stand-in for the harness advisor's pre-completion recheck while that was
   broken for Fable — the owner has since kept it on its own merits, so it
   does NOT retire now that the advisor works on Opus. The two are
   complementary: the advisor inherits the transcript and its blind spots,
   this spawn is fed raw artifacts and is charged to refute.)
   - **Tier by the Brief (owner ruling 2026-08-09): an inline-planned pickup
     gets ONE round, no loop.** Its findings are dispositioned by the bar below
     exactly as usual — fixed, carried, or filed — but nothing re-runs the
     check except a regression (which always does, any tier). The loop below is
     for spawn-planned work with real blast radius. Rationale: on a small diff
     a fresh max-effort adversary always finds *something*, and each fix adds
     surface for the next round to mine — #975's rounds 2–3 audited a test
     file, not the product, at ~180K tokens a round.
   - **Round 1 carries the bug-scan mandate too (owner ruling 2026-08-09).**
     For spawn-planned work, this first round is ALSO the diff-level bug hunt
     that `/code-review` no longer runs (item 3): charge the one adversary
     with both lenses — refute the ACs, and hunt the diff for defects
     reachable without them. It was already doing the second job by accident;
     now it does it on purpose, and nobody pays twice.
   - **Feed round 1 raw artifacts, never your narrative** — your summary
     inherits your blind spots. Include verbatim: the issue body + ACs, the
     Brief as printed, the plan, the full diff, the actual verification
     evidence (test output, run/reconciliation data, browser findings), and a
     plain list of assumptions or plan-deviations made mid-flight.
   - **Hard constraints in every done-check spawn prompt (owner ruling
     2026-08-09, learned the expensive way):** (a) **no broad process kills** —
     never `pkill`/`killall` by pattern; stop only exact PIDs you started
     (#975's round-1 agent `pkill -f "next dev"`-ed an UNRELATED project's dev
     server); (b) restore any file you mutate byte-for-byte and prove it
     (checksum, `git status`) before finishing; (c) never pipe test output
     through a filter that can drop a failing test's name.
   - **What it must return, IN THIS ORDER (owner rule 2026-08-01).** Per gap:
     **(1) the gap** — the verdict rests on this alone; **(2) the class it
     belongs to, and every other place that class appears** — enumerated, not
     sampled; **(3) a proposed remedy pitched at the class, not the instance.**
     The order is load-bearing: a finding formed while reaching for its fix
     drifts toward gaps that are easy to fix, and the ones worth catching are
     exactly the ones that are not. **"No remedy known" is a legal answer** —
     say it rather than invent a plan. The remedy is a PROPOSAL you judge, not
     an instruction you follow; a confident wrong plan obeyed deferentially is
     harder to catch than an improvised bad fix, because it reads as
     compliance. **The judgment cuts both ways (2026-08-09): when rounds fault
     the same hand-rolled mechanism twice — a parser, a matcher, a traversal —
     stop patching instances and take the structural remedy**, the adversary's
     or a simpler one of your own. #1015 patched one URL-matching regex four
     times, each patch buying its own edge-case bug; the rewrite proposed in
     the final round was simpler than the sum of the patches.
     *(Why (2) exists: #488 ran five rounds in which six of seven findings were
     the same shape. Each round's instance got fixed and the class did not, so
     the next round found the next instance. Enumerating the class turns five
     rounds into one — the same logic as the Phase-3 enumeration sweep, applied
     at verify time when plan time missed it.)*
   - **What to do with each gap — bias hard toward FIXING (owner rule, revised
     2026-07-28).** The disposition rule is the one in
     `${CLAUDE_PLUGIN_ROOT}/skills/conventions/issue-management.md`; this bar only decides **what re-runs
     the loop**, which is a different question from what gets fixed.
     **Dedup each gap before fixing it — Phase 5's rule applies here
     identically (extended 2026-08-09).** One grep over the cached issue bodies
     plus `git log origin/staging --since=<claim time>` on the gap's surface —
     seconds. #1015's round-4 gap had been fixed on staging two hours earlier,
     better, by a different route — and the duplicate fix cost a merge conflict
     plus an audit of the hand-resolved result. A hit → sync staging and
     confirm the end state instead of writing a second fix.
     - **A regression this change introduced** → fix it, and the done-check
       **always** re-runs. **Exempt from the cap below** — if the cap is reached
       with a regression outstanding, say so and ask; the owner extends it.
       ("I removed a safety net that used to exist" is a regression even when it
       violates no stated AC and breaks nothing yet — #547, 2026-07-28.)
     - **Violates an AC, or is breaking** (data loss/corruption, a destroyed or
       unreachable record, something that stops shipping) → fix it; re-run.
     - **Small and pertains to the issue at hand** → **fix it** (not file it),
       even when the code sits outside this change, and note it in the PR body.
       Re-run only if the fix could plausibly open a new gap; a change fully
       covered by the build/tests/browser pass you re-run anyway does not buy a
       round.
     - **Too big, substantial, or wholly unrelated** → late filing candidate:
       the batched ask already ran at step 0, so it default-files at Back
       Burner P3 in Phase 7 and is listed in the ship summary. Do not fix it,
       and never offer it as a fold-in. Buys no round.
     - **A gap in a test or guard AUTHORED IN THIS PICKUP → fix or narrow, buys
       no round (owner ruling 2026-08-09).** The product change and its
       verification artifacts are not the same deliverable. When the adversary
       faults a guard you wrote an hour ago — a coverage hole, an overclaiming
       header, a false red — fix it or **narrow the guard's claims to what it
       actually checks** (deleting an overclaiming sentence is one line and
       always available), then proceed; do not spawn a fresh round to re-refute
       it. Re-refutation is an arms race: each fix adds code, code adds claim
       surface, and a fresh reader will always find the next hole. #975 ran
       rounds 2 and 3 (~365K tokens) entirely on its own guard while the
       product fix stood faulted by nobody after round 1. Sizing corollary:
       **a guard longer than the diff it protects is the wrong guard** — state
       a smaller invariant instead of building an analyzer (#975's grew to
       ~690 lines, with a CSS parser and an AST walker, protecting 3
       declarations).
     **What this bar is really for.** The failure it prevents is *fix → break →
     fix → break*: an unstable change where each fix opens a new gap. It is NOT
     "avoid fixing things." A fresh adversarial reader will always find
     something, so the loop must not terminate on the reviewer running out of
     observations — but it terminates on the work being *correct*, and a
     regression left unfixed is not correct. The six-round #512 run (2026-07-27)
     was the anomaly it was written against: round after round of small
     **unrelated** findings. Those are now filing candidates, which buy no round,
     so that specific pathology is closed without also forbidding fixes.
   - **Verdict:** `done` → Phase 7. `not-done` → apply the bar above: fix what
     the bar says to fix and re-verify (targeted tests/browser); late filing
     candidates default-file in Phase 7. **A round whose findings are ALL
     filing candidates is a `done`** — carry them and proceed. A gap
     genuinely unresolvable in this pickup rides in the ship summary. The
     done-check is never itself a user gate.
   - **Loop until clean (added 2026-07-23).** A round that fixed a gap the bar
     says re-runs does NOT proceed — the done-check re-runs. Spawn a **fresh**
     agent (same escalation rule; fresh so it can't rationalize the prior
     verdict). **Rounds 2+ are delta-scoped (owner ruling 2026-08-09):** feed
     the prior round's gap list, what was done about each, the FIX DELTA (the
     diff since that round), and the issue + ACs for orientation — never the
     full re-shipped artifact bundle. The bundle grows every round while the
     round's real question shrinks to "did these gaps close, and did the
     fixes open new ones"; on #970 the one delta-scoped round cost ~20% less
     than its full-bundle siblings and still caught a real bug, so the fresh
     eyes survive the smaller feed. Charge it to confirm each gap is actually
     closed AND that the fixes opened no new gap. Repeat until a round
     returns `done` or finds only filing candidates. Carried candidates
     and stated-unresolvable gaps never block convergence.
     **A round that changed nothing does not re-run** — carrying a candidate is
     not a change, so the verdict still stands.
   - **Repeated gap CLASS → stop sampling and enumerate. This is a
     PRECONDITION, not advice (hardened 2026-08-09).** If a round finds a gap
     of the same *shape* as the previous round's ("another site that assumed the
     old state model", "another projection that drops the field"), do not just
     spawn another reviewer — that is sampling an unenumerated set, and each
     fresh reader walks a different path. Run the missing Phase-3 enumeration
     now — blast-radius for shared repo state, vendor-claims for dependency
     behavior (#1015's repeated class was the second) — mechanically and
     exhaustively, and verify against its list.
     Two rounds finding the same class is the signal the plan's enumeration was
     missing or incomplete. **Round 3 may not be spawned until the repeated
     class has been enumerated and the fixes verified against that list** — on
     #975 the enumeration (11 routes, each with its live population) is what
     actually terminated the loop, and it happened in round 3 when the
     two-rounds signal had already fired after round 2. Enumerating first
     makes the next round a *confirmation* pass over a closed list rather than
     another sample; often it makes the round unnecessary.
     **Cap: 3 FIX rounds** (a round that only carried filing candidates doesn't
     count — it changed nothing).
     **At the cap, STOP AND FLAG. Never default to shipping** (owner ruling
     2026-07-29, superseding the earlier "report and default to shipping"). If
     the done-check has not returned a clean `done` by the cap, say so plainly —
     "hit the 3-round cap with the done-check still not clean" — list what is
     outstanding, and **wait for the owner's call**. Shipping on an uncleared
     done-check is the owner's decision to make, not a default to fall back on:
     the whole point of the check is that the work is not known-correct yet, and
     silently proceeding converts "unverified" into "shipped" without anyone
     choosing it.
     Keep the ask CLOSED, not open — state the outstanding items and recommend
     one of ship / keep going, rather than an unbounded "shall I continue?".
     That open form is how this ran to SIX rounds on #512 (2026-07-27), the last
     two ~⅔ polish. If the owner lifts the cap, that is still not unbounded:
     **after two further rounds, report what they bought and re-ask.**
     **The cap NEVER applies to a regression this change introduced.** Fixing
     one always re-runs the check, cap or no cap; at the cap with a regression
     outstanding, say so and ask — the owner extends it (owner ruling
     2026-07-28: "always do it"). The cap governs polish churn, never
     correctness of our own work.
     Report rounds in the ship summary (`done-check ✓ (round 2)`).
   - **Skip rule:** docs-only or otherwise trivial diffs skip it — state the
     skip and reason in the ship summary, same spirit as the browser-verify
     skip.
   - **Any safety-net bypass beyond a standing skip rule needs the owner's
     explicit yes** (owner rule 2026-07-29): skipping the done-check outside
     docs-only/trivial, or browser verification on an issue that carries REQs.
     Foreseeable at plan time → fold the ask into the Brief; it is never a
     separate mid-flight stop and never a silent default.

## Phase 7 — Ship (report, not gate)

1. Commit via `/commit`; PR to staging with `Relates to #<N>`.
2. Board: On Staging (reuse the target's item id). **Dev stays** — permanent
   attribution. Check off satisfied ACs in the issue body.
3. Cascade: dated comment on each affected issue from the Phase-2/3 map;
   graduate dependents whose blockers all shipped (P2 → P1); check off this
   issue in its epic's order. **Reuse ids, don't re-pull:** a dependent's
   board-item id comes from `resolve-next.py --item-id <N>` (zero GraphQL) —
   never a full board re-pull to recover one id. Comments and checklist edits
   are REST. Epic drained → announce the new top-ranked epic in the ship
   summary and ask the user to confirm it as the next target (rides in the
   summary, not a separate stop).
4. **Late filing candidates** — anything Phase 6's review or done-check
   dispositioned as too big / substantial / unrelated files at **Back Burner
   P3** now, per the Birth Protocol, and is listed in the summary. **No ask
   here** (retimed 2026-08-09): the one batched question already ran at the
   top of Phase 6, and a fold-in chosen after verification would reopen
   execution at the exact moment nothing re-verifies it — the trap that cost
   #970 a fourth adversarial round. The owner re-places a default-filed issue
   from the summary in one line if they disagree; that costs a board edit,
   where the old order cost a verification cycle.

5. **Ship summary — ≤10 lines, plain English, past tense:**

```
#<N> shipped → <PR url>
<one sentence: the problem → what the app now does>
verified   build ✓ · tests ✓ · browser ✓ <or the stated skip>
review     <n> findings, all fixed <or "1 carried → asked below">
done-check ✓ (round <r>) <or "n gaps found, fixed (round <r>)" / "1 unresolved: <clause>" / stated skip>
also fixed <one clause each: found along the way, fixed in this PR> (omit if none)
filed      #A <one clause why> · #B <why>        (omit if none; placement per your
                                                    Phase-6 answer — Back Burner for
                                                    late finds, re-place in one line
                                                    if you disagree)
next up    #<M> — <handle>                        (advisory — from THIS cycle's
                                                    Phase-0 queue; do NOT re-pull
                                                    the board to compute it — the
                                                    next fresh /pickup resolves live)
```

## Releasing a claim (a pickup that stops before shipping)

A claim is a lock; a lock you don't ship you must release, or it silently blocks
the next resolver run. **Release when:** the Brief is answered **Hold**, a
tripwire aborts, you lost the optimistic-lock race, or you abandon the issue for
any reason before a PR exists.

Release =
- Board → its prior pickable status (**Todo**, or Backlog if it came from
  Backlog). If **nothing was built** (no branch, no commits), also **clear Dev**
  — there is no work to attribute, and a lingering Dev reads as a live claim. If
  partial work exists, leave Dev and say so in the release comment.
- Post the **release comment**:
  ```
  🔓 Released — <UTC-timestamp> · <reason>
  <!-- pickup:release -->
  ```

A pickup that **ships** never releases — the claim converts to permanent
attribution (Dev stays, per Phase 7).

## Planning Mode (KIND = Planning)

The deliverable is a **decision**, not code. Claim first exactly as Phase 1.1
(In Progress + Dev + the `pickup:claim` comment); no branch, no PR, no build
gates. If you exit without spawning execution issues or amending the issue,
release the claim per *Releasing a claim*.

1. Delegate the analysis per the escalation rule (Opus 5, max reasoning):
   landscape, options, consequences, a recommendation — product altitude
   throughout. If the decision turns on taste rather than correctness, that
   is the Fable case.
2. Walk it through with the user. This mode is a conversation: short turns,
   consequences only, weeds on request.
3. Exit one of three ways (the user picks):
   - **Execute now** — it turned out small; reclassify KIND and continue as
     a normal pickup from Phase 1 step 3.
   - **Plan into the issue** — write the decided plan into the issue body
     (it becomes the governing doc); return it to Todo, re-scoped.
   - **Spawn execution issues** — file them per the Birth Protocol
     (parented, ordered, connected); close the planning issue with a
     comment recording the decision.
4. Close with a 5-line summary: what was decided, what was filed or
   amended, what's next.

## Errors

Issue doesn't exist → stop and report. Staging conflicts → resolve at
setup; ask only if genuinely ambiguous. Build/tests red after 2 fix
attempts → stop, ask, consequences framing. Already In Progress under another
dev, OR carrying an unreleased `pickup:claim` from another session, OR a branch
/ worktree already names it → it is claimed; route around it (bare `/pickup`
re-resolves and skips off-board claims). Not on the board → warn and skip board
steps (still post the claim comment — it is the lock).
