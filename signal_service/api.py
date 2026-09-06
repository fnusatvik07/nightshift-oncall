"""The Signal API.

An HTTP surface over the catalogue, so that anything can ask what the numbers
are without importing python or knowing which database they live in.

    GET  /health                  is the service alive, and can it see the warehouse
    GET  /kpis                    the catalogue: what is watched, by whom
    GET  /kpis/{name}             one KPI, with its definition and its query
    GET  /signals                 evaluate everything, right now
    GET  /signals/{name}          evaluate one
    GET  /signals/{name}/history  what that number has been doing
    POST /evaluate                evaluate, record breaches, notify the agent
    GET  /breaches                what has breached, and what happened next
    GET  /breaches/{id}           one breach, in full

Two design notes worth saying out loud in class.

**GET never has a side effect.** `/signals` measures and tells you. It records
nothing and wakes nobody. `POST /evaluate` is the one that can start an
investigation. A dashboard refreshing every ten seconds must not be able to
page somebody.

**The API does not hold state.** Every answer is computed from the warehouse
and the oncall schema. Restart it mid sentence and nothing is lost, which is
what lets you deploy it during the day.

Run it:

    uvicorn signal_service.api:app --port 8091 --reload
"""
from __future__ import annotations

import datetime as dt

from fastapi import FastAPI, HTTPException

from . import evaluate as ev
from . import store
from .emit import emit
from .kpis import BY_NAME, CATALOGUE, get

app = FastAPI(
    title="NIGHTSHIFT Signal API",
    version="1.0",
    description="Thirteen KPIs, their baselines, and the breaches they produce.",
)


@app.on_event("startup")
def _startup() -> None:
    # The service creates its own schema on boot. A service that requires a
    # human to have run a migration first is a service that will not come back
    # up at 3am.
    try:
        store.setup()
    except Exception as e:                      # noqa: BLE001
        print(f"  could not create the oncall schema: {type(e).__name__}: {e}")


# ── is it alive ────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    """Alive is not the same as working, so this checks both."""
    kpi = CATALOGUE[0]
    reading = ev.read(kpi)
    return {
        "ok": reading.measured,
        "kpis": len(CATALOGUE),
        "warehouse": "reachable" if reading.measured else reading.error,
        "at": dt.datetime.now(dt.timezone.utc),
    }


# ── the catalogue ──────────────────────────────────────────────────────────

@app.get("/kpis")
def list_kpis() -> list[dict]:
    return [{
        "name": k.name,
        "title": k.title,
        "owner": k.owner,
        "watches": k.watches,
        "unit": k.unit,
        "judgement": k.judgement,
        "baseline": k.baseline,
        "tolerance": k.tolerance,
        "severity": k.severity,
        "tags": list(k.tags),
    } for k in CATALOGUE]


@app.get("/kpis/{name}")
def one_kpi(name: str) -> dict:
    if name not in BY_NAME:
        raise HTTPException(404, f"no KPI called {name!r}")
    k = get(name)
    return {
        "name": k.name, "title": k.title, "owner": k.owner, "watches": k.watches,
        "means": k.means, "unit": k.unit, "judgement": k.judgement,
        "baseline": k.baseline, "tolerance": k.tolerance,
        "z_threshold": k.z_threshold, "severity": k.severity,
        "watch_direction": k.watch_direction, "tags": list(k.tags),
        # the query is not a secret. Anybody arguing with the number deserves
        # to see exactly how it was produced.
        "sql": " ".join(k.sql.split()),
        "history_sql": " ".join(k.history_sql.split()) or None,
    }


# ── measuring, without side effects ────────────────────────────────────────

def _row(kpi, reading, verdict) -> dict:
    return {
        "kpi": kpi.name,
        "title": kpi.title,
        "owner": kpi.owner,
        "value": verdict.value,
        "baseline": verdict.baseline,
        "unit": kpi.unit,
        "breached": verdict.breached,
        "direction": verdict.direction,
        "deviation": round(verdict.deviation, 4),
        "z_score": verdict.z_score,
        "severity": kpi.severity,
        "detail": verdict.detail,
        "measured": reading.measured,
        "error": reading.error,
        "at": reading.at,
    }


@app.get("/signals")
def signals() -> dict:
    rows = [_row(*t) for t in ev.evaluate_all()]
    return {
        "at": dt.datetime.now(dt.timezone.utc),
        "total": len(rows),
        "breached": sum(1 for r in rows if r["breached"]),
        "unmeasured": sum(1 for r in rows if not r["measured"]),
        "signals": rows,
    }


@app.get("/signals/{name}")
def one_signal(name: str) -> dict:
    if name not in BY_NAME:
        raise HTTPException(404, f"no KPI called {name!r}")
    kpi = get(name)
    reading, verdict = ev.evaluate(kpi)
    return _row(kpi, reading, verdict)


@app.get("/signals/{name}/history")
def signal_history(name: str, limit: int = 50) -> dict:
    if name not in BY_NAME:
        raise HTTPException(404, f"no KPI called {name!r}")
    return {"kpi": name, "readings": store.recent_readings(name, limit)}


# ── measuring, with side effects ───────────────────────────────────────────

@app.post("/evaluate")
def run_evaluation(notify: bool = True) -> dict:
    """Measure everything, keep the readings, and raise anything that breached.

    This is the one endpoint that can wake somebody, which is why it is a POST
    and why the scheduler is the only thing that normally calls it.
    """
    results = ev.evaluate_all()

    store.save_readings([
        (k.name, v.value, r.error, v.breached, v.baseline, v.z_score)
        for k, r, v in results
    ])

    emitted = []
    for kpi, reading, verdict in results:
        if verdict.breached:
            breach = ev.to_breach(kpi, reading, verdict)
            emitted.append({"kpi": kpi.name, **emit(breach, notify=notify)})

    return {
        "at": dt.datetime.now(dt.timezone.utc),
        "evaluated": len(results),
        "breached": len(emitted),
        "emitted": emitted,
    }


# ── what has breached ──────────────────────────────────────────────────────

@app.get("/breaches")
def breaches(limit: int = 50) -> dict:
    return {"breaches": store.open_breaches(limit)}


@app.get("/breaches/{breach_id}")
def one_breach(breach_id: str) -> dict:
    b = store.load(breach_id)
    if b is None:
        raise HTTPException(404, f"no breach called {breach_id!r}")
    return b.model_dump(mode="json")
