---
description: Review changed code for quality, bugs, and rules compliance
---

# Code Review

Review of all changes, tiered to the diff: one combined agent for small
mechanical diffs, the multi-agent pipeline for diffs with blast radius
(Step 1.5). Auto-detects scope based on branch state.

## Step 1: Determine Diff Scope

```bash
# Check if we're on a feature branch with commits ahead of staging/main
CURRENT=$(git branch --show-current)
MERGE_BASE=$(git merge-base origin/staging HEAD 2>/dev/null || git merge-base origin/main HEAD 2>/dev/null)
COMMITS_AHEAD=$(git rev-list --count ${MERGE_BASE}..HEAD 2>/dev/null || echo "0")
```

- **Branch mode** (commits ahead > 0): review the full branch diff (`git diff ${MERGE_BASE}...HEAD`) PLUS any uncommitted changes (`git diff HEAD`)
- **Pre-commit mode** (no commits ahead): review uncommitted + staged changes only (`git diff HEAD` and `git diff --cached`)

If there are no changes in either mode, say "Nothing to review" and stop.

## Step 1.5: Pick the tier (owner ruling 2026-08-09)

**Small-diff mode** — use it when the diff is ≤ ~300 changed lines across ≤ ~6
files with no migration and no shared-state change, OR when the caller says so
(a `/pickup` whose Brief declared `PLAN inline` always reviews at this tier):

- Skip Step 2 entirely — the main agent already has the rules in context and
  wrote the diff; a summary agent summarizes what you already know.
- Run ONE review agent carrying ALL FOUR mandates from Step 3 (rules
  compliance + diff bugs + introduced-code analysis) against the diff and the
  relevant rules.
- Validate its findings inline (Step 4's checks, performed by the main agent
  reading the code) instead of spawning per-finding validation agents.

Everything below (Steps 2–4 as written) is **full mode**, for diffs with real
blast radius. Why the tier exists: on a 5-file diff, two parallel review
agents cost ~285K tokens; the rules agent found zero violations and the
duplicate coverage found nothing the single bug agent had not (2026-08-09
audit, #975).

**Either tier: do not re-execute verification the transcript already
evidences.** If the caller's transcript shows a mutation matrix, a browser
walk, or a test run with its output, cite it — re-running it is duplicate
spend, not independent confirmation. Re-verify only what you have reason to
distrust, and say why.

## Model policy

**Never pin a model tier on any agent — every agent inherits the session's
selected model.** The review runs on whatever model the user chose; pinning
("use opus for bugs") silently overrides that choice and freezes the skill on
old tiers. (User ruling 2026-06-12 — same principle as the eval judge: if a
specific model is running, it's because the user selected it.)

## Step 2: Context Gathering (2 parallel agents)

**Agent A:** Find all CLAUDE.md and `.claude/rules/*.md` files that are relevant to the changed files. Return the file paths AND their contents. A rules file is relevant if it shares a directory ancestor with any changed file, or if it's the root CLAUDE.md. Include the standing conventions from `${CLAUDE_PLUGIN_ROOT}/skills/conventions/` as well (issue-management, testing-standards, supabase-migrations) — those are the cross-repo rules, and in a cloud session they exist only there.

**Agent B:** Read the full diff and return a concise summary of the changes — what was added, modified, removed, and the apparent intent.

## Step 3: Review Pass (4 parallel agents)

Give every agent the diff, the change summary from Step 2B, and the relevant rules from Step 2A.

**Agents 1 + 2: Rules compliance**
Audit the changes against all relevant CLAUDE.md and `.claude/rules/*.md` files. Each agent reviews independently. Flag only clear, unambiguous violations where you can quote the exact rule being broken. Include the rule file path and the specific rule text in each finding.

**Agent 3: Bug scan — diff only**
Scan for bugs visible in the diff itself without reading surrounding code. Flag only significant bugs — logic errors, runtime crashes, data corruption, security issues. Ignore anything you cannot validate from the diff alone.

**Agent 4: Introduced code analysis**
Analyze the new/modified code for problems: incorrect logic, security vulnerabilities, race conditions, unhandled edge cases, missing null checks that will cause runtime errors. Only flag issues in the introduced code, not pre-existing problems.

### What to flag

- Objective bugs that will cause incorrect behavior at runtime
- Clear CLAUDE.md / rules violations with the exact rule quoted
- Dead/unused code introduced by this change
- Code duplication (DRY violations) introduced by this change
- Security vulnerabilities (injection, XSS, exposed secrets)
- Inconsistency with established project patterns (only when the pattern is documented in rules)

### What NOT to flag (false positives)

- Pre-existing issues not introduced by this change
- Subjective style preferences not required by any rules file
- Issues a linter will catch (do not run the linter to verify)
- "Potential" issues that "might" be problems — if you're not certain, don't flag it
- General suggestions or "nice to haves"
- Anything requiring interpretation or judgment calls
- Code that looks unusual but is actually correct (e.g., intentional `as any` casts documented as known patterns)
- Issues explicitly silenced in the code (e.g., lint ignore comments)

## Step 4: Validation Pass (parallel agents)

For EACH issue flagged in Step 3, launch a validation agent (session model, per the model policy above).

Each validation agent receives:
- The flagged issue description
- The relevant section of the diff
- The relevant rules file content (for compliance issues)
- Surrounding code context if needed (read the file)

The agent's job: independently verify the issue is real with high confidence. Check that:
- The bug actually exists (not a misread of the diff)
- The rules violation quotes a real rule that applies to this file
- The issue is in introduced code, not pre-existing
- The fix wouldn't break something else

Return a verdict: **CONFIRMED** or **REJECTED** with reasoning.

## Step 5: Report

Filter out all REJECTED issues. Organize confirmed issues by priority:

**Critical (must fix before committing/merging):**
- Runtime bugs and logic errors
- Security vulnerabilities
- Rules violations marked as required/must in the rules files

**Important (should fix):**
- Inconsistency with documented project patterns
- Dead/unused introduced code
- DRY violations
- Maintainability problems that will cause real pain

**Minor (your call):**
- Small cleanups within the changed code
- Consolidation opportunities

For each issue, include:
1. **File and location** (file path + line number or code snippet)
2. **What's wrong** (1-2 sentences)
3. **Which rule** (for compliance issues — quote the rule and its file path)
4. **Suggested fix** (brief — code snippet if helpful)

### Output rules

- If code is clean after validation, say so briefly: "Review complete. No issues found."
- No changes for the sake of change — every finding must be meaningful
- Be concise. Don't pad the report with praise or filler.
- End with a count: "**X critical, Y important, Z minor** issues found."
