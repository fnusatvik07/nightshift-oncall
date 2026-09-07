"""What the agents worked on, and how it ended.

One row per investigation. It exists because "the agent looked at this" is a
fact somebody will want tomorrow, and holding it only in the service's memory
means a restart erases the record of every incident that was ever handled.

Both entry points write here, which is the point of the module:

    the service        POST /incident, on a pool thread
    the command line   python cli.py investigate <kpi>

so the dashboard shows the same list either way, and a run you did live in
front of a class is a run the estate remembers.
"""
from __future__ import annotations

import psycopg

from events.contract import Incident
from pipelines.lib.config import dsn

SCHEMA = "oncall"

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};

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


def setup() -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)


def start(incident: Incident) -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.investigations
                      (breach_id, kpi, incident_id, signals, status)
                      VALUES (%s, %s, %s, %s, 'running')
                      ON CONFLICT (breach_id) DO UPDATE
                      SET status = 'running', started_at = now(),
                          ended_at = NULL, error = NULL""",
                  (incident.incident_id, incident.primary.kpi,
                   incident.incident_id, incident.signal_count))


def end(breach_id: str, status: str, steps: str = "",
        handover: str = "", error: str = "") -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""UPDATE {SCHEMA}.investigations
                      SET status = %s, ended_at = now(), steps = %s,
                          handover = %s, error = %s
                      WHERE breach_id = %s""",
                  (status, steps, handover, error or None, breach_id))


def recent(limit: int = 10) -> list[dict]:
    with psycopg.connect(dsn()) as c:
        rows = c.execute(
            f"""SELECT breach_id, kpi, incident_id, signals, status, steps,
                       coalesce(handover, ''), started_at, ended_at
                FROM {SCHEMA}.investigations
                ORDER BY started_at DESC LIMIT %s""", (limit,)).fetchall()
    keys = ("breach_id", "kpi", "incident_id", "signals", "status", "steps",
            "handover", "started_at", "ended_at")
    return [dict(zip(keys, r)) for r in rows]
