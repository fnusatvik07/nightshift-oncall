"""What the agent is allowed to produce.

The agent never changes a number. Everything it does ends up as one of four
artifacts, and every one of them is something a person reads and decides on.

    write_spec           a page: what happened, what it means, what to do.
                         ALWAYS produced, even when nothing else is.

    raise_ticket         a tracked item with an owner and a severity.

    propose_code_change  a branch, a commit and a pull request. Never a push
                         to main, never a merge. The PR review is the gate.

    request_db_change    anything that would touch data. This one stops and
                         waits for a human before it does anything at all.

## Why a spec is always produced

Because the most common outcome of an investigation is not a fix. It is a
diagnosis, some evidence, and a decision that belongs to somebody who was
asleep. A system that only produces output when it is confident produces
nothing on the nights you needed it most.

## The Confluence seam

`Publisher` is an interface with two implementations. `LocalPublisher` writes
markdown into `artifacts/` and a row into Postgres, and works for everybody with
no credentials. `ConfluencePublisher` posts to the real REST API and turns on by
itself when the environment holds a base URL, a space and a token.

Swapping one for the other changes no agent code, which is the entire reason
the interface exists.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import re
import threading
import uuid

import psycopg
from langchain.tools import tool

from pipelines.lib.config import dsn

from . import repo

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
SCHEMA = "oncall"

# The only directories a proposed code change may touch. A remediation agent
# that can edit the tests which judge it is not being judged.
WRITABLE = ("pipelines", "signal_service", "signals")

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};

CREATE TABLE IF NOT EXISTS {SCHEMA}.pages (
    page_id    TEXT PRIMARY KEY,
    breach_id  TEXT,
    title      TEXT NOT NULL,
    owner      TEXT,
    body       TEXT NOT NULL,
    url        TEXT,
    published  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {SCHEMA}.tickets (
    ticket_id  TEXT PRIMARY KEY,
    breach_id  TEXT,
    title      TEXT NOT NULL,
    owner      TEXT NOT NULL,
    severity   TEXT NOT NULL,
    kind       TEXT NOT NULL,           -- investigate, code_change, db_change
    body       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open',
    page_id    TEXT,
    raised_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {SCHEMA}.change_requests (
    request_id TEXT PRIMARY KEY,
    breach_id  TEXT,
    kind       TEXT NOT NULL,           -- code, database
    summary    TEXT NOT NULL,
    detail     TEXT NOT NULL,
    branch     TEXT,
    pr_url     TEXT,
    status     TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


_ready = False
_setup_lock = threading.Lock()


def setup() -> None:
    """Create the artifact tables. Safe to call from several threads at once.

    LangGraph runs tool calls in parallel, so two tools can arrive here in the
    same millisecond. CREATE TABLE IF NOT EXISTS is not as safe as it reads:
    two concurrent transactions both see the table missing, both create it, and
    one loses with a duplicate key on a system catalogue.

    So: do it once per process, hold a lock while doing it, and treat losing
    the race as success, because losing means somebody else created the table.
    """
    global _ready
    if _ready:
        return
    with _setup_lock:
        if _ready:
            return
        ARTIFACTS.mkdir(exist_ok=True)
        (ARTIFACTS / "pages").mkdir(exist_ok=True)
        (ARTIFACTS / "patches").mkdir(exist_ok=True)
        try:
            with psycopg.connect(dsn(), autocommit=True) as c:
                c.execute(DDL)
        except psycopg.errors.UniqueViolation:
            pass                    # another process got there first. Fine.
        _ready = True


# ═══════════════════════════════════════════════════════════════════════════
# The publisher seam
# ═══════════════════════════════════════════════════════════════════════════

class Publisher:
    """Somewhere a page can be published. One method."""

    name = "none"

    def publish(self, page_id: str, title: str, body: str) -> str:
        raise NotImplementedError


class LocalPublisher(Publisher):
    """Markdown on disk, and a row in Postgres. No credentials, works anywhere."""

    name = "local"

    def publish(self, page_id: str, title: str, body: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        path = ARTIFACTS / "pages" / f"{page_id}-{slug}.md"
        path.write_text(body)
        return f"file://{path}"


class ConfluencePublisher(Publisher):
    """The real thing, when the environment has credentials for it.

    Turns itself on when CONFLUENCE_BASE_URL, CONFLUENCE_SPACE and
    CONFLUENCE_TOKEN are all set. Nothing else in the project changes.
    """

    name = "confluence"

    def __init__(self) -> None:
        self.base = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
        self.space = os.environ["CONFLUENCE_SPACE"]
        self.token = os.environ["CONFLUENCE_TOKEN"]
        self.user = os.environ.get("CONFLUENCE_USER", "")

    def publish(self, page_id: str, title: str, body: str) -> str:
        import httpx

        payload = {
            "type": "page",
            "title": f"{title} [{page_id}]",
            "space": {"key": self.space},
            "body": {"storage": {"value": _markdown_to_storage(body),
                                 "representation": "storage"}},
        }
        auth = (self.user, self.token) if self.user else None
        headers = {} if auth else {"Authorization": f"Bearer {self.token}"}
        r = httpx.post(f"{self.base}/rest/api/content", json=payload,
                       auth=auth, headers=headers, timeout=30)
        r.raise_for_status()
        return f"{self.base}/pages/viewpage.action?pageId={r.json()['id']}"


def _markdown_to_storage(md: str) -> str:
    """Confluence storage format is XHTML. This is the smallest honest bridge."""
    return "<ac:structured-macro ac:name=\"markdown\"><ac:plain-text-body>" \
           f"<![CDATA[{md}]]></ac:plain-text-body></ac:structured-macro>"


def publisher() -> Publisher:
    needed = ("CONFLUENCE_BASE_URL", "CONFLUENCE_SPACE", "CONFLUENCE_TOKEN")
    if all(os.environ.get(k) for k in needed):
        try:
            return ConfluencePublisher()
        except Exception as e:                      # noqa: BLE001
            print(f"  confluence configured but unusable, falling back: {e}")
    return LocalPublisher()


# ═══════════════════════════════════════════════════════════════════════════
# The tools
# ═══════════════════════════════════════════════════════════════════════════

@tool
def write_spec(title: str, breach_id: str, owner: str, what_happened: str,
               evidence: str, what_it_means: str, what_to_do: str,
               confidence: str = "medium") -> str:
    """Publish the diagnosis page. Always do this, even if you found nothing.

    Write it for the owner, who was asleep and has never seen this code.

    title          one line a person can scan in a list
    breach_id      the breach this is about
    owner          the team this belongs to
    what_happened  the number, its normal value, and when it moved
    evidence       what you actually ran and what came back. Be specific
    what_it_means  the consequence in business terms, not in table names
    what_to_do     the recommendation, as steps somebody could follow
    confidence     high, medium or low, and say why in what_it_means
    """
    setup()
    page_id = f"PAGE-{uuid.uuid4().hex[:8].upper()}"
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = f"""# {title}

