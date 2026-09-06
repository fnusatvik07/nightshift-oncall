"""GOLD · daily.  One row per day, which is what a person actually asks for.

    reads   teach.silver_rides
    writes  teach.gold_daily
    runs    after silver

WHAT "GOLD" MEANS
    Silver is one row per ride: eighty thousand rows, all correct, and still not
    an answer. Nobody asks "show me ride TRP00042318". They ask "how did we do
    last week".

    Gold is the answer, shaped for the question. One row per day. Small enough
    to put on a dashboard without any further work.

WHAT YOU LOSE HERE, AND WHY IT MATTERS
    Look at the columns below. There is no trip_id. It has been aggregated away,
    and it is never coming back.

    That is worth saying out loud to a class, because it explains something that
    confuses people later: you cannot debug an individual broken ride by looking
    at gold. By the time data reaches here the individual has been averaged into
    a total. To find a problem you have to look further upstream, which is
    exactly why bronze and silver still exist after gold is built.

RUN IT
    python -m pipelines.p8_gold_daily
"""
from __future__ import annotations

import sys

import psycopg

from .lib.config import SCHEMA, dsn
from .lib.run import Run, setup

TABLE = "gold_daily"


# ══ STEP 1 · Describe the shape of the answer ══
#
# Every column here is something a person would actually ask for out loud. That
# is the test for a gold table: if you cannot say the column name in a sentence
# to a finance manager, it does not belong.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    trip_date       DATE PRIMARY KEY,
    rides           BIGINT,
    completed       BIGINT,
    cancelled       BIGINT,
    avg_distance_km NUMERIC(8,2),
    avg_duration_min NUMERIC(8,1),
    avg_surge       NUMERIC(6,3),
    revenue         NUMERIC(14,2),
    settled_rides   BIGINT,
    unsettled_rides BIGINT
);
"""


# ══ STEP 2 · Aggregate, using FILTER instead of three separate queries ══
#
# `count(*) FILTER (WHERE ...)` counts only the rows matching a condition, in
# the same pass as everything else. The alternative is three queries joined
# together, which is slower and much harder to read.
#
# Two details worth pointing at:
#
#   avg() ignores NULLs by itself. avg_surge is therefore the average across
#   rides that HAVE a surge value, not across all rides with missing ones
#   counted as zero. That is what you want, and it is also why a field going
#   missing does not drag this number down: it drags the row COUNT down
#   instead, which is a different signal entirely.
#
#   coalesce(sum(fare), 0) because sum() of nothing is NULL, not zero, and a
#   day with no fares should report 0 revenue rather than an empty cell.
BUILD = f"""
SELECT
    trip_date,
    count(*)                                            AS rides,
    count(*) FILTER (WHERE status = 'completed')        AS completed,
    count(*) FILTER (WHERE status LIKE 'cancelled%%')   AS cancelled,
    round(avg(distance_km), 2)                          AS avg_distance_km,
    round(avg(duration_min), 1)                         AS avg_duration_min,
    round(avg(surge), 3)                                AS avg_surge,
    round(coalesce(sum(fare), 0), 2)                    AS revenue,
    count(*) FILTER (WHERE is_settled)                  AS settled_rides,
    count(*) FILTER (WHERE NOT is_settled)              AS unsettled_rides
FROM {SCHEMA}.silver_rides
GROUP BY trip_date
"""


# ══ STEP 3 · Rebuild it, for the same reason as silver ══
#
# Thirty rows. A full rebuild takes milliseconds. Anything cleverer would be
# complexity nobody is paying for.
def run() -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p8_gold_daily") as r:
        with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {SCHEMA}.silver_rides")
            r.rows_in = cur.fetchone()[0]
            cur.execute(f"DELETE FROM {SCHEMA}.{TABLE}")
            cur.execute(f"INSERT INTO {SCHEMA}.{TABLE} {BUILD}")
            r.rows_out = cur.rowcount
            c.commit()
        r.message = "one row per day"
    return 0


if __name__ == "__main__":
    sys.exit(run())
