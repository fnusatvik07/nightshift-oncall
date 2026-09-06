"""Put everything back, so the same lesson can be taught twice.

Every table this course builds lives in one schema. Reset drops that schema and
recreates it empty. It cannot touch the source data, because nothing here has
permission to write there and nothing here ever tries.

    python reset.py

That is the whole thing. Run it between demos, run it if a student breaks
something, run it when you are not sure what state you are in.
"""
from __future__ import annotations

import sys

import psycopg

from pipelines.lib.config import KAFKA, SCHEMA, dsn
from pipelines.lib.run import setup

# Every consumer group this course creates. A stream pipeline keeps its place
# in the queue on the broker, not in our database, so dropping our tables is
# only half a reset: the pipeline would wake up believing it had already read
# everything and quietly do nothing.
GROUPS = [
    "teach-bronze-events",   # the pipeline
    "notebook-watcher",      # notebook 10, the consumer the class writes by hand
    "just-looking",          # notebook 10, the metadata-only consumer
]


def forget_stream_position() -> None:
    """Delete the consumer groups, so the next run starts from the beginning."""
    try:
        from confluent_kafka.admin import AdminClient
        admin = AdminClient({"bootstrap.servers": KAFKA})
        listing = admin.list_consumer_groups(request_timeout=10).result()
        existing = {g.group_id for g in listing.valid}
        todo = [g for g in GROUPS if g in existing]
        if not todo:
            print("  kafka: no saved position to forget")
            return
        for g, fut in admin.delete_consumer_groups(todo, request_timeout=15).items():
            fut.result()
            print(f"  kafka: forgot the saved position for '{g}'")
    except Exception as e:
        print(f"  kafka: could not clear the offset ({type(e).__name__}: {e})")


def what_is_there() -> list[tuple[str, int]]:
    with psycopg.connect(dsn()) as c:
        names = [r[0] for r in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name", (SCHEMA,))]
        return [(n, c.execute(f"SELECT count(*) FROM {SCHEMA}.{n}").fetchone()[0]) for n in names]


def main() -> int:
    before = what_is_there()
    if before:
        print(f"  dropping schema '{SCHEMA}':")
        for n, k in before:
            print(f"    {n:24} {k:>10,} rows")
    else:
        print(f"  schema '{SCHEMA}' is already empty")

    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    setup()
    forget_stream_position()

    print(f"\n  '{SCHEMA}' recreated, empty. The source data was never touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