|  |  |
|---|---|
| **Breach** | `{breach_id}` |
| **Owner** | {owner} |
| **Raised** | {now} |
| **Confidence** | {confidence} |
| **Written by** | the NIGHTSHIFT on call agent |

> This page was written automatically from a signal breach. Nothing in the
> warehouse was changed to produce it. Every number below came from a read only
> query, and the queries are quoted so you can run them yourself.

## What happened

{what_happened}

## Evidence

{evidence}

## What it means

{what_it_means}

## What to do

{what_to_do}

---

*If this diagnosis is wrong, the fastest fix is usually the KPI definition
rather than the pipeline. Both live in this repository.*
"""
    pub = publisher()
    try:
        url = pub.publish(page_id, title, body)
    except Exception as e:                          # noqa: BLE001
        url = ""
        body += f"\n\n<!-- publish to {pub.name} failed: {e} -->"

    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.pages
                      (page_id, breach_id, title, owner, body, url)
                      VALUES (%s, %s, %s, %s, %s, %s)""",
                  (page_id, breach_id, title, owner, body, url))

    return (f"published {page_id} to {pub.name}\n"
            f"{url or '(stored in oncall.pages only)'}")


@tool
def raise_ticket(title: str, breach_id: str, owner: str, severity: str,
                 kind: str, body: str, page_id: str = "") -> str:
    """Raise a tracked item somebody has to close.

    kind must be one of:
      investigate   a human needs to look, no change is proposed yet
      code_change   a code fix is proposed, see the pull request
      db_change     data would have to change, and that needs approval

    severity must be one of: low, medium, high, critical.
    """
    setup()
    if kind not in ("investigate", "code_change", "db_change"):
        return f"REFUSED: kind must be investigate, code_change or db_change, not {kind!r}"
    if severity not in ("low", "medium", "high", "critical"):
        return f"REFUSED: severity must be low, medium, high or critical, not {severity!r}"

    ticket_id = f"NS-{uuid.uuid4().hex[:6].upper()}"
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.tickets
                      (ticket_id, breach_id, title, owner, severity, kind, body, page_id)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                  (ticket_id, breach_id, title, owner, severity, kind, body,
                   page_id or None))
    return f"raised {ticket_id} for {owner} ({severity}, {kind})"


