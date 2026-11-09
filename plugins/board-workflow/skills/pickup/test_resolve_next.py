#!/usr/bin/env python3
"""Regression tests for resolve-next.py's dependency gating.

Run from this directory:

    python3 -m unittest test_resolve_next -v

Why fixture-driven rather than unit-testing `epic_blocked` directly: the walk's
helpers (`epic_blocked`, `shipped`, `member_kids`, `available`) are nested inside
`main()` and are not importable. Every I/O boundary `main()` crosses, however, is
a MODULE-level function, so the whole resolver can be driven end-to-end over a
synthetic board — which additionally pins the rendered strings (AC2) and the
walk-membership consequence of blocking an epic, neither of which a direct unit
test of the nested function could reach.

Born with #948 (2026-07-25): an epic's `Depends-on: #<non-epic issue>` was a
silent no-op, so an epic could open while the single issue gating it was still
open. These are the first automated tests this script has ever carried — keep
them running before any edit to the walk.
"""

import contextlib
import importlib.util
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "resolve-next.py")


def _load_module():
    """Import the hyphenated script as a module.

    `OWNER, PROJECT = resolve_board()` runs AT IMPORT and sys.exit()s when the
    board can't be resolved, so the env vars must be set before exec_module.
    """
    os.environ.setdefault("PICKUP_OWNER", "test-owner")
    os.environ.setdefault("PICKUP_PROJECT", "999")
    spec = importlib.util.spec_from_file_location("resolve_next", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RN = _load_module()

REPO = "test-org/test-repo"


def item(number, title, status, rank=None, dev=None):
    """One board row, in the shape `load_board()` returns."""
    return {
        "id": f"PVTI_{number}",
        "repository": f"https://github.com/{REPO}",
        "status": status,
        "epic Rank": rank,
        "module": None,
        "priority": None,
        "dev": dev,
        "content": {"type": "Issue", "number": number, "title": title},
    }


def body(number, text, state="OPEN"):
    return {"number": number, "body": text, "state": state}


def run(board, bodies, argv=None):
    """Drive the resolver over a synthetic board; return its stdout.

    Stubs every side effect: `write_idmap` would otherwise clobber the REAL
    id-map cache that a live /pickup cycle depends on, and the off-board claim
    checks would hit the network.
    """
    saved = {
        "load_board": RN.load_board,
        "load_bodies": RN.load_bodies,
        "write_idmap": RN.write_idmap,
        "git_branch_blob": RN.git_branch_blob,
        "open_claim": RN.open_claim,
        "argv": sys.argv,
    }
    RN.load_board = lambda: board
    RN.load_bodies = lambda repo: bodies
    RN.write_idmap = lambda items: None
    RN.git_branch_blob = lambda: ""
    RN.open_claim = lambda n, repo: None
    sys.argv = ["resolve-next.py"] + (argv or [])
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            RN.main()
    finally:
        RN.load_board = saved["load_board"]
        RN.load_bodies = saved["load_bodies"]
        RN.write_idmap = saved["write_idmap"]
        RN.git_branch_blob = saved["git_branch_blob"]
        RN.open_claim = saved["open_claim"]
        sys.argv = saved["argv"]
    return buf.getvalue()


# --- fixtures -------------------------------------------------------------
#
# Shared shape: epic #200 (rank 10) owns issue #201. What #200 waits on varies
# per test. Epic #300 (rank 20) owns #301 and never waits on anything, so every
# run has at least one available issue and the "NOTHING AVAILABLE" branch (a
# different code path) is not what is being measured.

def base_board(extra=()):
    return [
        item(200, "Epic: Gated", "Todo", rank=10),
        item(201, "Child of gated epic", "Todo"),
        item(300, "Epic: Open", "Todo", rank=20),
        item(301, "Child of open epic", "Todo"),
    ] + list(extra)


def base_bodies(dep_line, extra=None):
    out = {
        200: body(200, f"### Connections\n{dep_line}\n\n- [ ] #201 — child"),
        201: body(201, "### Connections\nParent: #200"),
        300: body(300, "### Connections\n\n- [ ] #301 — child"),
        301: body(301, "### Connections\nParent: #300"),
    }
    out.update(extra or {})
    return out


class EpicDependsOnIssue(unittest.TestCase):
    """AC1 — an epic waiting on a non-epic issue is blocked until it ships."""

    def test_unshipped_issue_dep_blocks_the_epic_and_its_children(self):
        # THE RED TEST: before #948 the epic was walked and #201 was offered.
        board = base_board([item(101, "Blocking issue", "Todo")])
        bodies = base_bodies("Depends-on: #101 — gates the epic",
                             {101: body(101, "standalone")})
        out = run(board, bodies)
        self.assertIn("epic #200 — waits on issue #101", out)
        self.assertNotIn("#201", out)          # child left the walk
        self.assertIn("NEXT → #301", out)      # walk spilled to the next epic

    def test_shipped_issue_dep_does_not_block(self):
        # "On Staging" is the production-realistic case: `load_board()` queries
        # `-status:Done`, so a Done dep never reaches `items` at all and instead
        # falls through the off-board branch. The Done subTest is fixture-only —
        # it pins the SHIPPED_STATES membership, not a live code path.
        for status in ("Done", "On Staging"):
            with self.subTest(status=status):
                board = base_board([item(101, "Blocking issue", status)])
                bodies = base_bodies("Depends-on: #101 — gates the epic",
                                     {101: body(101, "standalone")})
                out = run(board, bodies)
                self.assertNotIn("waits on issue #101", out)
                self.assertIn("NEXT → #201", out)

    def test_in_progress_issue_dep_still_blocks(self):
        # In Progress is not shipped — the dependent epic must stay closed.
        board = base_board([item(101, "Blocking issue", "In Progress", dev="Beau")])
        bodies = base_bodies("Depends-on: #101 — gates the epic",
                             {101: body(101, "standalone")})
        out = run(board, bodies)
        self.assertIn("epic #200 — waits on issue #101", out)


class EpicDependsOnEpic(unittest.TestCase):
    """Pre-existing epic→epic semantics must be unchanged."""

    def test_epic_dep_with_unshipped_kid_blocks_and_is_labelled_epic(self):
        board = base_board([item(100, "Epic: Blocker", "Todo", rank=5),
                            item(102, "Kid of blocker", "Todo")])
        bodies = base_bodies("Depends-on: #100 — gates the epic",
                             {100: body(100, "### Connections\n\n- [ ] #102 — kid"),
                              102: body(102, "Parent: #100")})
        out = run(board, bodies)
        self.assertIn("epic #200 — waits on epic #100 (unshipped items)", out)

    def test_epic_dep_fully_shipped_does_not_block(self):
        board = base_board([item(100, "Epic: Blocker", "Todo", rank=5),
                            item(102, "Kid of blocker", "Done")])
        bodies = base_bodies("Depends-on: #100 — gates the epic",
                             {100: body(100, "### Connections\n\n- [ ] #102 — kid"),
                              102: body(102, "Parent: #100")})
        out = run(board, bodies)
        self.assertNotIn("waits on epic #100", out)
        self.assertIn("NEXT → #201", out)

    def test_zero_member_dep_epic_still_does_not_block(self):
        # Deliberately deferred facet (#948): an empty dep epic gates nothing.
        # Pinned so a future change to it is a visible decision, not a slip.
        board = base_board([item(100, "Epic: Empty blocker", "Todo", rank=5)])
        bodies = base_bodies("Depends-on: #100 — gates the epic",
                             {100: body(100, "no members")})
        out = run(board, bodies)
        self.assertNotIn("waits on", out)
        self.assertIn("NEXT → #201", out)

    def test_dead_dep_epic_with_unshipped_kid_still_blocks(self):
        # Deliberately deferred facet (#948): a CLOSED dep epic that still holds
        # unshipped members blocks forever. Pinned as current behaviour; the
        # escape hatch is tracked as a follow-up, not fixed here.
        board = base_board([item(100, "Epic: Dead blocker", "Todo", rank=5),
                            item(102, "Kid of blocker", "Todo")])
        bodies = base_bodies(
            "Depends-on: #100 — gates the epic",
            {100: body(100, "### Connections\n\n- [ ] #102 — kid", state="CLOSED"),
             102: body(102, "Parent: #100")})
        out = run(board, bodies)
        self.assertIn("epic #200 — waits on epic #100", out)


class OffBoardDep(unittest.TestCase):
    """Fork A (owner call, #948): off-board deps keep the ignore-entirely rule."""

    def test_off_board_open_issue_dep_does_not_block(self):
        board = base_board()          # #101 exists in the repo, not on the board
        bodies = base_bodies("Depends-on: #101 — gates the epic",
                             {101: body(101, "off-board and open", state="OPEN")})
        out = run(board, bodies)
        self.assertNotIn("waits on", out)
        self.assertIn("NEXT → #201", out)


class IssueLevelUnchanged(unittest.TestCase):
    """AC3 — plain issue-level Depends-on resolution is untouched."""

    def test_issue_with_unshipped_dep_is_not_available(self):
        board = base_board([item(101, "Blocking issue", "Todo")])
        bodies = base_bodies("", {101: body(101, "standalone"),
                                  201: body(201, "Parent: #200\n"
                                                 "Depends-on: #101 — needs it")})
        out = run(board, bodies)
        self.assertIn("#201 — waits on #101", out)
        self.assertIn("NEXT → #301", out)

    def test_issue_with_shipped_dep_is_available(self):
        board = base_board([item(101, "Blocking issue", "Done")])
        bodies = base_bodies("", {101: body(101, "standalone"),
                                  201: body(201, "Parent: #200\n"
                                                 "Depends-on: #101 — needs it")})
        out = run(board, bodies)
        self.assertIn("NEXT → #201", out)


class BoardViewRendering(unittest.TestCase):
    """AC2 — --board names the blocker and says which kind it is."""

    def test_board_view_names_a_blocking_issue(self):
        board = base_board([item(101, "Blocking issue", "Todo")])
        bodies = base_bodies("Depends-on: #101 — gates the epic",
                             {101: body(101, "standalone")})
        out = run(board, bodies, argv=["--board"])
        self.assertIn("⛔ waits on issue #101", out)

    def test_board_view_names_a_blocking_epic(self):
        board = base_board([item(100, "Epic: Blocker", "Todo", rank=5),
                            item(102, "Kid of blocker", "Todo")])
        bodies = base_bodies("Depends-on: #100 — gates the epic",
                             {100: body(100, "### Connections\n\n- [ ] #102 — kid"),
                              102: body(102, "Parent: #100")})
        out = run(board, bodies, argv=["--board"])
        self.assertIn("⛔ waits on epic #100", out)
        self.assertIn("← unblocks 1 epic", out)

    def test_issue_blocker_does_not_claim_an_unblocks_annotation(self):
        # `epic_line` renders epics only, so an issue blocker must not be
        # counted into `unblocks` — it could never be printed there anyway.
        board = base_board([item(101, "Blocking issue", "Todo")])
        bodies = base_bodies("Depends-on: #101 — gates the epic",
                             {101: body(101, "standalone")})
        out = run(board, bodies, argv=["--board"])
        self.assertNotIn("unblocks", out)

    def test_gated_but_drained_epic_shows_both_markers(self):
        # The gate marker must not swallow the close prompt. #271 (17/17, gated
        # on a vestigial dep) lost its "drained — close?" the moment #948 made
        # epic→issue edges live; epic closure is what re-decides ranks, so the
        # prompt has to survive the gate.
        board = [item(200, "Epic: Gated", "Todo", rank=10),
                 item(201, "Child of gated epic", "Done"),
                 item(101, "Blocking issue", "Todo")]
        bodies = {200: body(200, "### Connections\nDepends-on: #101 — gates it\n\n"
                                 "- [ ] #201 — child"),
                  201: body(201, "Parent: #200"),
                  101: body(101, "standalone")}
        out = run(board, bodies, argv=["--board"])
        self.assertIn("⛔ waits on issue #101", out)
        self.assertIn("✔ drained — close?", out)

    def test_gated_epic_still_shows_an_in_progress_child(self):
        # A child claimed before its epic's gate went live is still in flight.
        board = [item(200, "Epic: Gated", "Todo", rank=10),
                 item(201, "Child of gated epic", "In Progress", dev="Amy"),
                 item(101, "Blocking issue", "Todo")]
        bodies = {200: body(200, "### Connections\nDepends-on: #101 — gates it\n\n"
                                 "- [ ] #201 — child"),
                  201: body(201, "Parent: #200"),
                  101: body(101, "standalone")}
        out = run(board, bodies, argv=["--board"])
        self.assertIn("⛔ waits on issue #101", out)
        self.assertIn("▶ #201 in progress (Amy)", out)

    def test_gated_epic_shows_no_next_dispatch_hint(self):
        # A gated epic dispatches nothing of its own. An issue of its that still
        # reaches the walk got there via ANOTHER epic's checklist and is offered
        # at that epic's line, so a `next` here would misread as dispatchable.
        board = [item(200, "Epic: Gated", "Todo", rank=10),
                 item(201, "Child of gated epic", "Todo"),
                 item(300, "Epic: Claims it too", "Todo", rank=20),
                 item(101, "Blocking issue", "Todo")]
        bodies = {200: body(200, "### Connections\nDepends-on: #101 — gates it\n\n"
                                 "- [ ] #201 — child"),
                  201: body(201, "Parent: #200"),
                  300: body(300, "### Connections\n\n- [ ] #201 — claimed here too"),
                  101: body(101, "standalone")}
        out = run(board, bodies, argv=["--board"])
        # the epic's own spine line, not the "NEXT → …" header that also cites it
        gated_line = next(l for l in out.splitlines() if l.lstrip().startswith("r10"))
        self.assertIn("⛔ waits on issue #101", gated_line)
        self.assertNotIn("next #201", gated_line)


class NothingAvailableReport(unittest.TestCase):
    """The blocker report on the no-walk path names the kind too."""

    def test_report_names_the_blocking_issue(self):
        # #101 is In Progress so it is neither shipped nor itself pickable —
        # the epic stays gated and the walk is empty, which is the branch
        # under test.
        board = [item(200, "Epic: Gated", "Todo", rank=10),
                 item(201, "Child of gated epic", "Todo"),
                 item(101, "Blocking issue", "In Progress", dev="Beau")]
        bodies = {200: body(200, "### Connections\nDepends-on: #101 — gates it\n\n"
                                 "- [ ] #201 — child"),
                  201: body(201, "Parent: #200"),
                  101: body(101, "standalone")}
        out = run(board, bodies)
        self.assertIn("NOTHING AVAILABLE", out)
        self.assertIn("epic #200 blocked by unshipped issue #101", out)


class SelfDependentEpic(unittest.TestCase):
    """#1045 — an epic whose Depends-on names its OWN member must not deadlock.

    Before the fix the epic was skipped whole until the member shipped, and the
    member could not reach the tail because the live epic still claimed it, so
    /pickup said NOTHING AVAILABLE with no hint the blocker was inside.
    """

    def _board(self, extra=()):
        return [item(200, "Epic: Self-gated", "Todo", rank=10),
                item(201, "Member named by the gate", "Todo"),
                item(202, "Other member", "Todo")] + list(extra)

    def _bodies(self, dep_line, extra=None):
        out = {200: body(200, f"### Connections\n{dep_line}\n\n"
                              "- [ ] #201 — first\n- [ ] #202 — second"),
               201: body(201, "Parent: #200"),
               202: body(202, "Parent: #200")}
        out.update(extra or {})
        return out

    def test_self_dependency_does_not_deadlock_the_epic(self):
        # THE RED TEST: before #1045 this printed NOTHING AVAILABLE.
        out = run(self._board(), self._bodies("Depends-on: #201 — do it first"))
        self.assertNotIn("NOTHING AVAILABLE", out)
        self.assertNotIn("waits on issue #201", out)
        self.assertIn("NEXT → #201", out)

    def test_other_members_stay_reachable(self):
        # AC3: with the named member in flight, the rest of the epic is offered.
        board = [item(200, "Epic: Self-gated", "Todo", rank=10),
                 item(201, "Member named by the gate", "In Progress", dev="Amy"),
                 item(202, "Other member", "Todo")]
        out = run(board, self._bodies("Depends-on: #201 — do it first"))
        self.assertIn("NEXT → #202", out)

    def test_warning_names_the_epic_and_the_member(self):
        # AC1 + AC2, on the default report.
        out = run(self._board(), self._bodies("Depends-on: #201 — do it first"))
        self.assertIn("SELF-DEPENDENCIES", out)
        self.assertIn("epic #200 depends on its own member #201", out)

    def test_board_view_flags_it_as_a_hygiene_defect(self):
        out = run(self._board(), self._bodies("Depends-on: #201 — do it first"),
                  argv=["--board"])
        self.assertIn("epic #200 depends on its own member #201", out)
        self.assertNotIn("⛔", out)

    def test_dependency_on_itself_is_also_caught(self):
        out = run(self._board(), self._bodies("Depends-on: #200 — typo"))
        self.assertIn("epic #200 depends on itself", out)
        self.assertIn("NEXT → #201", out)

    def test_dependency_on_a_member_of_a_sub_epic_is_caught(self):
        # The member sits one level down: #200 → sub-epic #210 → #211.
        board = self._board([item(210, "Epic: Sub", "Todo", rank=1),
                             item(211, "Grandchild", "Todo")])
        bodies = self._bodies("Depends-on: #211 — deep",
                              {210: body(210, "Parent: #200\n\n- [ ] #211 — gc"),
                               211: body(211, "Parent: #210")})
        out = run(board, bodies)
        self.assertIn("epic #200 depends on its own member #211", out)
        self.assertNotIn("NOTHING AVAILABLE", out)
        self.assertIn("NEXT → #211", out)

    def test_dependency_on_its_own_sub_epic_is_caught(self):
        board = self._board([item(210, "Epic: Sub", "Todo", rank=1),
                             item(211, "Grandchild", "Todo")])
        bodies = self._bodies("Depends-on: #210 — sub first",
                              {210: body(210, "Parent: #200\n\n- [ ] #211 — gc"),
                               211: body(211, "Parent: #210")})
        out = run(board, bodies)
        self.assertIn("epic #200 depends on its own member #210", out)
        self.assertNotIn("waits on epic #210", out)

    def test_real_dependency_alongside_a_self_dependency_still_gates(self):
        # Ignoring the self-edge must not open a genuine gate, and the genuine
        # gate must not hide the defect warning.
        board = self._board([item(101, "Real blocker", "In Progress", dev="Beau")])
        bodies = self._bodies("Depends-on: #101 — real\nDepends-on: #201 — self",
                              {101: body(101, "standalone")})
        out = run(board, bodies)
        self.assertIn("epic #200 blocked by unshipped issue #101", out)
        self.assertIn("epic #200 depends on its own member #201", out)

    def test_sibling_dependency_of_a_sub_epic_is_not_a_self_dependency(self):
        # Sub-epic #210 waiting on #201, a member of its PARENT, is an ordinary
        # cross-epic edge, not a self-dependency, and must keep gating.
        board = self._board([item(210, "Epic: Sub", "Todo", rank=1),
                             item(211, "Grandchild", "Todo")])
        bodies = self._bodies("",
                              {210: body(210, "Parent: #200\nDepends-on: #201 — x"
                                              "\n\n- [ ] #211 — gc"),
                               211: body(211, "Parent: #210")})
        out = run(board, bodies)
        self.assertNotIn("SELF-DEPENDENCIES", out)
        self.assertIn("epic #210 — waits on issue #201", out)

    # --- the mirror direction: the dependency CONTAINS the dependent ---------

    def test_sub_epic_waiting_on_its_parent_epic_is_caught(self):
        # #200's member set includes sub-epic #210, which can only finish once
        # #211 ships — and #211 is behind #210's gate. Before the fix this was
        # a silent NOTHING AVAILABLE, and closing #200 (as --board suggested)
        # made #211 vanish instead of freeing it.
        board = [item(200, "Epic: Parent", "Todo", rank=10),
                 item(201, "Shipped member", "Done"),
                 item(210, "Epic: Sub", "Todo", rank=1),
                 item(211, "Grandchild", "Todo")]
        bodies = {200: body(200, "- [ ] #201 — a\n- [ ] #210 — sub"),
                  201: body(201, "Parent: #200"),
                  210: body(210, "Parent: #200\nDepends-on: #200 — up\n\n- [ ] #211 — gc"),
                  211: body(211, "Parent: #210")}
        out = run(board, bodies)
        self.assertIn("epic #210 depends on its own parent epic #200", out)
        self.assertNotIn("NOTHING AVAILABLE", out)
        self.assertIn("NEXT → #211", out)

    def test_issue_waiting_on_its_own_epic_is_caught(self):
        out = run(self._board(), {200: body(200, "- [ ] #201 — a\n- [ ] #202 — b"),
                                  201: body(201, "Parent: #200\nDepends-on: #200 — x"),
                                  202: body(202, "Parent: #200")})
        self.assertIn("#201 depends on its own parent epic #200", out)
        self.assertIn("NEXT → #201", out)
        self.assertNotIn("waits on #200", out)

    def test_child_defect_is_reported_while_the_parent_is_gated(self):
        # The defect pass runs over every live item, not only walked epics, so
        # a parent's real blocker cannot hide a sub-epic's self-dependency.
        board = [item(200, "Epic: Gated parent", "Todo", rank=10),
                 item(101, "Real blocker", "In Progress", dev="Beau"),
                 item(210, "Epic: Sub", "Todo", rank=1),
                 item(211, "Grandchild", "Todo")]
        bodies = {200: body(200, "Depends-on: #101 — real\n\n- [ ] #210 — sub"),
                  101: body(101, "standalone"),
                  210: body(210, "Parent: #200\nDepends-on: #211 — self\n\n- [ ] #211 — gc"),
                  211: body(211, "Parent: #210")}
        out = run(board, bodies)
        self.assertIn("epic #210 depends on its own member #211", out)
        self.assertIn("epic #200 blocked by unshipped issue #101", out)

    def test_member_of_a_dead_sub_epic_is_still_a_real_gate(self):
        # A dead sub-epic releases its members to the tail, where they can
        # ship, so an edge to one of them clears and must keep gating.
        board = self._board([item(210, "Epic: Dead sub", "Done", rank=1),
                             item(211, "Released grandchild", "Todo")])
        bodies = self._bodies("Depends-on: #211 — real",
                              {210: body(210, "Parent: #200\n\n- [ ] #211 — gc",
                                         state="CLOSED"),
                               211: body(211, "Parent: #210")})
        out = run(board, bodies)
        self.assertNotIn("SELF-DEPENDENCIES", out)
        self.assertIn("epic #200 — waits on issue #211", out)
        self.assertIn("NEXT → #211", out)


if __name__ == "__main__":
    unittest.main()
