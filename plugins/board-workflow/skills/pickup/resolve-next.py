#!/usr/bin/env python3
"""
resolve-next.py — deterministic /pickup Phase-0 resolver.

Does the "which issue is next?" walk in ONE pass instead of a dozen sequential
gh calls + in-context graph reasoning. Encodes the scheduler paradigm from
the conventions skill, issue-management.md (Priority & Devs):

  - walk top-level epics by Epic Rank ascending (lower first), recursing into
    sub-epics in their local rank order
  - an epic with an epic-level `Depends-on: #E` is skipped whole until every
    item of #E has shipped; when the dep is an ISSUE rather than an epic the
    edge gates on that one issue shipping (the epic-only reading made every
    epic→issue edge a silent no-op — #877's freshness gate, #948, 2026-07-25)
  - a CLOSED (or board-Done) epic is DEAD: never walked, and its leftover
    checklist lines claim nothing — otherwise a ghost epic smuggles re-homed
    issues into the walk at its old rank position (the #148 incident, 2026-07-16)
  - an UNRANKED epic is invisible to the walk (issue-management.md calls this
    a creation defect) — skipped LOUDLY, so the defect surfaces instead of the
    epic's issues being walked at an arbitrary position
  - within an epic, take issues in the epic body's checklist order
  - an issue is AVAILABLE iff: Status in {Todo, Backlog}, not an epic, not a
    rider, and every `Depends-on: #N` has shipped (On Staging / Done / closed)
  - riders are never picked directly; their lead is the pickup
  - Module collision against a busy dev's in-flight issue is FLAGGED, not
    auto-excluded (the human/agent makes the final call, per the rules)

READ-ONLY: pulls the board + open issue bodies, prints a report. Writes nothing.

Generic across repos — NO hardcoded board. Board coordinates resolve in order:
  1. --owner / --project flags
  2. PICKUP_OWNER / PICKUP_PROJECT env vars
  3. .claude/pickup.json in the repo root  {"owner": "...", "project": N}
  4. parse the repo's docs (CLAUDE.md / .claude/rules/issue-management.md) for
     the documented `gh project item-list <N> --owner <owner>` command
The repo for issue bodies is derived from the board's own `.repository` field,
so the same script works unchanged in any repo that uses this paradigm.
"""
import json
import os
import re
import subprocess
import sys


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def resolve_board():
    owner = project = None
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--owner" and i + 1 < len(argv):
            owner = argv[i + 1]
        if a == "--project" and i + 1 < len(argv):
            project = argv[i + 1]
    owner = owner or os.environ.get("PICKUP_OWNER")
    project = project or os.environ.get("PICKUP_PROJECT")
    if owner and project:
        return owner, str(project)

    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True).stdout.strip() or os.getcwd()

    cfg_path = os.path.join(root, ".claude", "pickup.json")
    if os.path.exists(cfg_path):
        try:
            cfg = json.loads(_read(cfg_path))
            owner = owner or cfg.get("owner")
            project = project or cfg.get("project")
        except (ValueError, OSError):
            pass
    if owner and project:
        return owner, str(project)

    blob = "\n".join(_read(os.path.join(root, p)) for p in (
        "CLAUDE.md", ".claude/CLAUDE.md", ".claude/rules/issue-management.md"))
    # Prefer the declarative "- **Owner:** x / - **Project number:** n" lines.
    # The legacy path below scraped coordinates out of a documented
    # `gh project item-list` command — which broke the day those docs were
    # (correctly) rewritten to stop recommending that command (2026-08-09).
    # Never make config depend on prose that is expected to change.
    m = re.search(r"(?mi)^\s*[-*]\s*\*\*Owner:?\*\*[:\s]*([\w.-]+)", blob)
    if m:
        owner = owner or m.group(1)
    m = re.search(r"(?mi)^\s*[-*]\s*\*\*Project (?:number|#):?\*\*[:\s]*(\d+)", blob)
    if m:
        project = project or m.group(1)
    if owner and project:
        return owner, str(project)

    m = re.search(r"gh project item-list\s+(\d+)\s+--owner\s+([\w.-]+)", blob)
    if m:  # legacy fallback — repos whose docs still name the old command
        project = project or m.group(1)
        owner = owner or m.group(2)
    if owner and project:
        return owner, str(project)

    sys.exit("ERROR: could not resolve board coordinates for this repo.\n"
             "  Fix with any one of:\n"
             "    - export PICKUP_OWNER=<owner> PICKUP_PROJECT=<n>\n"
             "    - pass --owner <owner> --project <n>\n"
             "    - add .claude/pickup.json  {\"owner\":\"<owner>\",\"project\":<n>}\n"
             "    - document `- **Owner:** <owner>` and `- **Project number:** <n>`\n"
             "      under a '## Project Board' heading in CLAUDE.md")


OWNER, PROJECT = resolve_board()

SHIPPED_STATES = {"On Staging", "Done"}
PICKABLE_STATES = {"Todo", "Backlog"}
DEVS = ["Makayla", "Beau", "Amy", "Gartay", "Nehn", "Mien", "AJ", "Aubrey",
        "Jackson"]  # seniority order = fill order; the ONE source of truth for the roster.
# Every name here must also exist as an option on the `Dev` single-select of EVERY
# board this resolver serves (gborh1/1 Needo, gborh1/2 Meridian ESG). A name the
# board does not know fails the claim mutation silently — the issue goes In Progress
# with no Dev, which reads as a free dev and invites a double-booking.

# File-path tokens named in an issue body — used ONLY for a read-only collision
# FLAG (never to auto-block). Catches the cross-epic file overlap that no
# Depends-on edge encodes: the resolver's known blind spot. A candidate that
# shares a file with a busy dev's in-flight issue but has no serializing edge is
# exactly the missing-edge case — flag it so the agent confirms + encodes it.
FILE_RE = re.compile(r"[A-Za-z0-9_][\w./-]*\.(?:js|jsx|ts|tsx|py|sql|md|json|css|sh)\b")


def file_tokens(body):
    return {m.group(0) for m in FILE_RE.finditer(body or "")}