# ── code changes: an isolated branch, and a pull request ───────────────────

@tool
def propose_code_change(breach_id: str, summary: str, rationale: str,
                        path: str, old_string: str, new_string: str) -> str:
    """Open a pull request containing one small code change. It is never merged.

    Give the exact text to replace. The edit is applied on a branch in an
    ISOLATED checkout, the result is checked for syntax, and a pull request is
    opened if the repository has a remote.

    Nothing on the main branch changes. Nothing in anybody's working tree
    changes. Nothing in the database changes. If the change does not parse, it
    is thrown away and you are told why.

    Returns the branch, the pull request URL if one was opened, and the diff.
    Put the diff on the incident page: a reviewer who cannot see the change
    cannot review it.

    path must be inside: pipelines/, signal_service/, signals/, agent_service/
    """
    setup()
    result = repo.propose(breach_id, summary, rationale, path,
                          old_string, new_string, ARTIFACTS / "patches")

    if not result.ok:
        return result.reason

    request_id = f"CR-{uuid.uuid4().hex[:6].upper()}"
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.change_requests
                      (request_id, breach_id, kind, summary, detail, branch, pr_url)
                      VALUES (%s, %s, 'code', %s, %s, %s, %s)""",
                  (request_id, breach_id, summary,
                   f"{rationale}\n\n{result.diff}", result.branch,
                   result.pr_url or None))

    return (f"{request_id}: {result.summary()}\n\n"
            f"THE DIFF, which belongs on the incident page:\n{result.diff}")


# ── database changes: this one stops and asks ──────────────────────────────

@tool
def request_db_change(breach_id: str, summary: str, rationale: str,
                      statement: str, rows_affected_estimate: str,
                      reversible: str) -> str:
    """Ask a human to approve a change to data. Nothing is executed here, ever.

    This tool records a request and raises a ticket. It does not run the
    statement, and no part of this system will run it: a person does that, by
    hand, having read it.

    statement                the exact SQL, so it can be reviewed and run as is
    rows_affected_estimate   how many rows, and how you worked that out
    reversible               how to undo it, or say plainly that you cannot
    """
    setup()
    request_id = f"CR-{uuid.uuid4().hex[:6].upper()}"
    detail = (f"{rationale}\n\n"
              f"PROPOSED STATEMENT\n{statement}\n\n"
              f"ESTIMATED ROWS AFFECTED\n{rows_affected_estimate}\n\n"
              f"HOW TO REVERSE IT\n{reversible}")

    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.change_requests
                      (request_id, breach_id, kind, summary, detail, status)
                      VALUES (%s, %s, 'database', %s, %s, 'awaiting_human')""",
                  (request_id, breach_id, summary, detail))
        c.execute(f"""INSERT INTO {SCHEMA}.tickets
                      (ticket_id, breach_id, title, owner, severity, kind, body)
                      VALUES (%s, %s, %s, 'data-platform', 'high', 'db_change', %s)""",
                  (f"NS-{uuid.uuid4().hex[:6].upper()}", breach_id,
                   f"Approve data change: {summary}", detail))

    return (f"{request_id} recorded and WAITING FOR A HUMAN.\n"
            f"Nothing was executed. A person must run this by hand:\n\n{statement}")


PUBLISH_TOOLS = [write_spec, raise_ticket, propose_code_change, request_db_change]

# The tools that need a person to say yes before they run at all. A database
# change is gated here; a code change is gated by the pull request review,
# which is a human step by construction.
GATED = {"request_db_change": True}
