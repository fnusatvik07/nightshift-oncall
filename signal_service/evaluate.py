"""Turning a KPI into a reading, and a reading into a verdict.

Two steps, deliberately separate, because they fail for different reasons and
you want to be able to tell them apart.

    reading    run the query, get a number. Fails when the database is down
               or the table does not exist yet.

    verdict    compare the number to what normal looks like. Cannot fail:
               it is arithmetic on a number you already have.

Keeping them apart means "the KPI could not be measured" and "the KPI was
measured and it is wrong" are different outcomes, and the second one is the
only one worth waking somebody for.
"""
from __future__ import annotations

import datetime as dt
import statistics
import uuid

import psycopg
from pydantic import BaseModel

from events.contract import SignalBreach
from pipelines.lib.config import dsn

from .kpis import CATALOGUE, KPI


class Reading(BaseModel):
    """What one KPI was, at one moment."""

    kpi: str
    value: float | None
    at: dt.datetime
    error: str | None = None
    history: list[float] = []

    @property
    def measured(self) -> bool:
        return self.value is not None


class Verdict(BaseModel):
    """Whether that reading is worth anybody's night."""

    kpi: str
    value: float | None
    baseline: float
    deviation: float = 0.0
    z_score: float | None = None
    direction: str = "above"
    breached: bool = False
    detail: str = ""


# ── step one: measure ──────────────────────────────────────────────────────

def read(kpi: KPI, conn=None) -> Reading:
    """Run the KPI's query and its history query. Never raises."""
    now = dt.datetime.now(dt.timezone.utc)
    own_connection = conn is None
    try:
        conn = conn or psycopg.connect(dsn())
    except Exception as e:
        return Reading(kpi=kpi.name, value=None, at=now,
                       error=f"{type(e).__name__}: {e}")

    try:
        with conn.cursor() as cur:
            cur.execute(kpi.sql)
            row = cur.fetchone()
            value = float(row[0]) if row and row[0] is not None else None

            history: list[float] = []
            if kpi.judgement == "history" and kpi.history_sql:
                cur.execute(kpi.history_sql)
                history = [float(r[0]) for r in cur.fetchall() if r[0] is not None]

        return Reading(kpi=kpi.name, value=value, at=now, history=history)
    except Exception as e:
        # A KPI whose table does not exist yet is not an emergency, it is a
        # warehouse that has not been built. Say which, and carry on.
        #
        # The rollback is the line that matters. Postgres aborts the whole
        # transaction on any error, so without it every KPI after a failing one
        # dies with "current transaction is aborted" and you lose twelve good
        # numbers to one bad query. One poison KPI must not block the rest,
        # which is the same rule as one poison message on a topic.
        try:
            conn.rollback()
        except Exception:
            pass
        return Reading(kpi=kpi.name, value=None, at=now,
                       error=f"{type(e).__name__}: {e}")
    finally:
        if own_connection:
            conn.close()


# ── step two: judge ────────────────────────────────────────────────────────

