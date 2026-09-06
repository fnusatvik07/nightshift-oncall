"""The signal board, in a browser.

    python cli.py dashboard        then open http://localhost:8099

Same six signals as `python cli.py board`, same queries, same numbers. This is
only a different way of looking at them, and it is worth saying that out loud
in class: the dashboard is not the system. The system is six SQL queries and a
baseline. The dashboard is a nice way to read the answer.
"""
from __future__ import annotations

import pathlib

import psycopg
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from pipelines.lib.config import SCHEMA, dsn
from signals.board import collect

app = FastAPI(title="teach signal board")
HERE = pathlib.Path(__file__).parent


@app.get("/api/signals")
def api_signals():
    return JSONResponse([
        {"name": s.name, "value": round(s.value, 3), "unit": s.unit,
         "baseline": round(s.baseline, 3), "breached": s.breached,
         "owner": s.owner, "watches": s.watches, "means": s.means,
         "detail": s.detail, "sql": " ".join(s.current_sql.split())}
        for s in collect()])


@app.get("/api/runs")
def api_runs():
    with psycopg.connect(dsn()) as c:
        rows = c.execute(f"""SELECT pipeline, status, rows_in, rows_out,
                                    to_char(started_at,'HH24:MI:SS'), message
                             FROM {SCHEMA}.runs ORDER BY started_at DESC LIMIT 12""").fetchall()
        tables = [(n, c.execute(f"SELECT count(*) FROM {SCHEMA}.{n}").fetchone()[0])
                  for n in [r[0] for r in c.execute(
                      "SELECT table_name FROM information_schema.tables "
                      "WHERE table_schema=%s ORDER BY table_name", (SCHEMA,))]]
    return JSONResponse({
        "runs": [{"pipeline": p, "status": s, "rows_in": i or 0, "rows_out": o or 0,
                  "at": t, "message": m or ""} for p, s, i, o, t, m in rows],
        "tables": [{"name": n, "rows": k} for n, k in tables]})


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "dashboard.html").read_text()
