"""BRONZE · ride events.  Copy the ride event stream off Kafka.

    reads   kafka     kerb.trips.lifecycle   a stream, not a table
    writes  postgres  teach.bronze_events    our copy
    runs    every 5 minutes

WHY THIS ONE IS DIFFERENT
    Pipeline 1 read a table. A table lets you ask for any part of it, any time:
    "give me the eighteenth of August". You can ask twice and get the same
    answer. You can ask for the middle and skip the ends.

    A stream does not work like that. Kafka is a queue you walk forwards
    through. There is no WHERE clause. There is no "yesterday". There is only:

        "give me everything since where I last stopped"

    So the pipeline has to remember where it stopped, and that memory lives on
    the Kafka broker, not in our database. It is called an OFFSET.

    Every strange looking decision in this file follows from that one fact.

RUN IT
    python -m pipelines.p2_bronze_events
    python -m pipelines.p2_bronze_events --from-start
"""
from __future__ import annotations

import argparse
import json
import sys

import psycopg
from confluent_kafka import Consumer, OFFSET_BEGINNING, TopicPartition

from .lib.config import KAFKA, SCHEMA, TOPIC_RIDES, dsn
from .lib.run import Run, setup

TABLE = "bronze_events"

# The consumer group name IS the memory. Kafka stores "how far has
# teach-bronze-events read" against this exact string. Change the string and
# you have amnesia: the pipeline believes it has never read anything.
GROUP = "teach-bronze-events"


# ══ STEP 1 · Describe the table, with a key that makes replays harmless ══
#
# Look at the PRIMARY KEY. It is not a single id column, it is the pair
# (trip_id, event).
#
# That is a statement about the real world: a given ride can only ever have one
# "completed" event. Saying that in the table definition means that if the same
# message arrives twice, the database itself refuses the duplicate. We do not
# have to write any code to deduplicate, and we cannot forget to.
#
# STEP 5 explains why a message arriving twice is not just possible but
# expected, and therefore why this key is not optional.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    trip_id     TEXT NOT NULL,
    event       TEXT NOT NULL,        -- requested, accepted, driver_arrived, started, completed
    happened_at TIMESTAMPTZ,
    driver_id   TEXT,
    fare        NUMERIC(10,2),        -- only present on the 'completed' event
    PRIMARY KEY (trip_id, event)      -- the whole reason a replay is boring
);
"""


# ══ STEP 2 · The contract for a message ══
#
# A message off a stream is a blob of JSON that somebody else's code produced.
# It might not even be JSON. It might be JSON with the fields missing.
#
# These three are the fields without which the message is meaningless: we would
# not know which ride it belongs to, what happened, or when. Anything missing
# one of them is held rather than landed with holes in it.
REQUIRED = ("trip_id", "event", "ts")


# ══ STEP 3 · Open the consumer, with auto-commit turned OFF ══
#
# This function is four lines of configuration and one of them is the single
# most important line in the whole file.
#
#   enable.auto.commit = False
#
# By default, the Kafka library quietly saves your position on a timer, in the
# background, whether or not your database write succeeded. Picture the order:
#
#   1. library reads 5,000 messages
#   2. library's timer fires and saves "I have read up to here"
#   3. your process dies before writing them to Postgres
#
# Those 5,000 messages are gone. Not delayed, gone. The next run starts after
# them, and nobody will ever know they existed, because there is no error and
# no gap that anything can detect.
#
# Turning it off means WE decide when the position is saved, and we do it in
# STEP 5, after the rows are safely written.
def open_consumer(from_start: bool) -> Consumer:
    consumer = Consumer({
        "bootstrap.servers": KAFKA,
        "group.id": GROUP,                # the name our position is stored under
        "auto.offset.reset": "earliest",  # if we have never read before, start at the beginning
        "enable.auto.commit": False,      # WE commit, after the write. See above.
    })

    if from_start:
        # Deliberately ignore the saved position and replay the whole topic.
        # Used to prove the table survives seeing every message twice.
        parts = consumer.list_topics(TOPIC_RIDES, timeout=10).topics[TOPIC_RIDES].partitions
        consumer.assign([TopicPartition(TOPIC_RIDES, p, OFFSET_BEGINNING) for p in parts])
    else:
        # Normal operation: subscribe, and Kafka hands us everything after our
        # last committed position.
        consumer.subscribe([TOPIC_RIDES])
    return consumer


# ══ STEP 4 · Turn one raw message into one row, or hold it ══
#
# Everything here is defensive, because every single value came from outside our
# control. `m.value()` might be malformed JSON. The JSON might be missing
# fields. Neither of those should stop the pipeline: one poison message must
# never block the other four hundred thousand behind it.
#
# So: try to parse, check the contract, and if either fails, hold that one
# message and carry on with the rest.
def parse(m, run: Run):
    try:
        d = json.loads(m.value())
        missing = [k for k in REQUIRED if d.get(k) in (None, "")]
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")
    except Exception as e:
        run.quarantine(
            payload={"raw": (m.value() or b"").decode("utf8", "replace")[:400],
                     "partition": m.partition(), "offset": m.offset()},
            reason=str(e))
        return None

    # .get() for the optional fields, [] for the required ones. That is not
    # style: a required field missing here would already have been caught above,
    # so [] failing loudly would mean our own contract check has a hole in it.
    return (d["trip_id"], d["event"], d["ts"], d.get("driver_id"), d.get("fare"))


INSERT = f"""
    INSERT INTO {SCHEMA}.{TABLE} (trip_id, event, happened_at, driver_id, fare)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING          -- the same (trip, event) twice is fine, keep the first
