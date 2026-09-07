"""The KPI catalogue.

## A KPI is not a signal

This is the distinction the whole service rests on, and it is worth being
pedantic about because people use the words interchangeably and then cannot
work out why their alerting is useless.

    A KPI      is a number with a definition and an owner.
               "revenue yesterday" is a KPI. It is never wrong. It cannot fire.

    A SIGNAL   is a KPI plus a baseline plus a tolerance.
               "revenue yesterday, which is normally 1.9 million" can breach.

You cannot alert on a KPI, because a number on its own has no opinion about
itself. You can only alert on a KPI once somebody has said what normal looks
like, and that sentence is the part nobody wants to write.

## The rules for a KPI in this catalogue

**One query. One number.** If it returns a table it is a report, not a KPI. If
it returns two numbers it is two KPIs.

**It has an owner who exists.** A person or a named team. "the data team" is not
an owner, it is a way of making sure nobody looks.

**`means` is written for the owner, not for you.** They will read it at 3am
having never seen this code.

**It reads the warehouse, never a source.** Bands 3 and 4 of the architecture:
the services only ever read the copy. A KPI that queries kerb.trips directly is
competing with riders for the app database, which is the thing the warehouse was
built to stop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pipelines.lib.config import SCHEMA

Judgement = Literal["fixed", "history"]


@dataclass(frozen=True)
class KPI:
    """One number, defined once."""

    name: str
    title: str                     # the same thing, in words
    owner: str                     # a team that exists
    watches: str                   # the table it reads
    means: str                     # written for the owner
    sql: str                       # returns exactly one row, one column

    unit: str = ""
    judgement: Judgement = "history"

    # for judgement="fixed": what it should be, and how far off is still fine
    baseline: float | None = None
    tolerance: float = 0.0

    # for judgement="history": the query returning previous readings
    history_sql: str = ""
    z_threshold: float = 4.0

    # what a breach is worth waking somebody for
    severity: str = "medium"
    # which direction is bad. Some numbers are only bad when they rise.
    watch_direction: Literal["both", "above", "below"] = "both"

    tags: tuple[str, ...] = field(default_factory=tuple)


# ═══════════════════════════════════════════════════════════════════════════
# The catalogue.
#
# Thirteen KPIs, in four groups, because between them they answer the four
# questions that actually go wrong:
#
#     did the work happen          freshness, pipelines, held records
#     is the volume right          rides, revenue, events per ride
#     is the shape right           completion, cancellation, average fare
#     is anything missing          surge, fare, zone and settlement coverage
# ═══════════════════════════════════════════════════════════════════════════

CATALOGUE: list[KPI] = [

    # ── did the work happen ────────────────────────────────────────────────
    KPI(
        name="pipelines_failing",
        title="Pipelines whose last run failed",
        owner="data-platform",
        watches=f"{SCHEMA}.runs",
        means="How many pipelines failed on their most recent run. The only KPI "
              "here that does not look at data at all: it asks whether the work "
              "happened. A pipeline that never ran leaves perfectly valid data "
              "behind, and no check of values will ever notice.",
        unit=" runs",
        judgement="fixed", baseline=0, severity="critical",
        watch_direction="above",
        sql=f"""
            SELECT count(*)::float FROM (
                SELECT DISTINCT ON (pipeline) pipeline, status
                FROM {SCHEMA}.runs ORDER BY pipeline, started_at DESC) x
            WHERE status <> 'success'
        """,
        tags=("freshness", "platform"),
    ),
    KPI(
        name="warehouse_lag_hours",
        title="Age of the newest day in gold",
        owner="data-platform",
        watches=f"{SCHEMA}.gold_daily",
        means="How many hours old the newest row in gold is, measured against "
              "the newest ride we actually hold. A number that climbs while the "
              "pipelines all report success means they are running and reading "
              "nothing.",
        unit=" h",
        judgement="fixed", baseline=0, tolerance=30, severity="high",
        watch_direction="above",
        sql=f"""
            -- subtracting two dates gives whole days, not an interval, so this
            -- multiplies rather than calling extract(epoch ...) on an integer
            SELECT coalesce((
                       (SELECT max(trip_date) FROM {SCHEMA}.bronze_trips)
                     - (SELECT max(trip_date) FROM {SCHEMA}.gold_daily)
                   )::float * 24.0, 0)::float
        """,
        tags=("freshness",),
    ),
    KPI(
        name="records_held",
        title="Records a contract refused",
        owner="data-platform",
        watches=f"{SCHEMA}.quarantine",
        means="Records held because no contract could read them. Not lost, not "
              "wrong, just not published. Any number above zero means the "
              "warehouse is behind reality and somebody has to decide what the "
              "value meant.",
        unit=" rows",
        judgement="fixed", baseline=0, severity="medium",
        watch_direction="above",
        # The latest run of each pipeline, not every run ever. Quarantine is
        # append only, so counting the whole table means the number climbs on
        # every run and never comes back down once something has been fixed.
        # A signal that cannot return to healthy is not a signal, it is a
        # counter, and people learn to ignore it.
        sql=f"""
            SELECT count(*)::float FROM {SCHEMA}.quarantine
            WHERE run_id IN (SELECT DISTINCT ON (pipeline) run_id
                             FROM {SCHEMA}.runs WHERE status = 'success'
                             ORDER BY pipeline, started_at DESC)
        """,
        tags=("contracts",),
    ),

    # ── is the volume right ────────────────────────────────────────────────
    KPI(
        name="rides_per_day",
        title="Rides on the most recent day",
        owner="operations",
        watches=f"{SCHEMA}.gold_daily",
        means="Completed and cancelled rides on the newest day we hold, against "
              "the days before it. Catches a feed that stopped, a window built "
              "wrong, and a genuinely quiet Tuesday. Only two of those three are "
              "your problem.",
        unit=" rides", severity="high",
        sql=f"SELECT rides::float FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1",
        history_sql=f"SELECT rides::float FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1",
        tags=("volume",),
    ),
    KPI(
        name="revenue_per_day",
        title="Revenue on the most recent day",
        owner="finance",
        watches=f"{SCHEMA}.gold_daily",
        means="Fares collected on the newest day. This is the number that ends up "
              "in a board pack, so it is the one where being quietly wrong for "
              "three weeks costs the most.",
        unit="", severity="critical",
        sql=f"SELECT revenue::float FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1",
        history_sql=f"SELECT revenue::float FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1",
        tags=("money",),
    ),
    KPI(
        name="events_per_ride",
        title="Lifecycle events per ride",
        owner="streaming",
        watches=f"{SCHEMA}.bronze_events",
        means="A completed ride emits five events and a cancelled one emits "
              "three, so the true average sits a little under five and that is "
              "correct, not a fault. Well above five means the stream was "
              "replayed and something landed twice. Far below means events are "
              "being dropped.",
        judgement="fixed", baseline=4.7, tolerance=1.0, severity="high",
        sql=f"""
            SELECT coalesce(round(count(*)::numeric
                   / nullif(count(DISTINCT trip_id), 0), 2), 0)::float
            FROM {SCHEMA}.bronze_events
        """,
        tags=("streaming",),
    ),

    # ── is the shape right ─────────────────────────────────────────────────
    KPI(
        name="completion_rate",
        title="Share of rides that completed",
        owner="operations",
        watches=f"{SCHEMA}.gold_daily",
        means="Completed rides as a share of all rides, on the newest day. Drops "
              "when drivers cannot be matched, when the app ships a bug, or when "
              "a city has a problem.",
        unit="%", severity="high",
        sql=f"""
            SELECT round(100.0 * completed / nullif(rides, 0), 2)::float
            FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1
        """,
        history_sql=f"""
            SELECT round(100.0 * completed / nullif(rides, 0), 2)::float
            FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1
        """,
        tags=("shape",),
    ),
    KPI(
        name="cancellation_rate",
        title="Share of rides cancelled",
        owner="operations",
        watches=f"{SCHEMA}.gold_daily",
        means="Cancelled rides as a share of all rides, on the newest day. A jump "
              "usually means the app shipped something or a city has a problem, "
              "and it is visible here hours before it is visible in revenue.",
        unit="%", severity="medium", watch_direction="above",
        sql=f"""
            SELECT round(100.0 * cancelled / nullif(rides, 0), 2)::float
            FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1
        """,
        history_sql=f"""
            SELECT round(100.0 * cancelled / nullif(rides, 0), 2)::float
            FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1
        """,
        tags=("shape",),
    ),
    KPI(
        name="avg_fare",
        title="Average fare on the most recent day",
        owner="pricing",
        watches=f"{SCHEMA}.gold_daily",
        means="Revenue divided by completed rides. Moves when pricing changes, "
              "when the mix of zones changes, and when surge stops being applied "
              "because the value stopped arriving.",
        unit="", severity="high",
        sql=f"""
            SELECT round(revenue / nullif(completed, 0), 2)::float
            FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1
        """,
        history_sql=f"""
            SELECT round(revenue / nullif(completed, 0), 2)::float
            FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1
        """,
        tags=("money", "pricing"),
    ),

    # ── is anything missing ────────────────────────────────────────────────
    KPI(
        name="surge_coverage_pct",
        title="Share of driver app records carrying a surge value",
        owner="pricing",
        watches=f"{SCHEMA}.bronze_driver_app",
        means="What share of driver app records arrived with a surge value we "
              "could read. This is the one that moves when the mobile team "
              "renames a field without telling anybody, and it moves without any "
              "pipeline failing and without any row count changing.",
        unit="%",
        # Tolerance of 1, not 5. In normal operation this is exactly 100.0,
        # because the pipeline HOLDS a record it cannot read a surge value from
        # rather than writing a null. So any drop at all is a real change, and a
        # generous tolerance here just means a release can move a field and
        # stay under the bar until it has affected a lot of rides.
        judgement="fixed", baseline=100.0, tolerance=1.0, severity="high",
        watch_direction="below",
        # Measured against what the pipeline was OFFERED, not against what it
        # wrote. That distinction is the whole KPI. p3 never writes a null
        # surge: a document it cannot read a surge value from is HELD, so
        # count(surge)/count(*) over the landed table is 100% by construction
        # and can never move, however badly the upstream field is renamed.
        # rows_in and rows_out on the latest run say what actually happened.
        sql=f"""
            SELECT coalesce((SELECT round(100.0 * rows_out / nullif(rows_in, 0), 2)
                             FROM {SCHEMA}.runs
                             WHERE pipeline = 'p3_bronze_driver_app'
                               AND status = 'success'
                             ORDER BY started_at DESC LIMIT 1), 100)::float
        """,
        tags=("coverage", "pricing"),
    ),
    KPI(
        name="fare_coverage_pct",
        title="Share of completed rides that have a fare",
        owner="finance",
        watches=f"{SCHEMA}.silver_rides",
        means="A completed ride with no fare is money that happened and cannot be "
              "reported. Every percentage point here is real revenue missing from "
              "the number finance publishes.",
        unit="%",
        judgement="fixed", baseline=100.0, tolerance=2.0, severity="critical",
        watch_direction="below",
        sql=f"""
            SELECT coalesce(round(100.0 * count(fare) / nullif(count(*), 0), 2), 0)::float
            FROM {SCHEMA}.silver_rides WHERE status = 'completed'
        """,
        tags=("coverage", "money"),
    ),
    KPI(
        name="zone_coverage_pct",
        title="Share of rides that resolved to a zone",
        owner="operations",
        watches=f"{SCHEMA}.silver_rides",
        means="Rides whose pickup zone matched the zone dimension. A few in a "
              "thousand never resolve and that is normal. A sudden drop means the "
              "dimension did not refresh, and every per zone report silently "
              "stopped covering the whole business.",
        unit="%",
        judgement="fixed", baseline=99.6, tolerance=2.0, severity="medium",
        watch_direction="below",
        sql=f"""
            SELECT coalesce(round(100.0 * count(pickup_zone_name) / nullif(count(*), 0), 2), 0)::float
            FROM {SCHEMA}.silver_rides
        """,
        tags=("coverage",),
    ),
    KPI(
        name="settlement_coverage_pct",
        title="Share of asked settlements the processor answered",
        owner="finance",
        watches=f"{SCHEMA}.bronze_settlements",
        means="Of the payments we asked the processor about, how many came back "
              "with a status we could file. The rest are held. A drop means the "
              "processor changed something, and money is sitting in a state no "
              "report has a column for.",
        unit="%",
        # Tolerance of 40 was too tight and this signal flapped. The processor
        # answers a large and VARIABLE share of what it is asked on any given
        # run, and everything it has not answered yet is held rather than
        # guessed, so a healthy day sits anywhere from about 40% to about 70%.
        # A signal that goes red on a healthy day teaches people to ignore it.
        # 20 is the line worth waking somebody for: below that the processor has
        # stopped answering rather than being busy.
        judgement="fixed", baseline=100.0, tolerance=80.0, severity="medium",
        watch_direction="below",
        sql=f"""
            SELECT coalesce(round(100.0 * (SELECT count(*) FROM {SCHEMA}.bronze_settlements)
                   / nullif((SELECT count(*) FROM {SCHEMA}.bronze_settlements)
                          + (SELECT count(*) FROM {SCHEMA}.quarantine
                             WHERE pipeline = 'p4_bronze_settlements'), 0), 2), 100)::float
        """,
        tags=("coverage", "money"),
    ),
]

BY_NAME: dict[str, KPI] = {k.name: k for k in CATALOGUE}


def get(name: str) -> KPI:
    if name not in BY_NAME:
        raise KeyError(f"no KPI called {name!r}. Known: {', '.join(sorted(BY_NAME))}")
    return BY_NAME[name]
