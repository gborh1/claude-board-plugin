---
name: create-issue
description: Create a GitHub issue that is born connected — surveyed against the whole board, fully fielded, parented, and carrying a grounded Connections block. Use whenever the user asks to create/file/log an issue, or when a workflow needs to file a follow-up.
---

# /create-issue — Birth Protocol Executor

Create a GitHub issue for: $ARGUMENTS

Issues are born connected — never in a vacuum. This skill executes the Birth Protocol from `${CLAUDE_PLUGIN_ROOT}/skills/conventions/issue-management.md` end to end. An issue that skips any step below is a defect (unstatused items are invisible to filtered views; unparented items break swimlanes; blockless items are invisible to cascade maps).

---

## Step 1: Understand the ask (WHAT/WHY, never HOW)

Distill the request into: what is broken or missing, and why it matters. If the request is too vague to write outcome-based acceptance criteria, ask the user before proceeding. Do NOT include implementation approach, file paths, or code — that happens at pickup time in plan mode.

**Classify KIND at birth** — `/pickup`'s Brief reads this instead of guessing:

| KIND | Meaning |
|---|---|
| **Bug fix** | Something built is broken |
| **New feature** | The app gains something it doesn't have |
| **Change to existing** | An existing feature behaves differently after |
| **Invisible** | Internal — nothing visible changes (refactor, tests, tooling, metering) |
| **Planning** | The deliverable is a decision, not code ("figure out / decide / spec X") — `/pickup` runs it as a walkthrough, no branch/PR |

KIND usually follows from Work Type (Bug → Bug fix; Refactor/Chore/Test → Invisible; Feature → New or Change). Write an explicit `Kind:` line (Step 3) whenever the mapping is ambiguous or the issue is **Planning** — Planning has no Work Type of its own and MUST carry the line.

## Step 2: Survey the board (the whole-project view)

Pull the open board ONCE and hold it for all later steps:

```bash
gh issue list --state open --limit 500 --json number,title,body > /tmp/board-survey.json
```

From it, determine:

1. **Duplicate check** — does an open issue already cover this? If yes, STOP and report it to the user (offer to comment on the existing issue instead).
2. **Owning epic/cluster** — which epic (`Epic:` prefix or sub-issue parent) owns this area? If this is the start of a new 2+ issue cluster, propose creating an epic per the epic rules.
3. **Governing design doc** — is there a `docs/...` design doc that settles this area (check the epic's `Design:` line and sibling issues' Connections)?
4. **Dependencies** — which open issues produce something this one will consume? (Grounded only — name the contract.) **Dependency = consumption, never proximity:** touching the same file as another open issue is NOT a dependency — file overlap is a *simultaneity* problem handled at dispatch (the resolver flags it; a transient edge is written only while the other issue is in flight). Writing permanent `Depends-on` edges for file overlap serializes epics artificially and starves parallel pickup. If two same-file issues are so entangled they should ship together, that's a `Group:` (lead/rider — one dev, one PR), not a dependency.
5. **Reverse cascade** — does this new issue change the assumptions of any existing open issue (takes over work another body still claims, inserts into a sequence, supersedes scope)? Note each for Step 6.

## Step 3: Compose the body (template + Connections)

Per the issue template in `${CLAUDE_PLUGIN_ROOT}/skills/conventions/issue-management.md`:

- **`Kind: <Bug fix | New feature | Change to existing | Invisible | Planning>`** — one line at the top of the body, whenever Step 1 said it's needed (ambiguous mapping, or Planning — always)
- **### Problem / Goal** — 1-3 sentences
- **### Acceptance Criteria** — outcome-based checkboxes; no file paths, no implementation. For **Planning** issues, the criteria describe the decision to be made, not code outcomes
- **### User Flow Requirements** — REQ-NNN checkboxes, ONLY if the feature has testable UI behavior
- **### Testing Tier** — per the change type
- **### Context** — links, reports, prose color (`Relates to #N` allowed here, carries no cascade duty)
- **### Connections** — per the Connections Block spec:
  - `Parent: #N` — the owning epic (mirrors the native link made in Step 5)
  - `Depends-on: #N — <reason naming the consumed contract>` — grounded only; reason mandatory
  - `Design: <doc path> (<section>)` — explicit paths only
  - `Group: lead of #A / rider of #N` — only if the user set a group pickup
  - No grounded lines → `_(none — standalone)_`

**Checkpoint:** show the user the draft title + body + proposed board fields (one message), and proceed on their confirmation. Skip this checkpoint only if the user explicitly asked for no-confirm creation.

## Step 4: Create and board it

```bash
gh issue create --title "<title>" --body-file <draft>       # → issue URL/number
gh project item-add <PROJECT_NUMBER> --owner <OWNER> --url <issue-url> --format json -q .id   # → ITEM_ID
```

(Project number/owner: see the repo's CLAUDE.md. Meridian-ESG: project 2, owner gborh1.)

Set **ALL FIVE** board fields — never leave an item unstatused:

- **Status** — Backlog (new) or Todo (prioritized)
- **Priority** — P0/P1/P2/P3
- **Work Type** — Bug / Feature / Refactor / Chore / Test
- **Effort** — Small / Medium / Large
- **Module** — per the repo's issue-management.md

Field + option IDs via `gh project field-list <N> --owner <OWNER> --format json`; set each with the `updateProjectV2ItemFieldValue` GraphQL mutation.

**Never run `gh project item-list` here.** Step 4's `item-add … -q .id` already
handed you the `ITEM_ID`; if you lost it, `python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --item-id <N>`
costs nothing. `item-list` costs ~1.2 GraphQL pts per item — on 2026-08-09 two
issue-filing sessions made 8 such calls and drained the whole 5,000/hr budget,
stalling every parallel session. Verify a field landed by reading back that one
item (`node(id:"<ITEM_ID>")`), never by re-pulling the board. Option IDs rotate
whenever a single-select option is edited, so re-read them; never hardcode.

## Step 5: Link the native parent + place it in the order (MANDATORY)

If an epic owns it (Step 2), link via GraphQL `addSubIssue` (node IDs via `repository(...).issue(N) { id }`). The native link is ground truth; the `Parent:` line in Connections mirrors it.

Then **place the issue in the order** — never leave it unplaced:
- **Issue joining an initiative epic:** insert its line into the epic body's pickup-order checklist at its correct position (sequenced after what, parallel with what). If the Depends-on graph doesn't determine the position, ask the user — position IS the priority decision.
- **Standalone issue (no initiative epic):** slot it into a **standing container** (⚡ Express Lane = do now / Odds & Ends = scheduled / Back Burner = low) via `addSubIssue` — the container choice IS the priority decision; ask the user if unclear. An unslotted issue isn't lost (it falls to the implicit tail of the walk, after the last container) but slotting is the norm; leaving it unslotted should be deliberate and stated in the report.
- **If this creation spawned a new epic:** it must get an **Epic Rank** (numeric board field, lower = picked first, compared **among its siblings** — top-level epics rank against the other initiatives/containers; a sub-epic ranks against its siblings inside the umbrella) before this skill reports done — propose a sparse number between its neighbors (e.g. 25 between ranks 20 and 30), the user confirms. An unranked epic is invisible to `/pickup` at any level.

## Step 6: Reverse cascade

For each affected issue noted in Step 2.5, append a dated comment now: what the new issue takes over / changes, with its number. If an existing issue's body now actively misleads, flag it to the user and ask before rewriting.

## Step 7: Report

One compact summary: issue number + title, board fields set, parent linked, Connections lines, cascade comments posted, and (if applicable) where it sits in the owning epic's pickup order.
