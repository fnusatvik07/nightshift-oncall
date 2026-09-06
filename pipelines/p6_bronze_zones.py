"""BRONZE · zones.  A small reference table, copied whole every time.

    reads   postgres  kerb.zones      61 rows
    writes  postgres  teach.bronze_zones
    runs    daily

WHY THIS ONE LOOKS TOO SIMPLE
    It is thirty lines and it has no window, no offset and no contract check.
    That is the lesson.

    Every other bronze pipeline in this course rebuilds a WINDOW, because the
    source has hundreds of thousands of rows and copying all of them hourly
    would be absurd.

    This one has sixty one rows. A full copy takes four milliseconds. Adding
    incremental logic here would be complexity nobody is paying for, and worse,
    it would be complexity a reader has to understand before they can trust the
    table.

    There are two kinds of table in every warehouse and they get different
    treatment:

        FACTS       things that happened      millions of rows, always growing
                    rides, events, payments   rebuild a window

        DIMENSIONS  things that ARE           tens or hundreds of rows, slowly
                    zones, drivers, vehicles  changing. copy the lot

    Knowing which one you are holding is most of the design decision, and
    getting it wrong in either direction is expensive: a windowed dimension is
    over-engineered, and a fully rebuilt fact table takes four hours.

RUN IT
    python -m pipelines.p6_bronze_zones
"""
from __future__ import annotations

import sys

import psycopg

from .lib.config import SCHEMA, dsn
from .lib.run import Run, setup

TABLE = "bronze_zones"


# ══ STEP 1 · Describe the dimension ══
#
# Note there is no date column anywhere. A dimension is not "what happened on
# Tuesday", it is "what is true right now". There is nothing to partition by
# and nothing to window over.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    zone_id     INT PRIMARY KEY,
    zone_name   TEXT,
    borough     TEXT,
    zone_type   TEXT
);
"""


# ══ STEP 2 · Replace the whole thing, inside one transaction ══
#
# DELETE everything, INSERT everything, commit once.
#
# This is called a full snapshot, and for sixty one rows it is exactly right.
# The transaction still matters for the same reason it always does: a reader
# who queries halfway through must never see an empty table.
#
# What we lose by doing this: history. If a zone is renamed, the old name is
# gone and nothing records that it ever existed. That is usually fine for
# reference data, and when it is not, the technique you reach for is called a
# slowly changing dimension. Worth naming so the class has heard the phrase,
# not worth building today.
def run() -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p6_bronze_zones") as r:
        with psycopg.connect(dsn()) as c:
            rows = c.execute("""
                SELECT zone_id, zone_name, borough, zone_type
                FROM kerb.zones ORDER BY zone_id
            """).fetchall()
        r.rows_in = len(rows)

        with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
            cur.execute(f"DELETE FROM {SCHEMA}.{TABLE}")
            cur.executemany(
                f"INSERT INTO {SCHEMA}.{TABLE} (zone_id, zone_name, borough, zone_type)"
                f" VALUES (%s,%s,%s,%s)", rows)
            c.commit()

        r.rows_out = len(rows)
        r.message = "full snapshot, no window: this is a dimension, not a fact"
    return 0


if __name__ == "__main__":
    sys.exit(run())
