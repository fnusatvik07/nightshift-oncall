"""The signal board, in a browser.

    python cli.py dashboard          then open http://localhost:8099

Same thirteen KPIs as `python cli.py signals`, same seventeen invariants, same
queries, same numbers. This is only a different way of looking at them, and it
is worth saying out loud in class:

> **The dashboard is not the system.** The system is thirteen SQL queries, a
> baseline for each, and a clock. This is a nice way to read the answer.

It refreshes itself, so you can leave it on a second screen during a lesson,
break something in a terminal, and watch a tile go red without touching it.
"""
from __future__ import annotations

import datetime as dt

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import evaluate as ev
from . import invariants as inv
from . import store

app = FastAPI(title="NIGHTSHIFT signal board")


# ── the numbers ────────────────────────────────────────────────────────────

def snapshot() -> dict:
    signals = []
    for kpi, reading, verdict in ev.evaluate_all():
        signals.append({
            "kpi": kpi.name, "title": kpi.title, "owner": kpi.owner,
            "watches": kpi.watches, "unit": kpi.unit, "means": kpi.means,
            "value": verdict.value, "baseline": verdict.baseline,
            "breached": verdict.breached, "measured": reading.measured,
            "detail": verdict.detail, "severity": kpi.severity,
            "kind": "a rule" if kpi.judgement == "fixed" else "from history",
            "sql": " ".join(kpi.sql.split()),
        })

    try:
        report = inv.check_all()
    except Exception:                                # noqa: BLE001
        report = {"held": 0, "total": 0, "violated": 0, "results": []}

    try:
        incidents = store.open_incidents(8)
    except Exception:                                # noqa: BLE001
        incidents = []

    # The agent service owns this table, so the board reads it through the
    # agent service's own module rather than writing the query twice.
    try:
        from agent_service import journal
        investigations = [
            {"id": r["breach_id"], "kpi": r["kpi"], "status": r["status"],
             "steps": r["steps"] or "", "handover": r["handover"][:400]}
            for r in journal.recent(5)]
    except Exception:                                # noqa: BLE001
        investigations = []

    return {
        "at": dt.datetime.now().strftime("%H:%M:%S"),
        "signals": signals,
        "breached": sum(1 for s in signals if s["breached"]),
        "invariants": report,
        "incidents": incidents,
        "investigations": investigations,
    }


@app.get("/api/snapshot")
def api_snapshot() -> dict:
    # Returned as a dict rather than a JSONResponse on purpose: FastAPI encodes
    # datetimes on the way out, and every incident carries one.
    return snapshot()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


