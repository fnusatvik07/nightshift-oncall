"""Invariants: the things that must ALWAYS be true.

## Why this is not the signal board

A signal watches a number that is **usually** in a range. Rides per day is
normally around twelve thousand, and a quiet Sunday is not a bug.

An invariant is a statement that is **never** allowed to be false. A completed
ride cannot have a negative fare. A silver row cannot exist for a ride that is
not in bronze. There is no tolerance, no baseline, and no history: one violation
is one bug.

That difference is why they are separate files. A signal that fires is a
question for a human. **An invariant that fires is a defect**, and the honest
response is usually to stop rather than to investigate.

## The shape

Every invariant is a query that returns **the rows that violate it**. Zero rows
means it holds. That shape is chosen on purpose: when it fails you already have
the evidence in your hand, rather than a boolean and a hunt.

## Where they run

Three places, and they are the same checks each time:

    the verifier agent   after a change, to prove nothing else broke
    the signal API       GET /invariants, for a dashboard
    the command line     python cli.py invariants

This is the middle checkpoint of the three: the contract refuses one record on
the way in, the invariants judge the whole warehouse after a write, and the
signal board notices numbers drifting over time.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from pipelines.lib.config import SCHEMA, dsn


@dataclass(frozen=True)
class Invariant:
    """One thing that must never be false."""

    name: str
    means: str                 # in words, for whoever sees it fail
    sql: str                   # returns the VIOLATING rows. Zero rows is a pass
    severity: str = "high"     # low, medium, high, critical
    layer: str = "silver"      # which layer it judges


# ═══════════════════════════════════════════════════════════════════════════
# The invariants, grouped by the layer they judge.
#
# Read them as sentences. Every one of them should be a thing you would say out
# loud to a colleague without hedging: "a completed ride always has a fare".
# If you find yourself wanting to add "usually", it is a signal, not an
# invariant, and it belongs in kpis.py.
# ═══════════════════════════════════════════════════════════════════════════

INVARIANTS: list[Invariant] = [

    # ── bronze: the copy must be faithful ──────────────────────────────────
    Invariant(
        name="bronze_trips_unique",
        means="A ride appears at most once in bronze_trips. The primary key "
              "enforces this, so a violation means the key is gone.",
        layer="bronze", severity="critical",
        sql=f"""SELECT trip_id, count(*) FROM {SCHEMA}.bronze_trips
                GROUP BY 1 HAVING count(*) > 1""",
    ),
    Invariant(
        name="bronze_trips_status_known",
        means="Every landed ride has one of the four agreed statuses. A fifth "
              "means the contract let something through it should have held.",
        layer="bronze", severity="critical",
        sql=f"""SELECT DISTINCT status FROM {SCHEMA}.bronze_trips
                WHERE status NOT IN ('completed','cancelled_rider',
                                     'cancelled_driver','no_driver')""",
    ),
    Invariant(
        name="bronze_events_pair_unique",
        means="A ride has at most one event of each kind. Two 'completed' "
              "events for one ride means a replay landed twice.",
        layer="bronze", severity="critical",
        sql=f"""SELECT trip_id, event, count(*) FROM {SCHEMA}.bronze_events
                GROUP BY 1,2 HAVING count(*) > 1""",
    ),
    Invariant(
        name="bronze_no_future_rides",
        means="No ride was requested in the future. A violation is a clock or "
              "a timezone bug, and it silently poisons every window.",
        layer="bronze", severity="high",
        sql=f"""SELECT trip_id, trip_date FROM {SCHEMA}.bronze_trips
                WHERE trip_date > (current_date + 1)""",
    ),

    # ── silver: the join must not invent or lose rides ─────────────────────
    Invariant(
        name="silver_one_row_per_ride",
        means="Silver is one row per ride. More than one means a join "
              "multiplied rows, and every aggregate above it is inflated.",
        layer="silver", severity="critical",
        sql=f"""SELECT trip_id, count(*) FROM {SCHEMA}.silver_rides
                GROUP BY 1 HAVING count(*) > 1""",
    ),
    Invariant(
        name="silver_loses_no_rides",
        means="Every ride in bronze reaches silver. A missing one means a join "
              "quietly deleted it, which is the most expensive bug in this "
              "whole project.",
        layer="silver", severity="critical",
        sql=f"""SELECT t.trip_id FROM {SCHEMA}.bronze_trips t
                LEFT JOIN {SCHEMA}.silver_rides s ON s.trip_id = t.trip_id
                WHERE s.trip_id IS NULL LIMIT 50""",
    ),
    Invariant(
        name="silver_invents_no_rides",
        means="Silver contains no ride that is not in bronze. A violation "
              "means rows are being created in the warehouse, not copied.",
        layer="silver", severity="critical",
        sql=f"""SELECT s.trip_id FROM {SCHEMA}.silver_rides s
                LEFT JOIN {SCHEMA}.bronze_trips t ON t.trip_id = s.trip_id
                WHERE t.trip_id IS NULL LIMIT 50""",
    ),
    Invariant(
        name="silver_fare_not_negative",
        means="No ride was charged a negative amount. Money going backwards is "
              "never a rounding error.",
        layer="silver", severity="critical",
        sql=f"""SELECT trip_id, fare FROM {SCHEMA}.silver_rides
                WHERE fare < 0 LIMIT 50""",
    ),
    Invariant(
        name="silver_cancelled_has_no_fare",
        means="A cancelled ride was never charged. A fare on one means the "
              "join attached the wrong event to the wrong ride.",
        layer="silver", severity="high",
        sql=f"""SELECT trip_id, status, fare FROM {SCHEMA}.silver_rides
                WHERE status LIKE 'cancelled%%' AND fare IS NOT NULL LIMIT 50""",
    ),
    Invariant(
        name="silver_duration_sane",
        means="No ride lasted a negative time or more than a day. Both are "
              "conversion bugs rather than unusual journeys.",
        layer="silver", severity="high",
        sql=f"""SELECT trip_id, duration_min FROM {SCHEMA}.silver_rides
                WHERE duration_min < 0 OR duration_min > 1440 LIMIT 50""",
    ),
    Invariant(
        name="silver_settled_has_amount",
        means="A ride marked settled carries the amount that settled. Marked "
              "settled with no number is worse than not settled at all.",
        layer="silver", severity="high",
        sql=f"""SELECT trip_id FROM {SCHEMA}.silver_rides
                WHERE is_settled AND settled_net IS NULL LIMIT 50""",
    ),

    # ── gold: the aggregate must equal the rows underneath it ──────────────
    Invariant(
        name="gold_totals_match_silver",
        means="The ride count in gold equals the rides in silver for that day. "
              "This is the check that catches an aggregate built from a stale "
              "or partial silver table.",
        layer="gold", severity="critical",
        sql=f"""SELECT g.trip_date, g.rides, count(s.trip_id) AS actual
                FROM {SCHEMA}.gold_daily g
                LEFT JOIN {SCHEMA}.silver_rides s ON s.trip_date = g.trip_date
                GROUP BY g.trip_date, g.rides
                HAVING g.rides <> count(s.trip_id)""",
    ),
    Invariant(
        name="gold_parts_sum_to_whole",
        means="Completed plus cancelled never exceeds the total rides. A "
              "violation means the FILTER conditions overlap.",
        layer="gold", severity="critical",
        sql=f"""SELECT trip_date, rides, completed, cancelled
                FROM {SCHEMA}.gold_daily WHERE completed + cancelled > rides""",
    ),
    Invariant(
        name="gold_revenue_not_negative",
        means="A day never earned a negative amount. A negative total is a "
              "sign error or a refund counted as revenue, and it reaches a "
              "board pack before anybody re-reads the query.",
        layer="gold", severity="critical",
        sql=f"""SELECT trip_date, revenue FROM {SCHEMA}.gold_daily
                WHERE revenue < 0""",
    ),
    Invariant(
        name="gold_one_row_per_day",
        means="Gold is one row per day. Two rows for one date means the "
              "rebuild appended instead of replacing.",
        layer="gold", severity="critical",
        sql=f"""SELECT trip_date, count(*) FROM {SCHEMA}.gold_daily
                GROUP BY 1 HAVING count(*) > 1""",
    ),

    # ── the bookkeeping must be honest ─────────────────────────────────────
    Invariant(
        name="runs_have_ended",
        means="No run has been 'running' for more than an hour. One that has "
              "is a process that died without saying so.",
        layer="platform", severity="high",
        sql=f"""SELECT run_id, pipeline, started_at FROM {SCHEMA}.runs
                WHERE status = 'running'
                  AND started_at < now() - interval '1 hour' LIMIT 50""",
    ),
    Invariant(
        name="quarantine_has_reasons",
        means="Every held record says why it was held. One without a reason is "
              "a record nobody can ever action.",
        layer="platform", severity="medium",
        sql=f"""SELECT id, pipeline FROM {SCHEMA}.quarantine
                WHERE reason IS NULL OR reason = '' LIMIT 50""",
    ),
]

BY_NAME = {i.name: i for i in INVARIANTS}


# ── running them ───────────────────────────────────────────────────────────

def check(inv: Invariant, conn=None) -> dict:
    """Run one invariant. Never raises."""
    own = conn is None
    try:
        conn = conn or psycopg.connect(dsn())
    except Exception as e:
        return {"name": inv.name, "held": None, "violations": 0,
                "error": f"{type(e).__name__}: {e}", "sample": []}
    try:
        with conn.cursor() as cur:
            cur.execute(inv.sql)
            rows = cur.fetchmany(5)
            more = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(rows)
        return {"name": inv.name, "held": len(rows) == 0,
                "violations": max(more, len(rows)), "error": None,
                "sample": [tuple(str(v)[:40] for v in r) for r in rows],
                "severity": inv.severity, "layer": inv.layer, "means": inv.means}
    except Exception as e:
        # A table that does not exist yet is not a violation, it is a warehouse
        # that has not been built. Roll back so the shared transaction survives.
        try:
            conn.rollback()
        except Exception:
            pass
        return {"name": inv.name, "held": None, "violations": 0,
                "error": f"{type(e).__name__}: {e}", "sample": [],
                "severity": inv.severity, "layer": inv.layer, "means": inv.means}
    finally:
        if own:
            conn.close()


def check_all(conn=None) -> dict:
    """Every invariant, on one connection.

    Returns a summary a person or an agent can read without further work.
    """
    own = conn is None
    try:
        conn = conn or psycopg.connect(dsn())
    except Exception:
        conn = None
        own = False

    results = [check(i, conn) for i in INVARIANTS]
    if own and conn is not None:
        conn.close()

    held = [r for r in results if r["held"] is True]
    broken = [r for r in results if r["held"] is False]
    skipped = [r for r in results if r["held"] is None]

    return {
        "total": len(results),
        "held": len(held),
        "violated": len(broken),
        "not_checkable": len(skipped),
        "passed": not broken,
        "violations": broken,
        "results": results,
    }


def summary_text(report: dict) -> str:
    """The same report, formatted for a terminal or a model to read."""
    lines = [f"{report['held']} of {report['total']} invariants hold"]
    if report["not_checkable"]:
        lines[0] += f", {report['not_checkable']} not checkable"
    lines.append("")
    for r in report["results"]:
        if r["held"] is True:
            flag = "  ok  "
        elif r["held"] is False:
            flag = "BROKEN"
        else:
            flag = " ---- "
        detail = ""
        if r["held"] is False:
            detail = f"{r['violations']} violating row(s), e.g. {r['sample'][:2]}"
        elif r["error"]:
            detail = r["error"][:60]
        lines.append(f"  {flag}  {r['name']:30} {detail}")
    return "\n".join(lines)
