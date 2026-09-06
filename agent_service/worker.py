"""The agent service: asleep until a record arrives.

    POST /incident            the doorbell. The signal board rings it
    GET  /investigations      what has been worked, and what came out
    GET  /investigations/{id} one investigation, in full
    POST /investigations/{id}/resume   answer a paused one: approve or reject
    POST /sweep               pick up anything the doorbell missed
    GET  /health              alive, and can it reach a model

Run it:

    uvicorn agent_service.worker:app --port 8092

## Why the doorbell returns immediately

An investigation takes a minute or two: five agents, a dozen tool calls, a
model on the other end of a network. The signal board is a scheduler on a
clock, and a scheduler that blocks for two minutes on one HTTP call is a
scheduler that has stopped being a clock.

So the endpoint accepts the record, starts the work on a background thread and
returns `202 Accepted` at once. The board carries on.

## Why there is a sweep as well

Because the doorbell is allowed to fail. The breach is written to
`oncall.breaches` before anybody is notified, so a restart at the wrong second
costs latency rather than a lost incident. `POST /sweep` picks up anything left
open, and in production it runs on a slow timer as a backstop.

That pairing, durable record plus best effort notification, is the same shape
as writing rows before committing a Kafka offset, and it comes up every time
two systems have to agree on something.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import traceback

import psycopg
from fastapi import BackgroundTasks, FastAPI, HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from events.contract import Incident
from pipelines.lib.config import dsn
from signal_service import store

from .supervisor import investigate, resume
from .tools.publish import SCHEMA, setup as artifacts_setup

app = FastAPI(
    title="NIGHTSHIFT on call agent",
    version="1.0",
    description="Five agents. Asleep until a signal breaches. Changes nothing.",
)

# One saver per process, so a paused investigation can be resumed by a later
# HTTP call. In production this is a database backed checkpointer; in a class it
# is memory, and the tradeoff is worth saying out loud: restart the service and
# every paused investigation is forgotten.
CHECKPOINTER = InMemorySaver()

# ── the worker pool ────────────────────────────────────────────────────────
#
# Investigations are expensive: five agents, a dozen or so model calls, a minute
# or two of wall clock each. Left unbounded, six incidents at once means six
# concurrent investigations, six times the spend, and six processes competing
# for the same database connections.
#
# So they queue. MAX_CONCURRENT of them run; the rest wait their turn. A bounded
# queue is the difference between a service under load and a service that takes
# the estate down with it.
MAX_CONCURRENT = int(os.environ.get("ONCALL_MAX_CONCURRENT", "2"))
QUEUE_LIMIT = int(os.environ.get("ONCALL_QUEUE_LIMIT", "50"))

_slots = threading.Semaphore(MAX_CONCURRENT)
_running: dict[str, str] = {}
_queued: list[str] = []
_lock = threading.Lock()

RUNS_DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.investigations (
    breach_id   TEXT PRIMARY KEY,
    kpi         TEXT NOT NULL,
    incident_id TEXT,
    signals     INT NOT NULL DEFAULT 1,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'running',
                -- running, done, waiting_for_human, failed
    steps       TEXT,
    handover    TEXT,
    error       TEXT
);

-- CREATE TABLE IF NOT EXISTS does nothing when the table already exists, so a
-- new column needs saying out loud. Without this the service starts cleanly and
-- then fails on the first insert, which is the worst of both worlds.
ALTER TABLE {SCHEMA}.investigations ADD COLUMN IF NOT EXISTS incident_id TEXT;
ALTER TABLE {SCHEMA}.investigations ADD COLUMN IF NOT EXISTS signals INT NOT NULL DEFAULT 1;
"""


@app.on_event("startup")
def _startup() -> None:
    try:
        store.setup()
        artifacts_setup()
        with psycopg.connect(dsn(), autocommit=True) as c:
            c.execute(RUNS_DDL)
    except Exception as e:                          # noqa: BLE001
        print(f"  could not prepare the oncall schema: {type(e).__name__}: {e}")


