"""Handing the record to the agent system.

There are two things happening here and they are not the same, which is the
whole lesson of this file.

    RECORD    write the breach to oncall.breaches. Durable. This is the truth.
    NOTIFY    POST it to the agent service. A doorbell. This is a courtesy.

Do them in that order and a failure to notify costs you latency, not a breach:
the record is on disk, and the agent picks it up on its next sweep. Do them the
other way round, or only notify, and a restart of the agent service at the wrong
second means a breach nobody ever hears about, with no error anywhere.

That is the same argument as writing rows before committing a Kafka offset, and
it comes up every time two systems have to agree on something.
"""
from __future__ import annotations

import os

import httpx

from events.contract import Incident, SignalBreach

from . import correlate, store

AGENT_URL = os.environ.get("AGENT_SERVICE_URL", "http://localhost:8092")
NOTIFY_TIMEOUT = float(os.environ.get("AGENT_NOTIFY_TIMEOUT", "5"))


def emit(breach: SignalBreach, notify: bool = True) -> dict:
    """Record the breach, then ring the doorbell.

    Returns what happened, so the scheduler can log one honest line.
    """
    # 1. deduplicate. The same KPI breaching the same way is the same incident,
    #    and a board on a five minute clock would otherwise open 288
    #    investigations a day for one broken pipeline.
    existing = store.already_open(breach)
    if existing:
        return {"action": "suppressed", "breach_id": existing,
                "why": "the same breach is already open"}

    # 2. record it. Durable before anything else.
    store.record(breach)

    if not notify:
        return {"action": "recorded", "breach_id": breach.breach_id}

    # 3. ring the doorbell. Allowed to fail.
    try:
        r = httpx.post(f"{AGENT_URL}/breach", json=breach.model_dump(mode="json"),
                       timeout=NOTIFY_TIMEOUT)
        r.raise_for_status()
        store.mark(breach.breach_id, "dispatched")
        return {"action": "dispatched", "breach_id": breach.breach_id,
                "agent_said": r.json()}
    except Exception as e:
        # Deliberately not an error. The record is on disk; the agent will find
        # it. Losing the doorbell must never mean losing the breach.
        return {"action": "recorded", "breach_id": breach.breach_id,
                "notify_failed": f"{type(e).__name__}: {e}"}


def emit_incidents(breaches: list[SignalBreach], board_size: int,
                   notify: bool = True) -> list[dict]:
    """Group the breaches from one cycle, then raise one record per incident.

    This is the step that stops six signals becoming six investigations. See
    correlate.py for the rules and the arithmetic behind them.
    """
    fresh: list[SignalBreach] = []
    suppressed: list[dict] = []

    # deduplicate first, so a breach that is already being worked does not drag
    # unrelated signals into a new incident with it
    for b in breaches:
        existing = store.already_open(b)
        if existing:
            suppressed.append({"kpi": b.kpi, "action": "suppressed",
                               "breach_id": existing,
                               "why": "the same breach is already open"})
        else:
            fresh.append(b)

    out = list(suppressed)
    for incident in correlate.group(fresh, board_size):
        for b in incident.breaches:
            store.record(b)
        store.record_incident(incident)
        out.append(_dispatch(incident, notify))
    return out


def _dispatch(incident: Incident, notify: bool) -> dict:
    base = {"incident_id": incident.incident_id,
            "kpi": incident.primary.kpi,
            "signals": incident.signal_count,
            "correlation": incident.correlation}

    if not notify:
        return {**base, "action": "recorded"}

    try:
        r = httpx.post(f"{AGENT_URL}/incident",
                       json=incident.model_dump(mode="json"), timeout=NOTIFY_TIMEOUT)
        r.raise_for_status()
        store.mark_incident(incident.incident_id, "dispatched")
        for b in incident.breaches:
            store.mark(b.breach_id, "dispatched")
        return {**base, "action": "dispatched", "agent_said": r.json()}
    except Exception as e:
        # The incident is on disk. Losing the doorbell must never mean losing it.
        return {**base, "action": "recorded",
                "notify_failed": f"{type(e).__name__}: {e}"}
