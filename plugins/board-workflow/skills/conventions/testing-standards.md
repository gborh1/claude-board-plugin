# Testing Standards

## Philosophy

Tests are not optional — every issue that changes code requires them. Write during or before
implementation. **Never modify a test to make it pass without fixing the underlying code.** Tests
pass in CI before merge.

## Cadence — targeted while iterating, full exactly once (owner rule 2026-07-29)

- **The full suite runs ONCE per unit of work — at ship time, before commit. Never per-change.**
- While iterating, run only the tests that map to the changed surface: one stage's tests, not the
  whole tier folder; the touched module, not the pipeline.
- **Match the test to the change surface.** Prompt, skill-file, and docs changes run ZERO code
  tests — nothing they can break is code-testable. Don't run a code suite because "something
  changed."
- The repo's decision gate answers WHICH tiers a change requires; this rule governs WHEN (once, at
  the end) and HOW NARROW (the touched surface) until then.

## Tiers

| Tier | When |
|---|---|
| Component tests | new components, hooks, utils — renders, props, interactions, edge cases (empty/error/loading) |
| User flow verification | features and multi-step UI behavior — walked in a real browser |
| Full suite | major refactors, release candidates |

Repos define their own tier commands and folder layout; see the project's testing rules.

## Test Integrity — never paper over a bug

When a test fails, ask: is the test wrong, or the code? Code wrong → **fix the code**. Test wrong
(bad assertion/selector/assumption) → fix the test.

Banned: conditional assertions that skip checks on failure (`if (res.status === 200) {...}`),
loosening a specific expectation to `expect(res.ok)`, "known issue" comments paired with weakened
assertions, filtering out real errors. If a bug can't be fixed now, `test.skip()` with a link to the
issue — a skipped test is honest; a passing test that ignores failures is dangerous.

## User Flow Verification

Verified by walking the app in a real browser, not by writing automated scripts. Requirements are
generated **from source code** (never from spec docs, which go stale), recorded as REQ-NNN
checkboxes, and each one must pass or fail — no skipping. A failure becomes a Bug issue.

REQ numbers are sequential per project and **permanent — never reuse a retired number**.

**Tools, in order:** in-harness preview/browser tools → Playwright MCP → Claude in Chrome →
Playwright spec files (last resort, only where automated regression protection is worth the
maintenance: auth, data persistence).

Two modes:

**Mode 1 — embedded in a feature issue.** The issue carries a `### User Flow Requirements` section
of REQ-NNN checkboxes for the UI behavior it introduces. At pickup: implement → component tests →
walk each REQ in the browser before the PR → check them off. A failure is a behavior the feature is
supposed to have — fix it, don't file it.

**Mode 2 — standalone test issue** (`Work Type = Test`), when verifying an existing area on demand.
Read the source, generate one requirement per testable behavior, and the issue IS the requirements
list — no separate matrix document.

```markdown
### Test Scope
[Feature area] — [N] requirements generated from code analysis

### Requirements
- [ ] REQ-NNN: [testable behavior]

### Verification Method
User Flow Verification (browser)

### Context
- Source files analyzed: […]
```

Run it: walk each requirement in order, check off passes, file a Bug per failure, then close with a
summary. Audit coverage by filtering the board on `Work Type = Test`.