# ── running one investigation ──────────────────────────────────────────────

def _record_start(incident: Incident) -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.investigations
                      (breach_id, kpi, incident_id, signals, status)
                      VALUES (%s, %s, %s, %s, 'running')
                      ON CONFLICT (breach_id) DO UPDATE
                      SET status = 'running', started_at = now(),
                          ended_at = NULL, error = NULL""",
                  (incident.incident_id, incident.primary.kpi,
                   incident.incident_id, incident.signal_count))


def _record_end(breach_id: str, status: str, steps: str = "",
                handover: str = "", error: str = "") -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""UPDATE {SCHEMA}.investigations
                      SET status = %s, ended_at = now(), steps = %s,
                          handover = %s, error = %s
                      WHERE breach_id = %s""",
                  (status, steps, handover, error or None, breach_id))


def run_investigation(incident: Incident) -> None:
    """The work. Runs on a pool thread, waits for a slot, and never raises."""
    key = incident.incident_id
    with _lock:
        if key in _running:
            return
        _queued.append(key)

    # Wait for a slot. Queueing rather than refusing means a burst of incidents
    # is worked slowly instead of being dropped, which is what you want at 3am.
    _slots.acquire()
    with _lock:
        if key in _queued:
            _queued.remove(key)
        _running[key] = "running"

    try:
        # inside the try, so a failure here still releases the slot and still
        # leaves a row saying the attempt happened
        _record_start(incident)
        out = investigate(incident, checkpointer=CHECKPOINTER)
        status = "waiting_for_human" if out["waiting_for_human"] else "done"
        _record_end(key, status,
                    steps=" -> ".join(s["tool"] for s in out["steps"]),
                    handover=out["handover"])
        store.mark_incident(key, "diagnosed" if status == "done" else "dispatched",
                            outcome=out["handover"][:500])
        for b in incident.breaches:
            store.mark(b.breach_id, "diagnosed", outcome=out["handover"][:300])
    except Exception as e:                          # noqa: BLE001
        # An investigation that fails must say so loudly. The alternative is an
        # incident that looks handled and was not, which is worse than no agent.
        detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        print(f"  investigation {key} FAILED: {detail}")
        # recording the failure can itself fail. Say so on the way out rather
        # than replacing one exception with another and losing both.
        try:
            _record_end(key, "failed", error=detail)
            store.mark_incident(key, "failed", outcome=str(e)[:500])
        except Exception as inner:                  # noqa: BLE001
            print(f"  and the failure could not be recorded: {inner}")
    finally:
        with _lock:
            _running.pop(key, None)
        _slots.release()


# ── the endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "model": os.environ.get("ONCALL_MODEL", "openai:gpt-5.4-mini"),
        "model_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "running": list(_running),
        "queued": len(_queued),
        "max_concurrent": MAX_CONCURRENT,
        "at": dt.datetime.now(dt.timezone.utc),
    }


@app.post("/incident", status_code=202)
def receive(incident: Incident, background: BackgroundTasks) -> dict:
    """The doorbell. Accepts the incident and returns at once.

    One incident may carry several signals that moved for one reason. The board
    grouped them; this service works them as one investigation.
    """
    with _lock:
        if incident.incident_id in _running:
            return {"accepted": False, "why": "already being investigated",
                    "incident_id": incident.incident_id}
        if len(_queued) >= QUEUE_LIMIT:
            # Saying no is better than accepting work that will never be done.
            raise HTTPException(503, f"queue is full ({QUEUE_LIMIT}). The record "
                                     f"is on disk; the sweep will pick it up.")

    background.add_task(run_investigation, incident)
    return {"accepted": True,
            "incident_id": incident.incident_id,
            "signals": incident.signal_count,
            "queued_ahead": len(_queued),
            "note": "investigating in the background. Poll /investigations/{id}."}