PAGE = """
<!doctype html>
<meta charset="utf-8">
<title>NIGHTSHIFT signal board</title>
<style>
  :root {
    --ink:#111114; --mute:#6B7280; --line:#E4E4E7; --paper:#FFFFFF; --wash:#F7F7F8;
    --ok:#047857; --ok-bg:#ECFDF5; --bad:#B91C1C; --bad-bg:#FEF2F2;
    --warn:#B45309; --warn-bg:#FFFBEB; --blue:#1D4ED8; --blue-bg:#EFF4FF;
  }
  * { box-sizing:border-box }
  body { margin:0; background:var(--wash); color:var(--ink);
         font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif }
  header { background:var(--ink); color:#fff; padding:18px 28px;
           display:flex; align-items:baseline; gap:20px; flex-wrap:wrap }
  header h1 { margin:0; font-size:19px; letter-spacing:.3px }
  header .sub { color:#A1A1AA; font-size:13px }
  header .spacer { flex:1 }
  .pill { padding:3px 11px; border-radius:999px; font-size:12px; font-weight:600 }
  .pill.ok { background:var(--ok); color:#fff }
  .pill.bad { background:var(--bad); color:#fff }
  main { padding:24px 28px 60px; max-width:1500px; margin:0 auto }
  h2 { font-size:12px; letter-spacing:1.1px; text-transform:uppercase;
       color:var(--mute); margin:32px 0 12px; font-weight:700 }
  h2:first-of-type { margin-top:8px }
  .grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(310px,1fr)) }
  .card { background:var(--paper); border:1px solid var(--line); border-left-width:4px;
          border-radius:10px; padding:14px 16px; cursor:pointer }
  .card.ok   { border-left-color:var(--ok) }
  .card.bad  { border-left-color:var(--bad); background:var(--bad-bg) }
  .card.dead { border-left-color:var(--line); opacity:.55 }
  .card .name { font-weight:650; font-size:14px }
  .card .val { font-size:27px; font-variant-numeric:tabular-nums; margin:6px 0 2px }
  .card .base { color:var(--mute); font-size:12.5px; font-variant-numeric:tabular-nums }
  .card .who { color:var(--mute); font-size:12px; margin-top:8px;
               display:flex; justify-content:space-between; gap:8px }
  .card .sql { display:none; margin-top:10px; padding-top:10px; border-top:1px solid var(--line);
               font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
               color:var(--mute); white-space:pre-wrap; word-break:break-word }
  .card.open .sql { display:block }
  .card .means { display:none; margin-top:8px; font-size:12.5px; color:var(--mute) }
  .card.open .means { display:block }
  table { width:100%; border-collapse:collapse; background:var(--paper);
          border:1px solid var(--line); border-radius:10px; overflow:hidden }
  th, td { text-align:left; padding:9px 14px; border-bottom:1px solid var(--line);
           font-size:13.5px }
  th { background:var(--wash); font-size:11px; letter-spacing:.7px;
       text-transform:uppercase; color:var(--mute) }
  tr:last-child td { border-bottom:none }
  .tag { display:inline-block; padding:1px 8px; border-radius:999px;
         font-size:11px; font-weight:650 }
  .tag.ok { background:var(--ok-bg); color:var(--ok) }
  .tag.bad { background:var(--bad-bg); color:var(--bad) }
  .tag.warn { background:var(--warn-bg); color:var(--warn) }
  .tag.blue { background:var(--blue-bg); color:var(--blue) }
  .empty { color:var(--mute); padding:14px 2px; font-size:13.5px }
  .foot { margin-top:34px; color:var(--mute); font-size:12.5px; line-height:1.7 }
  code { font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;
         background:var(--wash); padding:1px 5px; border-radius:4px }
</style>

<header>
  <h1>NIGHTSHIFT · signal board</h1>
  <span class="sub" id="clock"></span>
  <span class="spacer"></span>
  <span class="pill" id="state">measuring</span>
</header>

<main>
  <h2>Signals · a KPI plus a baseline. These can breach</h2>
  <div class="grid" id="signals"></div>

  <h2>Invariants · things that must never be false. These are defects</h2>
  <div id="invariants"></div>

  <h2>Incidents · one row per cause, not per signal</h2>
  <div id="incidents"></div>

  <h2>Investigations · what the agents did about them</h2>
  <div id="investigations"></div>

  <p class="foot">
    Click any tile to see the exact query behind it and what it means for its owner.<br>
    Refreshes every 10 seconds. Break something with <code>python break_it.py</code>
    and watch a tile turn red.<br>
    <b>The dashboard is not the system.</b> The system is thirteen queries, a baseline
    for each, and a clock.
  </p>
</main>

<script>
const fmt = n => n === null || n === undefined ? '--'
  : Number(n).toLocaleString(undefined, {maximumFractionDigits:2});

function signalCard(s) {
  const cls = !s.measured ? 'dead' : (s.breached ? 'bad' : 'ok');
  return `<div class="card ${cls}" onclick="this.classList.toggle('open')">
    <div class="name">${s.kpi}</div>
    <div class="val">${fmt(s.value)}${s.unit || ''}</div>
    <div class="base">normally ${fmt(s.baseline)}${s.unit || ''} &middot; ${s.kind}</div>
    <div class="who"><span>${s.owner}</span><span>${s.watches}</span></div>
    <div class="means">${s.means}</div>
    <div class="sql">${s.sql}</div>
  </div>`;
}

function render(d) {
  document.getElementById('clock').textContent =
    `${d.signals.length} signals · ${d.invariants.total} invariants · ${d.at}`;
  const st = document.getElementById('state');
  const bad = d.breached + (d.invariants.violated || 0);
  st.textContent = bad ? `${bad} need attention` : 'all clear';
  st.className = 'pill ' + (bad ? 'bad' : 'ok');

  document.getElementById('signals').innerHTML = d.signals.map(signalCard).join('');

  const iv = d.invariants.results || [];
  document.getElementById('invariants').innerHTML = iv.length === 0
    ? '<div class="empty">not checked yet</div>'
    : `<table><tr><th>invariant</th><th>layer</th><th>holds</th><th>violations</th></tr>` +
      iv.map(r => `<tr>
        <td>${r.name}</td><td>${r.layer || ''}</td>
        <td><span class="tag ${r.held === true ? 'ok' : r.held === false ? 'bad' : 'warn'}">
          ${r.held === true ? 'holds' : r.held === false ? 'BROKEN' : 'skipped'}</span></td>
        <td>${r.held === false ? r.violations : ''}</td></tr>`).join('') + '</table>';

  document.getElementById('incidents').innerHTML = d.incidents.length === 0
    ? '<div class="empty">nothing has breached</div>'
    : `<table><tr><th>incident</th><th>lead signal</th><th>severity</th>
       <th>signals</th><th>status</th><th>owners</th></tr>` +
      d.incidents.map(i => `<tr>
        <td><code>${i.incident_id}</code></td><td>${i.primary_kpi}</td>
        <td><span class="tag ${i.severity === 'critical' || i.severity === 'high' ? 'bad' : 'warn'}">${i.severity}</span></td>
        <td>${i.signal_count}</td>
        <td><span class="tag blue">${i.status}</span></td>
        <td>${i.owners}</td></tr>`).join('') + '</table>';

  document.getElementById('investigations').innerHTML = d.investigations.length === 0
    ? '<div class="empty">the agents have not been woken yet. Try <code>python cli.py investigate surge_coverage_pct</code></div>'
    : `<table><tr><th>incident</th><th>signal</th><th>status</th><th>steps</th></tr>` +
      d.investigations.map(v => `<tr>
        <td><code>${v.id}</code></td><td>${v.kpi}</td>
        <td><span class="tag ${v.status === 'done' ? 'ok' : v.status === 'failed' ? 'bad' : 'warn'}">${v.status}</span></td>
        <td>${v.steps}</td></tr>`).join('') + '</table>';
}

async function tick() {
  try { render(await (await fetch('/api/snapshot')).json()); }
  catch (e) { document.getElementById('state').textContent = 'cannot reach the warehouse'; }
}
tick(); setInterval(tick, 10000);
</script>
"""


def serve(port: int = 8099) -> None:
    print(f"\n  signal board at http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
