"""BRONZE · rides.  Copy the ride table out of the app database, untouched.

    reads   postgres  kerb.trips           somebody else's live table
    writes  postgres  teach.bronze_trips   our copy
    runs    hourly

WHAT "BRONZE" MEANS
    Bronze is the landing layer. Its only job is to get a faithful copy of the
    source into our own database as fast as possible, with as few opinions as
    possible. We do not clean here. We do not join here. We do not rename
    columns to something nicer here.

    Why so strict? Because the moment bronze starts having opinions, you can no
    longer answer the question "is this wrong because the source sent it wrong,
    or because we broke it on the way in?" Bronze exists so that question always
    has an answer.

    The one exception is the contract check in STEP 4. A value we cannot read at
    all is held rather than landed, because landing a value nobody can interpret
    is not faithfulness, it is just deferring the problem.

RUN IT
    python -m pipelines.p1_bronze_trips
    python -m pipelines.p1_bronze_trips --days 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import psycopg

from .lib.config import SCHEMA, dsn
from .lib.run import Run, setup, write_window

TABLE = "bronze_trips"


# ══ STEP 1 · Describe the table we are going to fill ══
#
# The table is created by the pipeline itself, not by a human running SQL by
# hand at some point in the past that nobody wrote down. "CREATE TABLE IF NOT
# EXISTS" means a brand new laptop and a three year old production database end
# up with exactly the same shape.
#
# Every column below maps to one column in the source. Nothing is invented,
# nothing is renamed for taste. `trip_date` is the only derived column, and it
# exists because we need something to partition on in STEP 6.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    trip_id      TEXT PRIMARY KEY,   -- one row per ride, enforced by the database
    trip_date    DATE NOT NULL,      -- derived from requested_at, used to rebuild a window
    rider_id     TEXT,
    driver_id    TEXT,               -- empty until a driver accepts, so it is nullable
    pickup_zone  INT,
    distance_km  NUMERIC(8,2),
    duration_s   INT,                -- kept in seconds, exactly as the source has it
    status       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_{TABLE}_date ON {SCHEMA}.{TABLE} (trip_date);
"""


# ══ STEP 2 · Write down the contract ══
#
# A contract is the set of values we already know how to interpret. It is not a
# validation rule and it is not a preference: it is a written record of what the
# rest of the company has agreed a ride can be.
#
# These four are the only ways a ride can end. If a fifth ever appears, one of
# two things has happened: the product team shipped a new state and forgot to
# tell anybody, or something upstream is corrupting the field. Both of those are
# things you want to hear about on the day, not in three weeks.
KNOWN_STATUS = {"completed", "cancelled_rider", "cancelled_driver", "no_driver"}


# ══ STEP 3 · Decide which window of days to rebuild ══
#
# A pipeline never reads the whole table. In six months kerb.trips has fifty
# million rows and copying all of them hourly is absurd. We rebuild a small
# window of recent days, over and over.
#
# The trap is choosing the window. The obvious answer is "the last N days,
# counting back from today", and it is wrong here, twice over:
#
#   Using today's date fails because a teaching dataset is generated once and
#   then sits still. Ask it for yesterday and you get nothing, and you spend
#   twenty minutes wondering why your pipeline reads zero rows.
#
#   Using max(date) fails because one stray test row dated next year drags the
#   anchor to a day that contains a single ride.
#
# So we anchor on the newest day that actually looks like a day of trading.
def choose_window(days: int) -> tuple[dt.date, dt.date]:
    with psycopg.connect(dsn()) as c:
        newest = c.execute("""
            SELECT date(requested_at)
            FROM kerb.trips
            GROUP BY 1
            HAVING count(*) > 100        -- ignore days with a handful of stray rows
            ORDER BY 1 DESC
            LIMIT 1
        """).fetchone()[0]

    # lo is inclusive, hi is exclusive. Always. Mixing those up is how you get
    # a pipeline that double counts one day every single run.
    lo = newest - dt.timedelta(days=days - 1)
    hi = newest + dt.timedelta(days=1)
    return lo, hi


# ══ STEP 4 · Read the window out of the source ══
#
# One query, one window. Note there is no JOIN here and no aggregation: bronze
# copies one source table and nothing else. If you find yourself joining in a
# bronze pipeline, you are building silver and should say so.
READ = """
    SELECT trip_id,
           date(requested_at) AS trip_date,
           rider_id,
           driver_id,
           pu_zone_id,
           distance_km,
           duration_s,
           status
    FROM kerb.trips
    WHERE requested_at >= %s        -- inclusive
      AND requested_at <  %s        -- exclusive
    ORDER BY requested_at
"""


# ══ STEP 5 · Sort every record into one of two piles ══
#
# This is the heart of the pipeline and the place people get wrong.
#
# For each row there are only three possible responses to a value we do not
# recognise, and two of them are lies:
#
#   Drop it        the row count is quietly smaller and nobody ever finds out
#   Default it     a number appears on a finance report that never happened
#   Hold it        the warehouse is briefly incomplete, and somebody can see why
#
# Only the third is honest. `run.quarantine` keeps the record, the reason, and
# the original payload, so the person who picks it up tomorrow has everything
# they need and does not have to guess.
def sort_records(rows: list, run: Run) -> list:
    keep = []
    for trip_id, trip_date, rider, driver, zone, km, secs, status in rows:
        if status not in KNOWN_STATUS:
            run.quarantine(
                payload={"trip_id": trip_id, "status": status, "trip_date": str(trip_date)},
                reason=f"status {status!r} is not one of {sorted(KNOWN_STATUS)}",
                key=trip_id)
            continue
        keep.append((trip_id, trip_date, rider, driver, zone, km, secs, status))
    return keep


INSERT = f"""
    INSERT INTO {SCHEMA}.{TABLE}
        (trip_id, trip_date, rider_id, driver_id, pickup_zone, distance_km, duration_s, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


# ══ STEP 6 · Write the window, all at once or not at all ══
#
# This is what makes the pipeline safe to run twice, and it is four lines.
#
# Instead of appending, we DELETE the window we are about to rebuild and INSERT
# the new rows inside the same transaction. Two properties fall out for free:
#
#   Run it twice and you get the same table, not double the rows. The delete
#   removes what the previous run wrote before the insert puts it back.
#
#   Kill it halfway and the delete is rolled back along with the insert, so a
#   reader never sees a table with a hole in it. There is no moment where the
#   data is half deleted.
#
# `write_window` in lib/run.py is those four lines, written once so that every
# pipeline gets it right without thinking about it.
def run(days: int = 7) -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    lo, hi = choose_window(days)

    with Run("p1_bronze_trips") as r:
        with psycopg.connect(dsn()) as c:
            rows = c.execute(READ, (lo, hi)).fetchall()
        r.rows_in = len(rows)

        keep = sort_records(rows, r)

        with write_window(TABLE, "trip_date", lo, hi) as cur:
            cur.executemany(INSERT, keep)

        r.rows_out = len(keep)
        r.message = f"window {lo} to {hi}"
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=7,
                    help="how many days back to rebuild (default 7)")
    return run(ap.parse_args().days)


if __name__ == "__main__":
    sys.exit(main())
