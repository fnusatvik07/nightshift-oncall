"""SILVER · rides.  Four bronze copies become one clean row per ride.

    reads   teach.bronze_trips, bronze_events, bronze_driver_app,
            bronze_settlements, bronze_zones
    writes  teach.silver_rides
    runs    after all four bronze pipelines have finished

WHAT "SILVER" MEANS
    Bronze is four separate copies of four separate systems. Useful for
    debugging, useless for answering a question, because the answer to almost
    anything lives across two or three of them.

    Silver is where they become one row per real world thing. One row per RIDE,
    carrying its fare from the event stream, its surge from the driver app, and
    its settlement from the processor.

    Silver is also where cleaning is allowed for the first time. Bronze was
    forbidden from having opinions so that "did we break it or did they send it
    broken" always has an answer. By silver we have that answer, so now we can
    type things properly, convert units, and drop columns nobody needs.

WHY THIS PIPELINE IS ONLY SQL
    The four bronze pipelines were Python because they had to speak to Kafka,
    MongoDB and HTTP. This one does not: everything is already in the same
    database. Once data is in one place, the database is better at joining it
    than you are. Do not pull a million rows into Python to line them up.

RUN IT
    python -m pipelines.p7_silver_rides
"""
from __future__ import annotations

import sys

import psycopg

from .lib.config import SCHEMA, dsn
from .lib.run import Run, setup

TABLE = "silver_rides"


# ══ STEP 1 · Describe one clean row per ride ══
#
# Compare this to bronze_trips. Three differences worth pointing at:
#
#   duration_s became duration_min   a unit conversion, which bronze was not
#                                    allowed to do and silver is
#   fare, surge, settled_net         columns that did not exist in any single
#                                    source. They are the whole point of silver
#   no rider_id                      dropped, because nothing downstream uses it
#                                    and carrying a personal identifier you do
#                                    not need is a liability, not an asset
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    trip_id      TEXT PRIMARY KEY,
    trip_date    DATE NOT NULL,
    status       TEXT,
    driver_id    TEXT,
    pickup_zone  INT,
    pickup_zone_name TEXT,        -- from the zones dimension, see STEP 2
    pickup_borough   TEXT,        -- an id nobody can read is not an answer
    distance_km  NUMERIC(8,2),
    duration_min NUMERIC(8,1),    -- converted from seconds, see STEP 2
    fare         NUMERIC(10,2),   -- from the event stream
    surge        NUMERIC(6,2),    -- from the driver app
    settled_net  NUMERIC(12,2),   -- from the payment processor
    is_settled   BOOLEAN          -- a plain yes/no, so nobody downstream has to guess
);
CREATE INDEX IF NOT EXISTS ix_{TABLE}_date ON {SCHEMA}.{TABLE} (trip_date);
"""


# ══ STEP 2 · The join, and the single most expensive word in data engineering ══
#
# Read the three LEFT JOINs. Every one of them is deliberate, and changing any
# one to INNER would be a silent, unlogged, error-free data loss bug.
#
#   LEFT JOIN bronze_events     a cancelled ride has no 'completed' event.
#                               INNER would delete every cancelled ride.
#
#   LEFT JOIN bronze_driver_app not every ride has a driver app record.
#                               INNER would delete the rest.
#
#   LEFT JOIN bronze_settlements settlement is T+2, so recent rides have none
#                                yet. INNER would delete the last two days of
#                                trading, every single run.
#
# Now picture how that failure presents itself in production:
#
#     no error. no failed run. no log line. the number is just smaller.
#
# Somebody changes a join to make a query faster, the ride count drops four
# percent, and it takes three weeks to notice and a day to find. A wrong answer
# that runs successfully is worse than a crash, because a crash tells you.
#
# The `AND e.event = 'completed'` sits in the ON clause, not in a WHERE. In a
# WHERE it would filter out the null rows the LEFT JOIN just carefully kept,
# quietly turning it back into an inner join. That is a classic, and it is worth
# showing a class both versions side by side.
BUILD = f"""
SELECT
    t.trip_id,
    t.trip_date,
    t.status,
    t.driver_id,
    t.pickup_zone,
    z.zone_name                             AS pickup_zone_name,
    z.borough                               AS pickup_borough,
    t.distance_km,
    round(t.duration_s / 60.0, 1)          AS duration_min,
    e.fare,
    a.surge,
    s.net                                   AS settled_net,
    (s.settlement_id IS NOT NULL)           AS is_settled
FROM {SCHEMA}.bronze_trips t
LEFT JOIN {SCHEMA}.bronze_events e
       ON e.trip_id = t.trip_id
      AND e.event = 'completed'             -- in the ON, never the WHERE
LEFT JOIN {SCHEMA}.bronze_driver_app a
       ON a.trip_id = t.trip_id
LEFT JOIN {SCHEMA}.bronze_settlements s
       ON s.trip_id = t.trip_id
      AND s.status = 'settled'
-- The dimension join. LEFT again, for a reason worth saying out loud: about
-- 0.4% of rides never resolved to a service zone, so pickup_zone is NULL on
-- them. An INNER JOIN here would delete every one of those rides and the count
-- would just be smaller. That is INC-05 in the architecture course, and it is
-- the single most common way a dimension join loses data.
LEFT JOIN {SCHEMA}.bronze_zones z
       ON z.zone_id = t.pickup_zone
"""


# ══ STEP 3 · Rebuild the whole table, and be honest about why ══
#
# Bronze rebuilt a WINDOW of days because the source table is enormous. Here we
# delete everything and rebuild it, which would be indefensible at real scale.
#
# It is defensible here because silver_rides holds eighty thousand rows and the
# rebuild takes under a second. Being clever about incremental windows would
# cost more in explanation than it saves in runtime, and a lesson that is
# harder to read than it needs to be is a worse lesson.
#
# When this table reaches tens of millions, it grows a window exactly like
# bronze did. That is the honest answer: the technique is not "always full
# rebuild", it is "match the technique to the size, and say which you chose".
def run() -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p7_silver_rides") as r:
        with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {SCHEMA}.bronze_trips")
            r.rows_in = cur.fetchone()[0]

            # Both statements inside one transaction. A crash between them
            # rolls back the delete too, so the table is never empty for a
            # reader. Same idea as write_window, just over the whole table.
            cur.execute(f"DELETE FROM {SCHEMA}.{TABLE}")
            cur.execute(f"INSERT INTO {SCHEMA}.{TABLE} {BUILD}")
            r.rows_out = cur.rowcount
            c.commit()

        r.message = "one clean row per ride"
    return 0


if __name__ == "__main__":
    sys.exit(run())
