"""The agent service: asleep until a record arrives.

    POST /breach              the doorbell. The signal board rings it
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

from events.contract import SignalBreach
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

# investigations currently running, so the same breach is never worked twice
_running: dict[str, str] = {}
_lock = threading.Lock()

RUNS_DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.investigations (
    breach_id   TEXT PRIMARY KEY,
    kpi         TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'running',
                -- running, done, waiting_for_human, failed
    steps       TEXT,
    handover    TEXT,
    error       TEXT
);
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

def _record_start(breach: SignalBreach) -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.investigations (breach_id, kpi, status)
                      VALUES (%s, %s, 'running')
                      ON CONFLICT (breach_id) DO UPDATE
                      SET status = 'running', started_at = now(),
                          ended_at = NULL, error = NULL""",
                  (breach.breach_id, breach.kpi))


def _record_end(breach_id: str, status: str, steps: str = "",
                handover: str = "", error: str = "") -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""UPDATE {SCHEMA}.investigations
                      SET status = %s, ended_at = now(), steps = %s,
                          handover = %s, error = %s
                      WHERE breach_id = %s""",
                  (status, steps, handover, error or None, breach_id))


def run_investigation(breach: SignalBreach) -> None:
    """The work. Runs on a background thread, and is not allowed to raise."""
    with _lock:
        if breach.breach_id in _running:
            return
        _running[breach.breach_id] = "running"

    _record_start(breach)
    try:
        out = investigate(breach, checkpointer=CHECKPOINTER)
        status = "waiting_for_human" if out["waiting_for_human"] else "done"
        _record_end(breach.breach_id, status,
                    steps=" -> ".join(s["tool"] for s in out["steps"]),
                    handover=out["handover"])
        store.mark(breach.breach_id,
                   "diagnosed" if status == "done" else "dispatched",
                   outcome=out["handover"][:500])
    except Exception as e:                          # noqa: BLE001
        # An investigation that fails must say so loudly. The alternative is a
        # breach that looks handled and was not, which is worse than no agent.
        detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        _record_end(breach.breach_id, "failed", error=detail)
        store.mark(breach.breach_id, "failed", outcome=str(e)[:500])
        print(f"  investigation {breach.breach_id} failed: {e}")
    finally:
        with _lock:
            _running.pop(breach.breach_id, None)


# ── the endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "model": os.environ.get("ONCALL_MODEL", "openai:gpt-5.4-mini"),
        "model_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "running": list(_running),
        "at": dt.datetime.now(dt.timezone.utc),
    }


@app.post("/breach", status_code=202)
def receive(breach: SignalBreach, background: BackgroundTasks) -> dict:
    """The doorbell. Accepts the record and returns at once."""
    with _lock:
        if breach.breach_id in _running:
            return {"accepted": False, "why": "already being investigated",
                    "breach_id": breach.breach_id}

    background.add_task(run_investigation, breach)
    return {"accepted": True, "breach_id": breach.breach_id,
            "note": "investigating in the background. Poll /investigations/{id}."}


@app.post("/sweep")
def sweep(limit: int = 5) -> dict:
    """Pick up open breaches nobody has worked. The backstop for a lost doorbell."""
    picked = []
    for row in store.open_breaches(50):
        if row["status"] not in ("open", "dispatched"):
            continue
        breach = store.load(row["breach_id"])
        if breach is None or breach.breach_id in _running:
            continue
        threading.Thread(target=run_investigation, args=(breach,), daemon=True).start()
        picked.append(breach.breach_id)
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
                                   steps, handover, error
                            FROM {SCHEMA}.investigations WHERE breach_id = %s""",
                        (breach_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"no investigation for {breach_id!r}")
    keys = ("breach_id", "kpi", "status", "started_at", "ended_at",
            "steps", "handover", "error")
    out = dict(zip(keys, row))

    with psycopg.connect(dsn()) as c:
        out["pages"] = [dict(zip(("page_id", "title", "url"), r)) for r in c.execute(
            f"SELECT page_id, title, url FROM {SCHEMA}.pages WHERE breach_id = %s",
            (breach_id,)).fetchall()]
        out["tickets"] = [dict(zip(("ticket_id", "kind", "severity", "title"), r))
                          for r in c.execute(
            f"""SELECT ticket_id, kind, severity, title FROM {SCHEMA}.tickets
                WHERE breach_id = %s""", (breach_id,)).fetchall()]
        out["change_requests"] = [dict(zip(("request_id", "kind", "status", "summary",
                                            "branch", "pr_url"), r)) for r in c.execute(
            f"""SELECT request_id, kind, status, summary, branch, pr_url
                FROM {SCHEMA}.change_requests WHERE breach_id = %s""",
            (breach_id,)).fetchall()]
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
    breach = store.load(breach_id)
    if breach is None:
        raise HTTPException(404, f"no breach called {breach_id!r}")

    out = resume(breach_id, breach, decision.approve, decision.note,
                 checkpointer=CHECKPOINTER)
    _record_end(breach_id, "done",
                steps=" -> ".join(s["tool"] for s in out["steps"]),
                handover=out["handover"])
    return out
