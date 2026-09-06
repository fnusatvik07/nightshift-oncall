"""BRONZE · driver app.  Copy the driver phone's documents out of MongoDB.

    reads   mongodb   kerb_app.driver_app_events   documents, not rows
    writes  postgres  teach.bronze_driver_app      our copy, flattened
    runs    hourly

WHY THIS ONE IS DIFFERENT
    A PostgreSQL table has a shape the database enforces. Try to put a word in a
    numeric column and it refuses.

    MongoDB does not do that, deliberately. A document can contain anything, and
    the mobile team can ship a release on Tuesday that renames a field without
    a single thing anywhere complaining. That is not a flaw. It is the trade you
    accept for being able to store whatever the app sends.

    But somebody still has to do the job the database is not doing, and that
    somebody is this pipeline. STEP 2 is where it happens.

RUN IT
    python -m pipelines.p3_bronze_driver_app
"""
from __future__ import annotations

import argparse
import sys

import psycopg
from pymongo import MongoClient

from .lib.config import MONGO_URI, SCHEMA, dsn
from .lib.run import Run, setup

TABLE = "bronze_driver_app"


# ══ STEP 1 · Describe the flat table we are landing into ══
#
# The source is nested documents. The target is a flat table. Someone has to
# decide which nested values become columns, and that decision is this DDL.
#
# We take six fields out of a document that has twenty. That is on purpose:
# bronze copies what the business has agreed it needs, not everything that
# happens to exist. Landing every field of every document gives you a table
# nobody can read and a schema that changes under you every release.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    event_id    TEXT PRIMARY KEY,     -- the app's own id, so a re-read is harmless
    trip_id     TEXT,                 -- how this joins to rides later
    driver_id   TEXT,
    event_type  TEXT,
    happened_at TIMESTAMPTZ,
    app_version TEXT,                 -- nested at app.version, see STEP 3
    surge       NUMERIC(6,2)          -- nested at payload.surge_multiplier, see STEP 2
);
"""


# ══ STEP 2 · The contract: every place this value has ever legitimately lived ══
#
# This tuple is the most important thing in the file, and it deserves the whole
# comment it is about to get.
#
# The pricing team depends on the surge multiplier. Today the app sends it at
# payload.surge_multiplier. Nothing anywhere guarantees it stays there.
#
# Now picture the failure. The mobile team ships 4.2 and moves it to
# pricing.surge_multiplier. Perfectly reasonable refactor. They do not tell the
# data team, because why would they. And then:
#
#     the pipeline does not fail        it reads the document fine
#     the rows still land               the count is unchanged
#     surge is just empty               on some rows, starting Tuesday
#     nobody notices                    for three weeks
#
# Every row count check you can write stays green through that.
#
# So we write down every path we are willing to read it from, newest naming
# first. When the team renames it again, this tuple is the one line that
# changes, and the quarantine in STEP 4 is what tells you it happened.
SURGE_PATHS = (
    ("payload", "surge_multiplier"),          # 4.0.6, 4.1.2 and 4.1.5. 96.8% of documents
    ("payload", "pricing", "surgeFactor"),    # 4.2.0. See below.
    ("pricing", "surge_multiplier"),          # where we GUESSED 4.2 would put it. It did not
    ("surge_multiplier",),                    # the old flat shape, kept for older documents
)

# The second path is the one to talk about.
#
# We wrote this contract expecting release 4.2 to move the value to
# pricing.surge_multiplier. It was a reasonable guess and it was wrong: 4.2
# moved it to payload.pricing.surgeFactor, a different name at a different
# depth, and four documents landed at the path we guessed.
#
# That is the real shape of this problem. You cannot predict where a field will
# go. What you can do is notice, on the day, that some documents match none of
# your known paths, because those documents are sitting in quarantine with the
# reason attached. Notebook 4 walks through finding this one.


# ══ STEP 3 · Walk a nested path safely ══
#
# doc["payload"]["surge_multiplier"] raises KeyError if either level is missing,
# and one KeyError would stop the whole run over a single odd document.
#
# So we walk the path one key at a time and return None the moment a level is
# not there. None means "not found", which STEP 4 then decides what to do about.
def dig(doc: dict, path: tuple):
    cur = doc
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def surge_of(doc: dict):
    """The surge value, from whichever field this app version happened to use."""
    for path in SURGE_PATHS:
        value = dig(doc, path)
        if value is not None:
            return value
    return None      # none of the known paths matched. STEP 4 handles it.


INSERT = f"""
    INSERT INTO {SCHEMA}.{TABLE}
        (event_id, trip_id, driver_id, event_type, happened_at, app_version, surge)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (event_id) DO NOTHING
"""


# ══ STEP 4 · Read the documents, and never default a missing value ══
#
# When surge_of returns None we hold the document. We do NOT write a zero.
#
# That distinction is worth a minute in class, because it looks pedantic and is
# not. Consider a report that averages surge:
#
#     a zero meaning "there genuinely was no surge on this ride"
#     a zero meaning "we could not find the field"
#
# Those are indistinguishable once written. The first is a fact. The second is a
# lie that drags the average down and quietly misprices the product.
#
# Holding it costs you an incomplete table for a day. Defaulting it costs you a
# wrong number forever, with nothing to point at.
def run(limit: int = 40000) -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p3_bronze_driver_app") as r:
        collection = MongoClient(MONGO_URI).kerb_app.driver_app_events

        rows = []
        # sort newest first, NOT natural order. A collection returns its oldest
        # documents first, and the oldest documents describe rides that fell out
        # of the bronze window weeks ago. Read from the wrong end and every
        # column you worked for arrives full of nulls in silver, with no error
        # anywhere. There is a compound index on (event_type, ts), so this costs
        # nothing.
        for doc in collection.find({"event_type": "trip_offer"}).sort("ts", -1).limit(limit):
            r.rows_in += 1

            surge = surge_of(doc)
            if surge is None:
                r.quarantine(
                    payload={k: str(v)[:80] for k, v in list(doc.items())[:8]},
                    reason=("no surge value at any known path: "
                            + ", ".join(".".join(p) for p in SURGE_PATHS)),
                    key=str(doc.get("event_id") or doc.get("_id")))
                continue

            rows.append((
                str(doc.get("event_id") or doc["_id"]),
                doc.get("trip_id"),
                doc.get("driver_id"),
                doc.get("event_type"),
                doc.get("ts"),
                dig(doc, ("app", "version")),   # also nested, same problem, same solution
                surge))

        # ══ STEP 5 · Write in one batch, not one row at a time ══
        #
        # The first version of this pipeline opened a fresh database connection
        # for every held record. Forty thousand of them took 212 seconds.
        # Batching made it 0.7. Same code, same result, three hundred times
        # faster.
        #
        # The lesson is not "batch your writes". It is: when something is
        # inexplicably slow, count how many times you are opening a connection.
        if rows:
            with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
                cur.executemany(INSERT, rows)
                c.commit()

        r.rows_out = len(rows)
        r.message = f"surge read from {len(SURGE_PATHS)} known field paths"
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=40000)
    return run(ap.parse_args().limit)


if __name__ == "__main__":
    sys.exit(main())