"""


# ══ STEP 5 · Read, write, and only then save your position ══
#
# The order of the last three lines of this loop is the whole lesson.
#
#   write the rows to Postgres          <- first
#   commit the Kafka offset             <- only after the write succeeded
#
# Get it this way round and a crash in between means those messages are
# delivered again next time. We see them twice. Because of the primary key in
# STEP 1, seeing them twice changes nothing.
#
# Get it the other way round and a crash means those messages are gone forever.
#
#     duplicates you can remove.
#     missing data you cannot invent.
#
# That is the trade, and it is not close. This is called "at-least-once"
# delivery, and it is what almost every real streaming pipeline chooses.
def run(from_start: bool = False, idle_seconds: float = 3.0) -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p2_bronze_events") as r:
        consumer = open_consumer(from_start)
        try:
            # Prove the broker is actually there before reading from it.
            #
            # Without this, a broker that is down looks exactly like a topic we
            # have caught up with: consume() returns nothing, the loop ends,
            # and the run reports success having moved zero rows. That is the
            # precise failure this whole course argues against, so the pipeline
            # is not allowed to commit it.
            consumer.list_topics(TOPIC_RIDES, timeout=10)

            while True:
                # Ask for a batch. If nothing arrives within idle_seconds we
                # have caught up, and catching up is how this pipeline ends.
                batch = consumer.consume(num_messages=5000, timeout=idle_seconds)
                if not batch:
                    break

                rows = []
                for m in batch:
                    if m.error():
                        continue
                    r.rows_in += 1
                    parsed = parse(m, r)
                    if parsed is not None:
                        rows.append(parsed)

                if rows:
                    # FIRST: make the rows durable, in their own transaction.
                    with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
                        cur.executemany(INSERT, rows)
                        c.commit()
                    r.rows_out += len(rows)

                # ONLY NOW is it true that we have consumed these messages, so
                # only now do we say so. asynchronous=False means we wait for
                # the broker to confirm before moving on.
                consumer.commit(asynchronous=False)
        finally:
            # Always close, even if something above threw. An open consumer
            # holds its partitions and the next run will sit and wait for them.
            consumer.close()

        r.message = "offsets committed after the write, never before"
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-start", action="store_true",
                    help="ignore the saved position and replay the whole topic")
    return run(ap.parse_args().from_start)


if __name__ == "__main__":
    sys.exit(main())
