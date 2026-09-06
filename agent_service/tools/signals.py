"""Tools for looking at the board itself.

The agents reach the signal service over HTTP, exactly as any other client
would, rather than importing its code. That is not ceremony: it means the two
services can be deployed separately, restarted separately, and written in
different languages later, and it means the agent cannot accidentally reach
past the API into the signal service's own tables.

If the API is unreachable these fall back to evaluating in process, because an
investigation that fails because a sidecar is down is not much of an
investigation.
"""
from __future__ import annotations

import os

import httpx
from langchain.tools import tool

SIGNAL_URL = os.environ.get("SIGNAL_SERVICE_URL", "http://localhost:8091")
TIMEOUT = float(os.environ.get("SIGNAL_TIMEOUT", "30"))


def _get(path: str) -> dict | list | None:
    try:
        r = httpx.get(f"{SIGNAL_URL}{path}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


@tool
def get_signal_board() -> str:
    """Every KPI right now, with its value, its baseline and whether it breached.

    Read this when one number moves, to see whether anything else moved with it.
    Six signals moving together is usually one cause, and often an upstream one.
    """
    data = _get("/signals")
    if data is None:
        # the API is down, so measure in process rather than give up
        from signal_service import evaluate as ev
        rows = [{"kpi": k.name, "value": v.value, "baseline": v.baseline,
                 "breached": v.breached, "owner": k.owner, "unit": k.unit}
                for k, _r, v in ev.evaluate_all()]
        data = {"signals": rows, "breached": sum(1 for r in rows if r["breached"])}

    lines = [f"{data.get('breached', 0)} of {len(data['signals'])} signals breached", ""]
    for s in data["signals"]:
        flag = "BREACH" if s["breached"] else "  ok  "
        value = "--" if s["value"] is None else f"{s['value']:,.2f}"
        base = f"{s['baseline']:,.2f}" if s.get("baseline") is not None else "--"
        lines.append(f"  {flag}  {s['kpi']:26} {value:>14}{s.get('unit', '')}"
                     f"   normally {base:>14}   {s.get('owner', '')}")
    return "\n".join(lines)


@tool
def get_signal(name: str) -> str:
    """One KPI: its current value, its baseline, its owner and what it means."""
    data = _get(f"/signals/{name}")
    if data is None:
        return f"could not reach the signal service at {SIGNAL_URL}"
    return "\n".join(f"  {k:12} {v}" for k, v in data.items() if v is not None)


@tool
def get_kpi_definition(name: str) -> str:
    """How a KPI is defined, including the exact query behind it.

    Worth reading before blaming the data. Sometimes the number is right and
    the definition is wrong, and that is a one line fix rather than an incident.
    """
    data = _get(f"/kpis/{name}")
    if data is None:
        return f"could not reach the signal service at {SIGNAL_URL}"
    return "\n".join(f"  {k:16} {v}" for k, v in data.items() if v is not None)


@tool
def get_signal_history(name: str, limit: int = 30) -> str:
    """What one KPI has been doing over its recent readings.

    Answers "when did this start", which is the question that turns a diagnosis
    into a cause.
    """
    data = _get(f"/signals/{name}/history?limit={limit}")
    if data is None:
        return f"could not reach the signal service at {SIGNAL_URL}"
    readings = data.get("readings", [])
    if not readings:
        return f"no readings stored for {name} yet"
    lines = [f"{len(readings)} readings, newest first", ""]
    for r in readings:
        flag = "BREACH" if r["breached"] else "ok"
        value = "--" if r["value"] is None else f"{r['value']:,.3f}"
        lines.append(f"  {str(r['read_at'])[:19]}  {value:>14}  {flag}")
    return "\n".join(lines)


SIGNAL_TOOLS = [get_signal_board, get_signal, get_kpi_definition, get_signal_history]
