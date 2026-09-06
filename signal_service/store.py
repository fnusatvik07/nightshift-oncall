"""Where the service keeps what it has seen.

Two tables, in a schema of the service's own.

Note the schema name. The signal board **reads** the warehouse and **writes**
`oncall`. It never writes a row into `teach`. That is not tidiness, it is the
property that lets you drop the entire observability layer and rebuild it
without touching a single number anybody reports on.

    oncall.kpi_readings   every measurement, forever. This is the history a
                          baseline is computed from, and the thing you look at
                          when somebody asks "when did it start"

    oncall.breaches       one row per breach, deduplicated by fingerprint, with
                          what the agent system did about it
"""
from __future__ import annotations

import datetime as dt

import psycopg

from events.contract import SignalBreach
from pipelines.lib.config import dsn

SCHEMA = "oncall"

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};

CREATE TABLE IF NOT EXISTS {SCHEMA}.kpi_readings (
    id         BIGSERIAL PRIMARY KEY,
    kpi        TEXT NOT NULL,
    value      DOUBLE PRECISION,          -- NULL when it could not be measured
    error      TEXT,
    breached   BOOLEAN NOT NULL DEFAULT false,
    baseline   DOUBLE PRECISION,
    z_score    DOUBLE PRECISION,
    read_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_readings_kpi_at
    ON {SCHEMA}.kpi_readings (kpi, read_at DESC);

CREATE TABLE IF NOT EXISTS {SCHEMA}.breaches (
    breach_id    TEXT PRIMARY KEY,
    fingerprint  TEXT NOT NULL,
    kpi          TEXT NOT NULL,
    severity     TEXT NOT NULL,
    owner        TEXT NOT NULL,
    value        DOUBLE PRECISION,
    baseline     DOUBLE PRECISION,
    detected_at  TIMESTAMPTZ NOT NULL,
    payload      JSONB NOT NULL,          -- the whole record, as emitted

    -- what happened next
    status       TEXT NOT NULL DEFAULT 'open',
                 -- open, dispatched, diagnosed, dismissed, failed
    dispatched_at TIMESTAMPTZ,
    handled_at    TIMESTAMPTZ,
    outcome       TEXT
);
CREATE INDEX IF NOT EXISTS ix_breaches_status ON {SCHEMA}.breaches (status, detected_at DESC);
CREATE INDEX IF NOT EXISTS ix_breaches_fp     ON {SCHEMA}.breaches (fingerprint, detected_at DESC);
"""


def setup() -> None:
    """Create the schema and its two tables. Safe to call every start."""
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)


# ── readings ───────────────────────────────────────────────────────────────

def save_readings(rows: list[tuple]) -> None:
    """One batch insert per evaluation cycle, not one per KPI."""
    if not rows:
        return
    with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
        cur.executemany(
            f"""INSERT INTO {SCHEMA}.kpi_readings
                (kpi, value, error, breached, baseline, z_score)
                VALUES (%s, %s, %s, %s, %s, %s)""", rows)
        c.commit()


def recent_readings(kpi: str, limit: int = 50) -> list[dict]:
    with psycopg.connect(dsn()) as c:
        rows = c.execute(
            f"""SELECT value, breached, baseline, z_score, read_at
                FROM {SCHEMA}.kpi_readings WHERE kpi = %s
                ORDER BY read_at DESC LIMIT %s""", (kpi, limit)).fetchall()
    return [{"value": v, "breached": b, "baseline": base, "z_score": z, "read_at": t}
            for v, b, base, z, t in rows]


# ── breaches ───────────────────────────────────────────────────────────────

def already_open(breach: SignalBreach, within_minutes: int = 120) -> str | None:
    """Has this exact breach already been raised recently?

    Without this, a board on a five minute clock opens 288 investigations a day
    for one broken pipeline, and the thing you built to help becomes the outage.
    Returns the existing breach_id if so.
    """
    with psycopg.connect(dsn()) as c:
        row = c.execute(
            f"""SELECT breach_id FROM {SCHEMA}.breaches
                WHERE fingerprint = %s
                  AND status <> 'dismissed'
                  AND detected_at > now() - make_interval(mins => %s)
                ORDER BY detected_at DESC LIMIT 1""",
            (breach.fingerprint(), within_minutes)).fetchone()
    return row[0] if row else None


def record(breach: SignalBreach) -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(
            f"""INSERT INTO {SCHEMA}.breaches
                (breach_id, fingerprint, kpi, severity, owner, value, baseline,
                 detected_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (breach_id) DO NOTHING""",
            (breach.breach_id, breach.fingerprint(), breach.kpi, breach.severity,
             breach.owner, breach.value, breach.baseline, breach.detected_at,
             breach.to_json()))


def mark(breach_id: str, status: str, outcome: str = "") -> None:
    column = {"dispatched": "dispatched_at"}.get(status, "handled_at")
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(
            f"""UPDATE {SCHEMA}.breaches
                SET status = %s, {column} = %s, outcome = coalesce(nullif(%s, ''), outcome)
                WHERE breach_id = %s""",
            (status, dt.datetime.now(dt.timezone.utc), outcome, breach_id))


def open_breaches(limit: int = 50) -> list[dict]:
    with psycopg.connect(dsn()) as c:
        rows = c.execute(
            f"""SELECT breach_id, kpi, severity, owner, value, baseline,
                       detected_at, status, outcome
                FROM {SCHEMA}.breaches
                ORDER BY detected_at DESC LIMIT %s""", (limit,)).fetchall()
    keys = ("breach_id", "kpi", "severity", "owner", "value", "baseline",
            "detected_at", "status", "outcome")
    return [dict(zip(keys, r)) for r in rows]


def load(breach_id: str) -> SignalBreach | None:
    with psycopg.connect(dsn()) as c:
        row = c.execute(f"SELECT payload FROM {SCHEMA}.breaches WHERE breach_id = %s",
                        (breach_id,)).fetchone()
    if not row:
        return None
    payload = row[0]
    return SignalBreach.model_validate(payload)