def judge(kpi: KPI, reading: Reading) -> Verdict:
    """Compare a reading to what normal looks like. Pure arithmetic."""
    if not reading.measured:
        return Verdict(kpi=kpi.name, value=None, baseline=0.0,
                       detail=reading.error or "not measured")

    value = reading.value

    if kpi.judgement == "fixed":
        # A baseline somebody decided, not one computed from history. Zero held
        # records is not an average, it is a rule.
        baseline = float(kpi.baseline or 0.0)
        gap = value - baseline
        direction = "above" if gap >= 0 else "below"
        breached = abs(gap) > max(kpi.tolerance, 1e-9)
        detail = (f"expected {baseline:g}{kpi.unit}"
                  + (f" give or take {kpi.tolerance:g}" if kpi.tolerance else ""))
    else:
        history = reading.history
        if len(history) < 3:
            return Verdict(kpi=kpi.name, value=value, baseline=0.0,
                           detail=f"only {len(history)} reading(s) of history, not judging yet")
        baseline = statistics.mean(history)
        # a floor on the spread, so a KPI that has been perfectly flat does not
        # breach on the first digit of movement
        spread = max(statistics.pstdev(history), abs(baseline) * 0.001, 0.01)
        z = (value - baseline) / spread
        gap = value - baseline
        direction = "above" if gap >= 0 else "below"
        breached = abs(z) > kpi.z_threshold
        detail = f"{len(history)} readings of history, spread {spread:,.3f}"
        return _apply_direction(kpi, Verdict(
            kpi=kpi.name, value=value, baseline=baseline, deviation=gap,
            z_score=round(z, 2), direction=direction, breached=breached, detail=detail))

    return _apply_direction(kpi, Verdict(
        kpi=kpi.name, value=value, baseline=baseline, deviation=gap,
        direction=direction, breached=breached, detail=detail))


def _apply_direction(kpi: KPI, v: Verdict) -> Verdict:
    """Some numbers are only bad in one direction.

    Held records going UP is a problem. Held records going down is a Tuesday.
    A KPI that fires on good news trains people to ignore it.
    """
    if v.breached and kpi.watch_direction != "both" and v.direction != kpi.watch_direction:
        v.breached = False
        v.detail += f" (moved {v.direction}, which we do not watch)"
    return v


# ── the two together ───────────────────────────────────────────────────────

def evaluate(kpi: KPI, conn=None) -> tuple[Reading, Verdict]:
    reading = read(kpi, conn)
    return reading, judge(kpi, reading)


def evaluate_all(conn=None) -> list[tuple[KPI, Reading, Verdict]]:
    """Every KPI in the catalogue, on one connection.

    One connection for thirteen queries, not thirteen connections. The board
    runs on a clock, so this happens every few minutes forever, and the cost of
    getting it wrong compounds quietly.
    """
    own = conn is None
    try:
        conn = conn or psycopg.connect(dsn())
    except Exception:
        return [(k, *evaluate(k)) for k in CATALOGUE]
    try:
        return [(k, *evaluate(k, conn)) for k in CATALOGUE]
    finally:
        if own:
            conn.close()


def to_breach(kpi: KPI, reading: Reading, verdict: Verdict) -> SignalBreach:
    """The record the agent system receives.

    Everything the agent needs to start is in here. If it has to call back to
    ask what happened, the record is incomplete.
    """
    return SignalBreach(
        breach_id=f"BRC{uuid.uuid4().hex[:12].upper()}",
        detected_at=reading.at,
        kpi=kpi.name,
        title=kpi.title,
        value=float(verdict.value or 0.0),
        baseline=verdict.baseline,
        unit=kpi.unit,
        direction=verdict.direction,
        deviation=verdict.deviation,
        z_score=verdict.z_score,
        severity=kpi.severity,
        owner=kpi.owner,
        watches=kpi.watches,
        means=kpi.means,
        history=reading.history[:14],
        evaluated_sql=" ".join(kpi.sql.split()),
        baseline_kind="a rule" if kpi.judgement == "fixed" else "from history",
        tolerance=kpi.tolerance,
        normally=_normally(kpi),
    )


def _normally(kpi: KPI) -> str:
    """One sentence about what this number does when nothing is wrong.

    Written for whoever reads the breach, human or agent. "97.3 against a
    baseline of 100" means nothing until you know whether the 100 wobbles.
    """
    if kpi.judgement != "fixed":
        return "this number varies from day to day, so the baseline is an average."
    if kpi.tolerance:
        return (f"this number sits at {kpi.baseline:g}{kpi.unit} when the platform is "
                f"healthy, give or take {kpi.tolerance:g}.")
    return (f"this number is exactly {kpi.baseline:g}{kpi.unit} when the platform is "
            f"healthy. Not approximately: exactly.")
