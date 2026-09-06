"""The signal board: the thing that notices when a number stops making sense.

A signal is four things and nothing more:

    a name          so a person can talk about it
    a query         that returns exactly one number
    a baseline      what that number normally is
    an owner        who gets told when it moves

That is the whole idea. There is no model here and no intelligence. Deciding
that 34% is far from 0.09% is arithmetic, and pretending otherwise is how
people end up buying something they could have written in an afternoon.

Where it runs: beside the warehouse, on a clock, after the pipelines have
finished. Never inside a pipeline, because a check that can block a write is a
different thing with a different name, and we call that one a contract.

    python -m signals.board
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass

import psycopg

from pipelines.lib.config import SCHEMA, dsn


@dataclass
class Signal:
    """One number, watched."""
    name: str
    owner: str
    watches: str
    means: str
    current_sql: str          # returns one row, one number: how it is now
    history_sql: str = ""     # returns many rows, one number each: how it usually is
    unit: str = ""
    fixed_baseline: float | None = None
    tolerance: float = 0.0    # how far from the baseline is still fine

    value: float = 0.0
    baseline: float = 0.0
    z: float = 0.0
    breached: bool = False
    detail: str = ""


# ── the board ───────────────────────────────────────────────────────────────
# Read these as a set. Between them they answer the four questions that go
# wrong: did it arrive, is it the right amount, is it the right shape, and does
# it still add up.
SIGNALS = [
    Signal(
        name="pipelines_failing", owner="data-platform", watches=f"{SCHEMA}.runs",
        means="How many pipelines failed on their most recent run. The only signal "
              "here that does not look at data at all: it looks at whether the work "
              "happened. A pipeline that never ran leaves perfectly valid data behind.",
        unit="runs", fixed_baseline=0,
        current_sql=f"""
            SELECT count(*) FROM (
                SELECT DISTINCT ON (pipeline) pipeline, status
                FROM {SCHEMA}.runs ORDER BY pipeline, started_at DESC) x
            WHERE status <> 'success'"""),
    Signal(
        name="records_held", owner="data-platform", watches=f"{SCHEMA}.quarantine",
        means="Records a contract refused. Not lost, not wrong, just not published. "
              "A number above zero here means the warehouse is behind reality.",
        unit="rows", fixed_baseline=0,
        current_sql=f"SELECT count(*) FROM {SCHEMA}.quarantine"),
    Signal(
        name="rides_per_day", owner="operations", watches=f"{SCHEMA}.gold_daily",
        means="Rides on the most recent day, against the days before it. Catches a "
              "feed that stopped, a window that was built wrong, and a genuinely "
              "quiet Tuesday. Only two of those three are your problem.",
        unit="rides",
        current_sql=f"SELECT rides FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1",
        history_sql=f"SELECT rides FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1"),
    Signal(
        name="events_per_ride", owner="streaming", watches=f"{SCHEMA}.bronze_events",
        means="A completed ride emits five events. A cancelled one emits fewer, so the "
              "true average sits a little under five and that is correct, not a fault. "
              "Well above five means the stream was replayed and something landed twice. "
              "Far below means events are being dropped.",
        unit="", fixed_baseline=4.7, tolerance=1.0,
        current_sql=f"""
            SELECT coalesce(round(count(*)::numeric
                   / nullif(count(DISTINCT trip_id), 0), 2), 0)
            FROM {SCHEMA}.bronze_events"""),
    Signal(
        name="rides_missing_fare", owner="finance", watches=f"{SCHEMA}.gold_daily",
        means="Completed rides on the latest day with no fare attached. Every one of "
              "these is money that happened and cannot be reported.",
        unit="rides", fixed_baseline=0,
        current_sql=f"""
            SELECT count(*) FROM {SCHEMA}.bronze_trips t
            LEFT JOIN {SCHEMA}.bronze_events e ON e.trip_id = t.trip_id AND e.event = 'completed'
            WHERE t.status = 'completed' AND e.fare IS NULL
              AND t.trip_date = (SELECT max(trip_date) FROM {SCHEMA}.bronze_trips)"""),
    Signal(
        name="surge_missing_pct", owner="pricing", watches=f"{SCHEMA}.bronze_driver_app",
        means="Share of driver app records with no surge value. This is the one that "
              "moves when the mobile team renames a field without telling anybody.",
        unit="%", fixed_baseline=0,
        current_sql=f"""
            SELECT coalesce(round(100.0 * count(*) FILTER (WHERE surge IS NULL)
                   / nullif(count(*), 0), 3), 0) FROM {SCHEMA}.bronze_driver_app"""),
]

Z_THRESHOLD = 4.0


def one(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def collect() -> list[Signal]:
    """Run every signal and work out which ones have moved."""
    with psycopg.connect(dsn()) as c, c.cursor() as cur:
        for s in SIGNALS:
            try:
                s.value = one(cur, s.current_sql)
            except Exception as e:
                s.detail = f"could not run: {type(e).__name__}"
                continue

            if s.fixed_baseline is not None:
                # A baseline somebody decided, not one computed from history.
                # Zero held records is not an average, it is a rule.
                s.baseline = float(s.fixed_baseline)
                gap = abs(s.value - s.baseline)
                s.breached = gap > max(s.tolerance, 0.0001)
                s.z = 0.0 if not s.breached else round(gap, 3)
                s.detail = (f"expected {s.baseline:g}" if not s.tolerance
                            else f"expected {s.baseline:g} give or take {s.tolerance:g}")
            else:
                cur.execute(s.history_sql)
                hist = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
                if len(hist) < 3:
                    s.detail = f"only {len(hist)} day(s) of history, not judging yet"
                    continue
                s.baseline = statistics.mean(hist)
                spread = max(statistics.pstdev(hist), 0.01)
                s.z = (s.value - s.baseline) / spread
                s.breached = abs(s.z) > Z_THRESHOLD
                s.detail = f"{len(hist)} days of history"
    return SIGNALS


def main() -> int:
    rows = collect()
    bad = [s for s in rows if s.breached]
    print(f"\n  signal board   {len(rows)} signals, {len(bad)} breached\n")
    for s in rows:
        flag = "BREACH" if s.breached else "  ok  "
        print(f"  {flag}  {s.name:22} {s.value:>12,.3f}{s.unit:<6} "
              f"base {s.baseline:>10,.3f}  {s.detail}")
    print()
    if bad:
        for s in bad:
            print(f"  -> {s.name} is {s.owner}'s. {s.means.splitlines()[0]}")
        print()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