def sh(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


# --- reality cross-check (the double-pickup guard) -------------------------
# The board's Status is the only availability signal the walk reads, but a
# parallel session claims the board only AFTER the resolver has run in it —
# leaving a minutes-wide window where an issue is already being built (branch
# cut, worktree open, claim comment posted) while the board still says Todo. A
# second bare `/pickup` in that window re-dispatches the same issue (the
# 2026-07-17 #348 incident; the 2026-07-06 one had a different, since-fixed
# cause). These helpers catch it: an issue whose board status is pickable but
# which a branch / worktree / unreleased claim comment shows is in flight is
# "claimed off-board" — skipped for target selection and surfaced LOUDLY so the
# board/reality mismatch gets reconciled.

# Claim/release markers the /pickup skill writes as its FIRST and LAST acts.
# The claim COMMENT (not the board field) is the authoritative lock: board
# field edits carry no visible author/timestamp; a comment does.
CLAIM_RE = re.compile(r"<!--\s*pickup:claim\b(.*?)-->", re.S)
RELEASE_RE = re.compile(r"<!--\s*pickup:release\b")


def git_branch_blob():
    """Local + remote branch short-names and the worktree list, newline-joined.
    Worktrees are the strongest local signal in this setup: parallel sessions
    each run in their own worktree, so `git worktree list` shows a sibling
    session's in-flight branch with no network fetch needed."""
    out = []
    for args in (["git", "for-each-ref", "--format=%(refname:short)",
                  "refs/heads", "refs/remotes"],
                 ["git", "worktree", "list"]):
        try:
            out.append(subprocess.run(args, capture_output=True,
                                      text=True).stdout)
        except Exception:
            pass
    return "\n".join(out)


def branch_names_issue(blob, n):
    """True iff issue #n appears as a token in some branch/worktree name
    (e.g. `fix/348-...`). Token-bounded so #48 never matches `fix/348-...`."""
    return bool(re.search(rf"(?:^|[/_-])0*{n}(?:[/_-]|$)", blob, re.M))


def open_claim(n, repo):
    """Return a short claimant string if issue #n carries an UNRELEASED pickup
    claim comment, else None. Best-effort: an API hiccup returns None (never
    block resolution on it). The most recent claim/release marker wins.
    Deliberately REST (`gh api`), not `gh issue view` — issue comments are the
    authoritative lock and must stay readable even when the GraphQL pool (which
    the board pull drains) is exhausted. REST comments come oldest-first."""
    try:
        raw = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues/{n}/comments?per_page=100"],
            capture_output=True, text=True, check=True).stdout
        comments = json.loads(raw)
    except Exception:
        return None
    claimant = None  # set by the latest claim, cleared by a later release
    for c in comments:
        body = c.get("body", "")
        if RELEASE_RE.search(body):
            claimant = None
        m = CLAIM_RE.search(body)
        if m:
            claimant = (m.group(1).strip() or "another session")
    return claimant


# --- board read: LIVE-FIRST, cache = outage-only fallback ------------------
# The board's fields (Status/Dev/Epic Rank) live in Projects v2 — GraphQL-only,
# ~400+ pts per pull, one shared 5,000/hr pool per ACCOUNT (all repos + all
# parallel sessions draw from it). Dispatch must be priority-correct and see
# just-shipped changes, so every resolve pulls the board LIVE — a stale board
# picks the WRONG-priority issue, not merely a late one, and that defeats the
# whole scheduler. The on-disk copy is written on every success purely as an
# OUTAGE net: if a live pull fails (rate limit / GitHub down), we serve the last
# good copy LOUDLY instead of crashing. It is never served on a healthy pull.
#
# Cost is controlled the right way instead — by pulling ONCE per cycle, not by
# staleness: (1) the id-map file below lets the whole cycle reuse item ids so no
# write ever re-pulls the board just to recover an id; (2) freshness re-checks
# read the SPECIFIC issues in play (REST/narrow), never the full board. So a
# clean cycle = exactly one live board pull.
# Not ~/.claude: when this ships inside a plugin the script lives under the
# plugin root, which is not guaranteed writable. A cache is disposable, so
# prefer an explicit override, then the user cache dir.
CACHE_DIR = os.environ.get("PICKUP_CACHE_DIR") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-pickup")


def _cache_file(kind):
    safe = re.sub(r"[^\w.-]", "_", f"{kind}-{OWNER}-{PROJECT}")
    return os.path.join(CACHE_DIR, safe + ".json")


def _cache_read(kind):
    """-> (payload, age_seconds) or (None, None)."""
    import time
    try:
        with open(_cache_file(kind), encoding="utf-8") as f:
            blob = json.load(f)
        return blob["payload"], time.time() - blob["ts"]
    except Exception:
        return None, None


def _cache_write(kind, payload):
    import time
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = _cache_file(kind) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "payload": payload}, f)
        os.replace(tmp, _cache_file(kind))
    except Exception:
        pass  # cache is an optimization, never a failure


def _cached(kind, fetch):
    """LIVE-FIRST with outage-only fallback. Always pulls fresh so dispatch is
    priority-correct and sees just-shipped changes; the on-disk copy is written
    on every success and served ONLY when a live pull fails — never on a healthy
    pull (that would reintroduce the staleness this design exists to avoid)."""
    try:
        result = fetch()
        _cache_write(kind, result)
        return result
    except Exception as e:
        payload, age = _cache_read(kind)
        if payload is not None:
            print(f"⚠ {kind}: LIVE PULL FAILED ({type(e).__name__}) — serving "
                  f"last-good cache ({age/60:.0f} min old) so you aren't blocked. "
                  f"It may be stale; reconcile once the API recovers.",
                  file=sys.stderr)
            return payload
        detail = ""
        if isinstance(e, subprocess.CalledProcessError):
            detail = (e.stderr or e.stdout or "").strip().splitlines()
            detail = ("\n  " + detail[0]) if detail else ""
        sys.exit(f"ERROR: {kind}: live pull failed and no cache exists yet.{detail}\n"
                 f"  If rate-limited: check `gh api rate_limit --jq .resources.core`\n"
                 f"  and re-run after reset.")


