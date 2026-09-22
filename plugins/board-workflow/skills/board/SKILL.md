---
name: board
description: Show the current priority board — open work only, epics in rank order with issues in pickup order beneath. Renders a hierarchy diagram by default; `/board table` prints the raw resolver table. Use when the user asks for the board, the priority board, the state of open work, what is in progress, or what to pick up next.
argument-hint: "[table]"
---

# /board — Priority Board Snapshot

Show the current priority board: **open work only**, epics in rank order, issues
in pickup order beneath. Default output is a **hierarchy diagram** (owner
preference, 2026-07-12); `/board table` prints the raw resolver table instead.

## Step 1 — pull the data (always)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/pickup/resolve-next.py --list
```

This is the same graph engine `/pickup` uses. READ-ONLY. Self-configures board
coordinates from the repo. Keep its output — it is the data for either renderer.

## Step 1b — dev reconcile (always, from the data already pulled)

From that same output, count the **In Progress** rows per `Dev`. A dev on **2+
In Progress issues is a double-booking** — one dev works one issue at a time.
It happens when two `/pickup` runs read the board before either writes its
claim; the issue-scoped lock cannot see it (see pickup Phase 1.2b).

Surface it in one line under the widget and offer to reassign — do not silently
fix it. The cost is not lost work: it is a **phantom-busy board**, which makes
the next `/pickup` STOP on "all three devs busy" while a dev sits idle.

To resolve which claim came second, read the claim comments — they carry the
authoritative timestamp and worktree:

```bash
gh issue view <N> --json comments -q '.comments[].body' | grep -oE '🔒 Claimed by .*'
```

Reassign the **later** claim to the most senior genuinely-free dev (seniority
order = the resolver's `devs` line) by setting the board's Dev field, and comment
on the issue saying what happened. Zero In Progress rows, or one per dev → say
nothing.

## Step 2 — render

**If the argument is `table`, or the `mcp__visualize__show_widget` tool is
unavailable:** print the resolver's Markdown table verbatim, no commentary.

**Otherwise (default): render the hierarchy widget.** Call
`mcp__visualize__read_me` (modules: ["diagram"]) silently if not already loaded
this session, then `mcp__visualize__show_widget` with an HTML tree built from
the resolver output plus the visible epics' bodies:

- **One card per standing bucket / top-level epic, in rank order** (rank badge
  `rN · #issue` + title). Children indent inside with a left border rail.
- **Umbrella epics** (children are epics) render as an outer card containing
  nested area-epic cards in rank order — the hierarchy must be visible.
- **Issues** render as compact rows: `#N` muted · title · status. In-progress
  items get an accent chip with the dev name. Blocked epics get a warning chip
  naming what they wait on (from their body's `Depends-on:` line).
- **Groups render as ONE row.** The resolver already collapses riders: a lead
  row arrives carrying `(+ #a #b …)`. Render it as a single row with a
  `group of N` chip and the rider numbers muted after the title — never as
  separate rows per rider. The group is the unit of execution; the board must
  read in group units, not confetti.
- **Lanes:** if an epic's body has `### <name> lane` sections, render them as
  side-by-side columns with the body's pickup order and its `→ after #N` /
  `∥` (parallel-safe) annotations.
- **Containers** (Express Lane / Odds & Ends / Back Burner) compress to a
  single row: rank, name, item count (list items only if ≤3).
- **On-staging items** compress to one muted footnote line.
- Follow the visualize design rules: CSS variables only, flat, sentence case,
  no emoji (Tabler icons ok), font ≥11px, weights 400/500.

After the widget, write at most one line of text — the single most decision-
relevant fact (e.g. what gate opens next). No re-narration of the diagram.

## Errors

- **GitHub rate limit**: run `gh api rate_limit --jq .resources.graphql`, tell
  the user the reset time. Do not loop-retry.
- **Could not resolve board coordinates**: tell the user to set
  `PICKUP_OWNER`/`PICKUP_PROJECT` or add `.claude/pickup.json`.