@app.post("/sweep")
def sweep(limit: int = 5) -> dict:
    """Pick up open incidents nobody has worked. The backstop for a lost doorbell."""
    picked = []
    for row in store.open_incidents(50):
        if row["status"] not in ("open", "dispatched"):
            continue
        incident = store.load_incident(row["incident_id"])
        if incident is None or incident.incident_id in _running:
            continue
        threading.Thread(target=run_investigation, args=(incident,), daemon=True).start()
        picked.append(incident.incident_id)
        if len(picked) >= limit:
            break
    return {"picked_up": picked}


@app.get("/investigations")
def investigations(limit: int = 25) -> dict:
    with psycopg.connect(dsn()) as c:
        rows = c.execute(f"""SELECT breach_id, kpi, status, started_at, ended_at,
                                    steps, left(coalesce(handover, ''), 300)
                             FROM {SCHEMA}.investigations
                             ORDER BY started_at DESC LIMIT %s""", (limit,)).fetchall()
    keys = ("breach_id", "kpi", "status", "started_at", "ended_at", "steps", "handover")
    return {"investigations": [dict(zip(keys, r)) for r in rows]}


@app.get("/investigations/{breach_id}")
def one_investigation(breach_id: str) -> dict:
    with psycopg.connect(dsn()) as c:
        row = c.execute(f"""SELECT breach_id, kpi, status, started_at, ended_at,
                                   steps, handover, error, incident_id, signals
                            FROM {SCHEMA}.investigations WHERE breach_id = %s""",
                        (breach_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"no investigation for {breach_id!r}")
    keys = ("breach_id", "kpi", "status", "started_at", "ended_at",
            "steps", "handover", "error", "incident_id", "signals")
    out = dict(zip(keys, row))

    # An agent may label an artifact with the incident id or with any of the
    # breach ids inside it, and both are reasonable. Look for either, or the
    # page it definitely wrote appears to be missing.
    ids = [breach_id]
    incident = store.load_incident(breach_id)
    if incident is not None:
        ids += [b.breach_id for b in incident.breaches]
        out["grouped_signals"] = [b.kpi for b in incident.breaches]
        out["correlation"] = incident.correlation

    with psycopg.connect(dsn()) as c:
        out["pages"] = [dict(zip(("page_id", "title", "url"), r)) for r in c.execute(
            f"SELECT page_id, title, url FROM {SCHEMA}.pages WHERE breach_id = ANY(%s)",
            (ids,)).fetchall()]
        out["tickets"] = [dict(zip(("ticket_id", "kind", "severity", "title"), r))
                          for r in c.execute(
            f"""SELECT ticket_id, kind, severity, title FROM {SCHEMA}.tickets
                WHERE breach_id = ANY(%s)""", (ids,)).fetchall()]
        out["change_requests"] = [dict(zip(("request_id", "kind", "status", "summary",
                                            "branch", "pr_url"), r)) for r in c.execute(
            f"""SELECT request_id, kind, status, summary, branch, pr_url
                FROM {SCHEMA}.change_requests WHERE breach_id = ANY(%s)""",
            (ids,)).fetchall()]
    return out


class Decision(BaseModel):
    approve: bool
    note: str = ""


@app.post("/investigations/{breach_id}/resume")
def resume_investigation(breach_id: str, decision: Decision) -> dict:
    """Answer a paused investigation.

    Rejecting is a real outcome, and the note goes back to the agent. That is
    the difference between a human gate and a rubber stamp.
    """
    incident = store.load_incident(breach_id)
    if incident is None:
        raise HTTPException(404, f"no incident called {breach_id!r}")

    out = resume(breach_id, incident, decision.approve, decision.note,
                 checkpointer=CHECKPOINTER)
    _record_end(breach_id, "done",
                steps=" -> ".join(s["tool"] for s in out["steps"]),
                handover=out["handover"])
    return out