# --- id-map: the "never re-pull just for an id" file -----------------------
# An item's ProjectV2 id is STABLE (it never changes for the life of the board
# item), so unlike Status/Dev it is safe to reuse indefinitely. Every board pull
# writes the full {issue# -> item-id} map here; any step in the cycle that must
# mutate ANOTHER issue's board fields (graduate a dependent, field a follow-up)
# reads the id from this file instead of re-pulling all ~220 items to recover
# one id. `--item-id <N>` prints a single id (no GraphQL at all).
def _idmap_file():
    safe = re.sub(r"[^\w.-]", "_", f"idmap-{OWNER}-{PROJECT}")
    return os.path.join(CACHE_DIR, safe + ".json")


def write_idmap(items):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        m = {str(n): it["item_id"] for n, it in items.items() if it.get("item_id")}
        tmp = _idmap_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f)
        os.replace(tmp, _idmap_file())
    except Exception:
        pass


def read_idmap():
    try:
        with open(_idmap_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# --- the board pull ---------------------------------------------------------
# `gh project item-list` costs ~1.2 GraphQL points PER ITEM: measured 708 pts
# for 601 items unfiltered, ~203 with -status:Done. That is the single largest
# spend in the whole flow — at 5,000 pts/hr it caps you at ~7 board pulls, which
# three parallel pickup sessions exhaust in an afternoon.
#
# PORTED TO REST 2026-09-19. GitHub shipped a Projects v2 REST API (API version
# 2026-03-10), and it draws on the `core` pool — a DIFFERENT 5,000/hr budget from
# `graphql`. Measured on the 410-item Meridian board: the full pull costs ZERO
# GraphQL points and ~5 core requests (one per 100-item page, plus the field
# lookup). The board pull can no longer starve parallel sessions, which is the
# failure this comment used to be about.
#
# GraphQL remains as a fallback only, for an environment where the REST version
# isn't served. It is never the first choice.
#
# The emitted shape is byte-compatible with `gh project item-list --format json`
# so every consumer below is untouched: gh lowercases only the first character
# of a field name ("Epic Rank" -> "epic Rank", "Work Type" -> "work Type"), which
# _gh_key() reproduces.
def _gh_key(field_name):
    return field_name[:1].lower() + field_name[1:] if field_name else field_name


# REST is primary. The API version header is required — without it GitHub serves
# 2022-11-28, which predates these endpoints entirely.
_API_VERSION = "2026-03-10"

# The GraphQL query below asked only for SingleSelect / Number / Text values, so
# the REST port requests the same classes and nothing else. Built-ins (assignees,
# labels, milestone, reviewers, linked PRs, sub-issue progress) are skipped: they
# were never in the emitted shape and each one inflates every page.
_VALUE_TYPES = {"single_select", "number", "text", "title"}


def _rest_scalar(v):
    """Flatten a REST field value to the scalar the GraphQL path produced.
    number -> 110 · text/title -> {raw,html} · single_select -> {name:{raw,html}}."""
    if not isinstance(v, dict):
        # GraphQL's ProjectV2ItemFieldNumberValue was a Float, so ranks rendered
        # as "r5.0". REST returns an int. Coerce to keep the emitted shape — and
        # the rendered board — byte-identical.
        if isinstance(v, int) and not isinstance(v, bool):
            return float(v)
        return v
    name = v.get("name")
    if isinstance(name, dict):
        return name.get("raw")
    if name is not None:
        return name
    return v.get("raw")


def _pull_items_rest(root):
    """Page the project's items over REST. Same return contract as the GraphQL
    twin: raise on anything unexpected so _cached() falls back to disk."""
    base = "/%s/%s/projectsV2/%s" % ("users" if root == "user" else "orgs",
                                     OWNER, PROJECT)
    hdr = ["-H", "X-GitHub-Api-Version: " + _API_VERSION]
    fields = json.loads(sh(["gh", "api"] + hdr + [base + "/fields"]))
    ids = ",".join(str(f["id"]) for f in fields
                   if f.get("data_type") in _VALUE_TYPES)
    if not ids:
        raise RuntimeError("no readable fields on project #%s" % PROJECT)
    # Without `fields=`, REST returns Title only.
    rows = json.loads(sh(["gh", "api", "--paginate"] + hdr +
                         [base + "/items?per_page=100&fields=" + ids]))
    if not isinstance(rows, list):
        raise RuntimeError("unexpected REST payload for project #%s" % PROJECT)
    return rows


def _rows_from_rest(nodes):
    """REST item -> the `gh project item-list --format json` row shape."""
    out = []
    for n in nodes:
        c = n.get("content") or {}
        if n.get("content_type") != "Issue" or c.get("number") is None:
            continue
        row = {"id": n.get("node_id"),          # PVTI_… — what item-edit takes
               "title": c.get("title"),
               "content": {"type": "Issue", "number": c["number"],
                           "title": c.get("title")},
               "repository": c.get("repository_url")}
        for f in n.get("fields") or []:
            fname = f.get("name")
            if fname:
                row[_gh_key(fname)] = _rest_scalar(f.get("value"))
        out.append(row)
    return out


_ITEM_PAGE = """
query($login:String!,$num:Int!,$after:String){
  %s(login:$login){ projectV2(number:$num){ items(first:100,after:$after){
    pageInfo{hasNextPage endCursor}
    nodes{ id
      content{ __typename ... on Issue{ number title repository{url} } }
      fieldValues(first:20){ nodes{
        ... on ProjectV2ItemFieldSingleSelectValue{ name field{... on ProjectV2SingleSelectField{name}} }
        ... on ProjectV2ItemFieldNumberValue{ number field{... on ProjectV2Field{name}} }
        ... on ProjectV2ItemFieldTextValue{ text field{... on ProjectV2Field{name}} }
      } }
    } } } }
}"""


def _pull_items(root):
    """Page the project's items under `user` or `organization`. Returns the raw
    node list, or raises so _cached() can fall back to the on-disk copy."""
    out, after = [], None
    while True:
        args = ["gh", "api", "graphql", "-f", "query=" + (_ITEM_PAGE % root),
                "-F", f"login={OWNER}", "-F", f"num={PROJECT}"]
        if after:
            args += ["-F", f"after={after}"]
        d = json.loads(sh(args))
        if d.get("errors"):
            raise RuntimeError(d["errors"][0].get("message", "graphql error"))
        holder = (d.get("data") or {}).get(root)
        if not holder or not holder.get("projectV2"):
            raise RuntimeError(f"no projectV2 #{PROJECT} under {root} {OWNER}")
        page = holder["projectV2"]["items"]
        out += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return out
        after = page["pageInfo"]["endCursor"]


def load_board():
    def fetch():
        items = None
        for root in ("user", "organization"):     # board may be org-owned
            try:
                items = _rows_from_rest(_pull_items_rest(root))
                break
            except Exception:
                continue
        if items is None:
            # REST unavailable (older GitHub, or the API version withdrawn).
            # Fall back to the GraphQL twin rather than failing the pull.
            try:
                nodes = _pull_items("user")
            except Exception:
                nodes = _pull_items("organization")
            items = _rows_from_graphql(nodes)
        # Dispatch/display never need Done items: the walk infers "shipped"
        # from absence + the REST body's closed state (see shipped()).
        items = [r for r in items if r.get("status") != "Done"]
        if not items:
            raise RuntimeError("board pull returned no issues")
        return items
    return _cached("board", fetch)


def _rows_from_graphql(nodes):
    """Fallback shape adapter — kept byte-compatible with _rows_from_rest."""
    items = []
    if True:
        for n in nodes:
            c = n.get("content") or {}
            if c.get("__typename") != "Issue" or c.get("number") is None:
                continue
            row = {"id": n.get("id"),
                   "title": c.get("title"),
                   "content": {"type": "Issue", "number": c["number"],
                               "title": c.get("title")},
                   "repository": (c.get("repository") or {}).get("url")}
            for fv in (n.get("fieldValues") or {}).get("nodes") or []:
                if not fv:
                    continue
                fname = (fv.get("field") or {}).get("name")
                if not fname:
                    continue
                row[_gh_key(fname)] = fv.get("name", fv.get("number", fv.get("text")))
            items.append(row)
    return items


def load_bodies(repo):
    # state=all so closed/Done children still carry their `Parent:` line —
    # needed for accurate per-epic progress (shipped/total) in --board mode.
    # Deliberately REST (`gh api repos/…/issues`), not `gh issue list`
    # (GraphQL): bodies must stay readable when the board pull has drained the
    # GraphQL pool. REST 'issues' includes PRs — filtered out — and lowercase
    # state, normalized to the OPEN/CLOSED the walk expects.
    def fetch():
        raw = sh(["gh", "api", f"repos/{repo}/issues?state=all&per_page=100",
                  "--paginate",
                  "--jq", "[.[] | {number, body, state, pr: (has(\"pull_request\"))}]"])
        out = {}
        dec = json.JSONDecoder()
        i, s = 0, raw.strip()
        while i < len(s):                      # --paginate emits one array per page
            page, j = dec.raw_decode(s, i)
            for it in page:
                if it.get("pr"):
                    continue
                out[it["number"]] = {"number": it["number"],
                                     "body": it.get("body") or "",
                                     "state": (it.get("state") or "").upper()}
            i = j
            while i < len(s) and s[i] in " \n\r\t":
                i += 1
        return out
    got = _cached(f"bodies-{repo.replace('/', '_')}", fetch)
    # JSON round-trips dict keys as strings; the walk indexes by int
    return {int(k): v for k, v in got.items()} if got else {}


def parse_body(body):
    """Extract Connections signals from an issue body."""
    body = body or ""
    parent = None
    m = re.search(r"(?mi)^Parent:\s*#(\d+)", body)
    if m:
        parent = int(m.group(1))
    depends = [int(x) for x in re.findall(r"(?mi)^Depends-on:\s*#(\d+)", body)]
    rider_of = None
    m = re.search(r"(?mi)^Group:\s*rider of\s*#(\d+)", body)
    if m:
        rider_of = int(m.group(1))
    # Walk the body's "- [ ] / - [x]" checklist once. A line WITH a #N feeds
    # the pickup order (resolved to one issue later; "(Hole #8) (#623)" → #623,
    # the real issue). A line WITHOUT a #N that's still unchecked is PLANNED
    # WORK stated only in prose (e.g. #691's per-module passes, filed lazily at
    # pickup) — captured so an open epic with real remaining intent still shows
    # on the board even before its issues exist.
    order_raw = []
    plan = []
    for line in body.splitlines():
        m = re.match(r"\s*-\s*\[([ xX])\]\s*(.*)", line)
        if not m:
            continue
        nums = [int(x) for x in re.findall(r"#(\d+)", line)]
        if nums:
            order_raw.append(nums)
        elif m.group(1) == " " and m.group(2).strip():
            plan.append(m.group(2).strip())
    return {"parent": parent, "depends": depends, "rider_of": rider_of,
            "checklist_raw": order_raw, "checklist": [], "plan": plan}


def render_list(items, top_epics, epic_children, shipped):
    """--list: the /board display. A table of OPEN work only — epics in rank
    order, their still-to-do issues in pickup order beneath. Done/On-Staging
    items are omitted; fully-drained epics don't appear at all."""
    def members(n):
        ks = {k for k in epic_children(n) if not items[k]["is_epic"]}
        for k in items[n]["checklist"]:
            if k != n and (k not in items or not items[k]["is_epic"]):
                ks.add(k)
        return ks

    def ordered_open(n):
        pos = {num: i for i, num in enumerate(items[n]["checklist"])}
        opens = [k for k in members(n) if k in items and not shipped(k)]
        return sorted(opens, key=lambda k: (pos.get(k, 10_000), k))

    def clean(t):
        return re.sub(r"^Epic:\s*", "", t or "").strip()

    def cell(t):
        return clean(t).replace("|", "\\|")

    def status_of(k):
        st = items[k]["status"] or "—"
        if st == "In Progress" and items[k].get("dev"):
            st += f" · {items[k]['dev']}"
        return st

    # flatten to (epic_item, rows) groups, in rank/walk order. An epic shows
    # while it has remaining work — open filed issues OR unchecked prose plans.
    # Rows are (#-cell, title, status). Recurses into sub-epics.
    groups = []

    def collect(it):
        # Group pickups display as ONE unit: a rider row is folded into its
        # lead's row (`(+ #a #b)`) wherever the rider would have appeared —
        # riders ship with the lead, so a separate row overstates the board.
        # A rider whose lead already shipped (eject/partial) shows standalone.
        rows = []
        for k in ordered_open(it["number"]):
            rid = items[k]["rider_of"]
            if rid is not None and rid in items and not shipped(rid):
                continue
            riders = sorted(m for m, x in items.items()
                            if x["rider_of"] == k and not shipped(m))
            ttl = cell(items[k]["title"])
            if riders:
                ttl += " **(+ " + " ".join(f"#{m}" for m in riders) + ")**"
            rows.append((f"#{k}", ttl, status_of(k)))
        rows += [("—", cell(t), "_planned · not filed_")
                 for t in items[it["number"]].get("plan", [])]
        if rows:
            groups.append((it, rows))
        for sub in sorted((k for k in epic_children(it["number"])
                           if items[k]["is_epic"]
                           and items[k]["status"] not in SHIPPED_STATES),
                          key=lambda k: (items[k]["rank"] or 9999, k)):
            collect(items[sub])

    for it in top_epics:
        if it["status"] in SHIPPED_STATES:
            continue
        collect(it)

    print("## [ priority board ] — open work\n")
    if not groups:
        print("_Nothing open — every epic is drained._")
        return
    print("| epic | # | issue | status |")
    print("|---|---|---|---|")
    for it, rows in groups:
        rank = it["rank"] if it["rank"] is not None else "—"
        label = f"**r{rank} · #{it['number']}** {cell(it['title'])}"
        for i, (num, ttl, st) in enumerate(rows):
            print(f"| {label if i == 0 else ''} | {num} | {ttl} | {st} |")


def render_board_view(items, walk, blocked_epics, busy, free, repo,
                      epic_children, shipped, epic_of, top_epics):
    """--board: the priority-board display. Same graph, second renderer."""
    from datetime import date
    blocked_map = dict(blocked_epics)          # epic -> (blocker, kind)
    unblocks = {}
    for _ep, (blk, kind) in blocked_epics:
        # epic_line() only ever renders EPICS (the `normal` list + recursion
        # over epic children), so an issue key here would never surface. Filter
        # explicitly rather than leave a silently-dead entry for a later reader.
        if kind == "epic":
            unblocks[blk] = unblocks.get(blk, 0) + 1

    def is_container(n):
        return "container" in (items[n]["title"] or "").lower()

    def member_kids(n):
        # Membership = Parent: lines ∪ the epic body's own checklist. Older
        # (pre-backfill) children often lack a Parent: line but always sit in
        # the epic checklist; counting only one source undercounts progress.
        ks = {k for k in epic_children(n) if not items[k]["is_epic"]}
        for k in items[n]["checklist"]:
            if k == n:
                continue
            if k not in items or not items[k]["is_epic"]:
                ks.add(k)
        return ks

    def open_kids(n):
        return [k for k in member_kids(n)
                if k in items
                and items[k]["status"] in PICKABLE_STATES | {"In Progress"}]

    def stats(n):
        kids = member_kids(n)
        return sum(1 for k in kids if shipped(k)), len(kids)

    def bar(done, total, width=10):
        if total == 0:
            return "·" * width
        return "▓" * round(width * done / total) + \
               "░" * (width - round(width * done / total))

    def next_in(n):
        return next((w for w in walk if epic_of(w) == n), None)

    def inprog_in(n):
        return next((k for k in member_kids(n)
                     if k in items and items[k]["status"] == "In Progress"),
                    None)

    TW = 40
    def title(n, width=TW):
        t = re.sub(r"^Epic:\s*", "", items[n]["title"]).strip()
        return (t[:width - 1] + "…") if len(t) > width else t.ljust(width)

    # --- header ---
    print(f"[ board ]  {OWNER}/{PROJECT} · {repo} · {date.today().isoformat()}")
    print("devs   " + " · ".join(
        f"{d} → #{busy[d]['number']}" if d in busy else f"{d} free"
        for d in DEVS))
    if walk:
        t0, ep0 = walk[0], epic_of(walk[0])
        where = f"epic #{ep0} r{items[ep0]['rank']}" if ep0 else "tail"
        print(f"NEXT → #{t0} · {where} · {title(t0, 52).rstrip()}")
    else:
        print("NEXT → (nothing available — see /pickup blocker report)")
    print()

    # --- split epics: interrupt container(s) / normal / trailing containers ---
    live = [it for it in top_epics if it["status"] not in SHIPPED_STATES]
    normal = [it for it in live if not is_container(it["number"])]
    min_normal_rank = min((it["rank"] for it in normal
                           if it["rank"] is not None), default=None)
    interrupt, trailing = [], []
    for it in live:
        if is_container(it["number"]):
            (interrupt if min_normal_rank is not None
             and it["rank"] is not None and it["rank"] < min_normal_rank
             else trailing).append(it)

    # --- interrupt lane: surface items when non-empty, one dim line when not ---
    def container_name(n):
        t = re.sub(r"^Epic:\s*", "", items[n]["title"])
        return t.split("(")[0].strip()

    for it in interrupt:
        n = it["number"]
        kids = open_kids(n)
        if kids:
            print(f"⚡ r{it['rank']}  #{n} {container_name(n)} — {len(kids)} waiting")
            for k in sorted(kids):
                print(f"      · #{k} {title(k, 56).rstrip()}")
        else:
            print(f"⚡ r{it['rank']}  #{n} {container_name(n)} — empty (skipped)")
    print()

    # --- the spine ---
    def epic_line(it, indent=""):
        n = it["number"]
        done, total = stats(n)
        line = (f"{indent} r{str(it['rank'] or '??'):<4}#{n:<5}{title(n)} "
                f"{bar(done, total)} {done:>2}/{total:<3}")
        # The gate marker suppresses only the `next` DISPATCH hint (a gated epic
        # dispatches nothing of its own; anything of its still showing up in the
        # walk got there via another epic's checklist — it still appears in the
        # default view's Queue and in `--list`, but no --board spine line
        # advertises it, since next_in() matches on the NATIVE parent, not
        # walk_via). The other two are STATE FACTS about this epic and must
        # survive the gate: an in-progress child claimed before the gate went
        # live is still in flight, and a drained epic is still closeable —
        # #271 (17/17, gated on a vestigial `Depends-on: #1021`) silently lost
        # its `✔ drained — close?` when #948 made epic→issue edges live, and
        # epic closure is the lifecycle event that re-decides ranks.
        gated = n in blocked_map
        if gated:
            blk, kind = blocked_map[n]
            line += f"  ⛔ waits on {kind} #{blk}"
        ip = inprog_in(n)
        nx = next_in(n)
        if ip:
            who = items[ip]["dev"] or "?"
            line += f"  ▶ #{ip} in progress ({who})"
        elif nx and not gated:
            line += f"  next #{nx}"
        elif total and done == total:
            line += "  ✔ drained — close?"
        if n in unblocks:
            line += f"  ← unblocks {unblocks[n]} epic{'s' if unblocks[n] > 1 else ''}"
        print(line)
        for sub in sorted((k for k in epic_children(n) if items[k]["is_epic"]
                           and items[k]["status"] not in SHIPPED_STATES),
                          key=lambda k: (items[k]["rank"] or 9999, k)):
            epic_line(items[sub], indent + "   ")

    for it in normal:
        epic_line(it)
    print()

    # --- trailing containers, one line ---
    if trailing:
        print("containers   " + "   |   ".join(
            f"#{it['number']} {container_name(it['number']).lower()}"
            f" · {len(open_kids(it['number']))} open" for it in trailing))

    # --- hygiene: creation defects the walk silently punishes ---
    issues = [(n, it) for n, it in items.items() if not it["is_epic"]]
    unranked = [it["number"] for it in live
                if it["rank"] is None and not is_container(it["number"])]
    unstatused = [n for n, it in items.items() if it["status"] is None]
    tail = [n for n, it in issues
            if it["parent"] is None and it["status"] in PICKABLE_STATES]
    notes = []
    if unranked:
        notes.append(f"unranked epics (INVISIBLE to /pickup): "
                     + ", ".join(f"#{x}" for x in unranked))
    if unstatused:
        notes.append(f"{len(unstatused)} board items with no Status")
    if tail:
        shown = ", ".join(f"#{x}" for x in sorted(tail)[:8])
        more = f" +{len(tail) - 8}" if len(tail) > 8 else ""
        notes.append(f"parentless open issues (implicit tail): {shown}{more}")
    if notes:
        print("hygiene   " + " · ".join(notes))


def main():
    # Zero-GraphQL id lookup — reuse the id-map from the last board pull so a
    # mid-cycle mutation of another issue's board fields never re-pulls the board.
    if "--item-id" in sys.argv:
        i = sys.argv.index("--item-id")
        n = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        val = read_idmap().get(str(n))
        if val:
            print(val)
            return
        sys.exit(f"ERROR: no cached item id for #{n}. Run bare `resolve-next.py` "
                 f"once to refresh the id-map, or #{n} isn't on the board.")

    board = load_board()
    repo_url = next((it.get("repository") for it in board if it.get("repository")), None)
    if not repo_url:
        print("ERROR: could not determine repo from board.", file=sys.stderr)
        sys.exit(1)
    repo = "/".join(repo_url.rstrip("/").split("/")[-2:])
    bodies = load_bodies(repo)

    # --- build the item map (issues only; drop PRs/drafts) ---
    items = {}
    for it in board:
        c = it.get("content") or {}
        if c.get("type") != "Issue" or c.get("number") is None:
            continue
        n = c["number"]
        rank = it.get("epic Rank")
        title = c.get("title", "")
        raw_body = (bodies.get(n) or {}).get("body", "")
        conn = parse_body(raw_body)
        items[n] = {
            "number": n,
            # ProjectV2Item id — carried so /pickup Phase 1.4 (In-Progress) and
            # Phase 5.6 (On-Staging) can mutate the item directly instead of
            # re-pulling the whole board just to recover this id. The board pull
            # is the single most expensive GraphQL call in the flow (~400 pts per
            # 100-item page); reusing this id removes 1–2 redundant pulls/pickup.
            "item_id": it.get("id"),
            "title": title,
            "status": it.get("status"),
            "module": it.get("module"),
            "priority": it.get("priority"),
            "rank": rank,
            "dev": it.get("dev"),
            "is_epic": (rank is not None) or title.startswith("Epic:"),
            "fileset": file_tokens(raw_body),
            **conn,
        }

    # resolve each checklist line to a single issue number now that the board
    # is known: prefer the first #N that is a real board issue (skips prose
    # mentions like "Hole #8"), else fall back to the first number on the line.
    for it in items.values():
        it["checklist"] = [next((x for x in nums if x in items), nums[0])
                           for nums in it.get("checklist_raw", [])]

    # Persist every item id from THIS pull so the rest of the cycle reuses them
    # (claim, ship, and any cascade write) without ever re-pulling the board.
    write_idmap(items)

    def shipped(n):
        if n not in items:
            # not on the board: closed issue => shipped; but a still-OPEN
            # off-board issue must NOT count as shipped (fail toward blocked)
            return (bodies.get(n) or {}).get("state") != "OPEN"
        return items[n]["status"] in SHIPPED_STATES

    def epic_dead(n):
        # A closed / board-Done epic routes nothing and claims nothing. Its
        # leftover checklist lines otherwise channel re-homed issues into the
        # walk at the dead epic's old rank position, invisible on every open
        # board view (closed #148 pulled Odds-&-Ends P3 items in at Planning's
        # r20, 2026-07-16).
        return (items[n]["status"] in SHIPPED_STATES
                or (bodies.get(n) or {}).get("state") == "CLOSED")

    def epic_children(epic_n):
        return [n for n, it in items.items() if it["parent"] == epic_n]

    def member_kids(epic_n):
        # Epic membership = Parent: lines ∪ the epic body's own checklist
        # (non-epic, on-board). The WALK must use the same union the /board
        # renderers use — pre-backfill children often lack a Parent: line and
        # would otherwise be walked at the tail instead of inside their epic
        # (and could wrongly unblock epic-level Depends-on).
        ks = set(epic_children(epic_n))
        for k in items[epic_n]["checklist"]:
            if k != epic_n and k in items and not items[k]["is_epic"]:
                ks.add(k)
        return ks

    def epic_blocked(epic_n):
        """epic-level Depends-on. A dep EPIC gates until every one of its items
        has shipped; a dep ISSUE gates until it itself has shipped. Returns
        (dep, kind) or None — kind is decided HERE, where is_epic is known, so
        the three render sites don't each re-derive it.

        The epic branch is an `if`, the issue branch its `elif`: a dep epic is
        consumed by the epic branch whether or not its inner test fires, so the
        two deliberately-deferred facets stay untouched — a ZERO-member dep epic
        still never blocks, and a DEAD (closed/board-Done) dep epic still blocks
        exactly as before. Off-board deps keep today's ignore-entirely behaviour
        (owner call, #948: honouring them would let a board-Done-but-open epic
        wedge every epic behind it shut, since the board query drops Done).
        """
        for dep in items[epic_n]["depends"]:
            if dep in items and items[dep]["is_epic"]:
                kids = member_kids(dep)
                if kids and not all(shipped(k) for k in kids):
                    return (dep, "epic")  # the blocking epic
            elif dep in items:
                if not shipped(dep):
                    return (dep, "issue")  # the blocking issue
        return None

    def available(n):
        it = items[n]
        if it["is_epic"] or it["status"] not in PICKABLE_STATES:
            return False
        if it["rider_of"] is not None:
            return False
        return all(shipped(d) for d in it["depends"])

    def order_children(epic_n, kids):
        checklist = items[epic_n]["checklist"]
        pos = {num: i for i, num in enumerate(checklist)}
        return sorted(kids, key=lambda k: (pos.get(k, 10_000), k))

    walk = []            # flattened available issues, in walk order
    walk_via = {}        # issue -> the epic whose walk position offered it
    blocked_epics = []   # (epic, (blocker, "epic"|"issue"))
    skipped_unranked = []  # live epics with no Epic Rank — invisible, warned

    def gather(epic_n):
        blk = epic_blocked(epic_n)
        if blk is not None:
            blocked_epics.append((epic_n, blk))
            return
        kids = member_kids(epic_n)
        # sub-epics enter in LOCAL RANK order (issue-management.md: rank is the
        # truth for epics; body checklists order only ISSUES). Dead epics are
        # skipped whole; live-but-unranked ones are skipped LOUDLY (documented
        # as invisible — walking them at an arbitrary position hides the defect).
        subs = sorted((k for k in kids if items[k]["is_epic"] and not epic_dead(k)),
                      key=lambda k: (items[k]["rank"] if items[k]["rank"] is not None else 9999, k))
        issues = order_children(epic_n, [k for k in kids if not items[k]["is_epic"]])
        for c in subs:
            if items[c]["rank"] is None:
                skipped_unranked.append(c)
                continue
            gather(c)
        for c in issues:
            if available(c):
                walk.append(c)
                walk_via.setdefault(c, epic_n)

    # top-level epics = epics whose parent is not itself an epic
    def is_top_epic(it):
        return it["is_epic"] and (it["parent"] is None or
                                  it["parent"] not in items or
                                  not items[it["parent"]]["is_epic"])

    top_epics = [it for it in items.values() if is_top_epic(it)]
    top_epics.sort(key=lambda it: (it["rank"] if it["rank"] is not None else 9999,
                                   it["number"]))
    for ep in top_epics:
        n = ep["number"]
        if epic_dead(n):
            continue
        if ep["rank"] is None:
            skipped_unranked.append(n)
            continue
        gather(n)

    # tail: issues claimed by NO epic (safety net), oldest (lowest #) first.
    # "Claimed" = any LIVE epic's member set (Parent line OR checklist), so a
    # checklist-only member of a blocked epic can't leak in through the tail —
    # but a DEAD epic's claims are released (its members fall to the tail if
    # nothing live claims them, instead of vanishing). Live-but-unranked epics
    # DO keep their claims: the defect should scream (see the warning), not leak.
    claimed = set()
    for it in items.values():
        if it["is_epic"] and not epic_dead(it["number"]):
            claimed |= member_kids(it["number"])
    tail = sorted([n for n, it in items.items()
                   if n not in claimed and available(n)])
    for n in tail:
        if n not in walk:
            walk.append(n)

    # --- capacity ---
    # Collision-freedom SHOULD be encoded in the graph at issue-creation time (a
    # Depends-on that serializes file-sharing work, or a Group that co-delivers
    # it). But cross-epic file overlaps are routinely missed at birth (they live
    # only in epic-body prose), so we ALSO emit a read-only file-overlap FLAG
    # below: a candidate that shares a named file with a busy dev's in-flight
    # issue and has no serializing edge. The flag never auto-excludes — the
    # agent confirms the overlap and writes the missing `Depends-on` edge.
    in_prog = [it for it in items.values() if it["status"] == "In Progress"]
    busy = {it["dev"]: it for it in in_prog if it["dev"]}
    free = [d for d in DEVS if d not in busy]

    def collision_flags(n):
        """Read-only: file-surface overlap with a busy dev's in-progress issue
        that no Depends-on edge already serializes. Returns (inprog#, dev,
        [shared files]). A FLAG for the agent to confirm + encode, never an
        auto-exclusion — this is the exact gap that surfaced #114↔#263."""
        out = []
        cand = items[n].get("fileset", set())
        if not cand:
            return out
        for it in in_prog:
            if not it["dev"] or it["number"] == n:
                continue
            if it["number"] in items[n]["depends"]:
                continue  # already serialized by an edge
            shared = cand & it.get("fileset", set())
            if shared:
                out.append((it["number"], it["dev"], sorted(shared)))
        return out

    def epic_of(n):
        p = items[n]["parent"]
        return p if (p in items and items[p]["is_epic"]) else None

    def riders_of(n):
        return sorted([m for m, it in items.items() if it["rider_of"] == n])

    def label(n):
        it = items[n]
        rd = riders_of(n)
        rd_s = f"  (+ riders {', '.join('#'+str(r) for r in rd)})" if rd else ""
        # Show the epic whose WALK POSITION offered this issue (the scheduling
        # truth); note the native home when it differs — a bare native-parent
        # label misattributed a checklist-claimed issue's priority (2026-07-16).
        home = epic_of(n)
        via = walk_via.get(n, home)
        if via is not None:
            ep_s = f"epic #{via} r{items[via]['rank']}"
            if home is not None and home != via:
                ep_s += f" · homed in #{home}"
        else:
            ep_s = "no epic (tail)"
        return f"#{n}  [{ep_s}]  {it['title']}{rd_s}"

    # --- list view (--list): plain ordered epics + issues ---
    if "--list" in sys.argv:
        render_list(items, top_epics, epic_children, shipped)
        return

    # --- board view (--board): same graph, different renderer ---
    if "--board" in sys.argv:
        render_board_view(items, walk, blocked_epics, busy, free, repo,
                          epic_children, shipped, epic_of, top_epics)
        return

    # --- report ---
    print("=" * 72)
    print(f"  /pickup — next target   (board {OWNER}/{PROJECT} · {repo})")
    print("=" * 72)
    print(f"Devs busy: " + (", ".join(f"{d}→#{i['number']}" for d, i in busy.items())
                            if busy else "none"))
    print(f"Free devs: " + (", ".join(free) if free else "NONE — all three busy, STOP"))
    print()
    if skipped_unranked:
        print("⚠ UNRANKED epics skipped (invisible to the walk — assign an Epic "
              "Rank to schedule their work):")
        for n in sorted(set(skipped_unranked)):
            print(f"    #{n}  {items[n]['title']}")
        print()

    if not free:
        print("All devs busy. Per the rules, print who's on what and stop.")
        return

    claim = free[0]
    if not walk:
        print("NOTHING AVAILABLE. Blocker report:")
        for ep, (blk, kind) in blocked_epics:
            print(f"  epic #{ep} blocked by unshipped {kind} #{blk}")
        for n, it in sorted(items.items()):
            if it["status"] in PICKABLE_STATES and not it["is_epic"] \
               and it["rider_of"] is None:
                un = [d for d in it["depends"] if not shipped(d)]
                if un:
                    print(f"  #{n} waits on " + ", ".join(f"#{d}" for d in un))
        return

    # --- reality cross-check: skip anything already in flight off-board ---
    # Walk in order; the first candidate that is NOT being built elsewhere is
    # the target. A branch/worktree naming the issue is a free local signal;
    # only when that's clean do we spend one API call on the claim-comment
    # check (authoritative), so the common case (clean head) costs 1 call.
    branch_blob = git_branch_blob()
    claimed_off = []   # [(n, [reasons])] — board says pickable, reality says taken
    target = None
    for n in walk:
        reasons = []
        if branch_names_issue(branch_blob, n):
            reasons.append("a branch/worktree already exists for it")
        else:
            oc = open_claim(n, repo)
            if oc:
                reasons.append(f"an unreleased pickup claim ({oc})")
        if reasons:
            claimed_off.append((n, reasons))
            continue
        target = n
        break

    if claimed_off:
        print("⚠ CLAIMED OFF-BOARD — skipped (board says pickable, but work is in "
              "flight; the board is stale — reconcile it to In Progress):")
        for n, reasons in claimed_off:
            print(f"    #{n} {items[n]['title'][:60]} — " + "; ".join(reasons))
        print()

    if target is None:
        print("NOTHING AVAILABLE that isn't already in flight. Every pickable "
              "candidate is claimed off-board (see above) — reconcile the board, "
              "or wait for one to ship.")
        return

    off = {n for n, _ in claimed_off}
    print(f"NEXT → {label(target)}")
    print(f"        claim as {claim} (most senior free dev)")
    print(f"        board item id: {items[target]['item_id']}   status: {items[target]['status']}")
    print(f"        ↳ CLAIM THIS FIRST (Phase 1.1): set In-Progress + Dev AND post the")
    print(f"          pickup:claim comment BEFORE reading/branching. Reuse this item id")
    print(f"          for the In-Progress and On-Staging mutations — do NOT re-pull the board.")
    print()
    print(f"This pull is the ONLY board pull this cycle. Every item id was saved:")
    print(f"  · need another issue's board-item id (graduate a dependent, field a")
    print(f"    follow-up)?  →  python3 {os.path.basename(__file__)} --item-id <N>   (no GraphQL)")
    print(f"  · need to know if a specific issue changed?  →  read THAT issue")
    print(f"    (`gh issue view <N>` / `gh api repos/{repo}/issues/<N>`), never re-pull the board.")
    print()
    rest = [n for n in walk if n != target and n not in off]
    if rest:
        print("Queue (then, in order):")
        for n in rest[:5]:
            print(f"  · {label(n)}")
        print()

    # read-only collision flags for the target + queue vs in-flight work
    flag_lines = []
    for n in walk[:6]:
        for inp, dev, shared in collision_flags(n):
            sh = ", ".join(shared[:3]) + ("  …" if len(shared) > 3 else "")
            flag_lines.append(
                f"  ⚠ #{n} shares [{sh}] with In-Progress #{inp} ({dev}) and has NO edge.\n"
                f"      → Confirm the overlap; if real, add 'Depends-on: #{inp} — <shared surface>' "
                f"to #{n} and take the next candidate.")
    if flag_lines:
        print("Collision flags (file overlap vs in-flight work — confirm, then encode):")
        for l in flag_lines:
            print(l)
        print()

    # blocked-but-waiting (useful "why not X" context)
    waiting = []
    for n, it in sorted(items.items()):
        if it["status"] in PICKABLE_STATES and not it["is_epic"] \
           and it["rider_of"] is None:
            un = [d for d in it["depends"] if not shipped(d)]
            if un:
                waiting.append((n, un))
    if waiting or blocked_epics:
        print("Blocked (not yet available):")
        for ep, (blk, kind) in blocked_epics:
            detail = "unshipped items" if kind == "epic" else "unshipped"
            print(f"  · epic #{ep} — waits on {kind} #{blk} ({detail})")
        for n, un in waiting[:8]:
            print(f"  · #{n} — waits on " + ", ".join(f"#{d}" for d in un))


if __name__ == "__main__":
    main()
