"""Fill the estate with a month of trading.

    python -m seed                 the full dataset, about three minutes
    python -m seed --quick         a smaller one, about thirty seconds
    python -m seed --force         wipe what is there and generate it again

Everything is deterministic. The same --seed gives the same rides, the same
fares and the same incidents, on any machine, so the numbers in a lesson match
the numbers on the screen.

One deliberate choice worth knowing about: the data ENDS a couple of weeks
before today, and does not run up to the current date. A pipeline that asks for
"the last seven days counting back from today" therefore reads nothing, which
is the first trap notebook 2 walks into on purpose.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time

import psycopg

from pipelines.lib.config import MONGO_URI, KAFKA, SOURCE_DB, dsn
from seed import targets, trips as trip_gen, world

DEFAULT_DAYS = 30
DEFAULT_TRIPS_PER_DAY = 12_000
DEFAULT_DRIVERS = 2_800
DEFAULT_RIDERS = 40_000
# how far in the past the dataset ends. See the module docstring.
DEFAULT_END_OFFSET = 14


def paynimbus_dsn() -> str:
    p = SOURCE_DB
    return (f"host={p['host']} port={p['port']} dbname=paynimbus "
            f"user={p['user']} password={p['password']}")


def step(label: str):
    print(f"\n  {label}")
    return time.time()


def done(t0: float, detail: str = "") -> None:
    print(f"    {time.time() - t0:5.1f}s  {detail}")


# ── guards ─────────────────────────────────────────────────────────────────

def already_seeded(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM kerb.trips")
        return cur.fetchone()[0]


def wipe(conn, pn_conn) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE kerb.payments, kerb.trips, kerb.riders, "
                    "kerb.drivers, kerb.zones RESTART IDENTITY CASCADE")
    conn.commit()
    with pn_conn.cursor() as cur:
        cur.execute("TRUNCATE settlements")
    pn_conn.commit()


# ── the run ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=int(os.environ.get("KERB_DAYS", DEFAULT_DAYS)))
    ap.add_argument("--trips-per-day", type=int,
                    default=int(os.environ.get("KERB_TRIPS_PER_DAY", DEFAULT_TRIPS_PER_DAY)))
    ap.add_argument("--seed", type=int, default=int(os.environ.get("KERB_SEED", 20260901)))
    ap.add_argument("--end-offset-days", type=int, default=DEFAULT_END_OFFSET,
                    help="how many days before today the dataset ends")
    ap.add_argument("--quick", action="store_true",
                    help="7 days of 2,000 rides, for a fast first run")
    ap.add_argument("--force", action="store_true",
                    help="wipe existing data and generate it again")
    ap.add_argument("--skip", default="", help="comma separated: mongo,stream,files")
    a = ap.parse_args()

    if a.quick:
        a.days, a.trips_per_day = 7, 2_000

    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    rng = random.Random(a.seed)

    last_day = dt.date.today() - dt.timedelta(days=a.end_offset_days)
    first_day = last_day - dt.timedelta(days=a.days - 1)

    print(f"\n  seeding {a.days} days, {a.trips_per_day:,} rides a day")
    print(f"  {first_day} to {last_day}   (the dataset ends "
          f"{a.end_offset_days} days before today, on purpose)")

    conn = psycopg.connect(dsn())
    pn_conn = psycopg.connect(paynimbus_dsn())

    existing = already_seeded(conn)
    if existing and not a.force:
        print(f"\n  kerb.trips already holds {existing:,} rides.")
        print("  Nothing was changed. Use --force to wipe and generate again.")
        return 1
    if existing:
        t0 = step("clearing what is there")
        wipe(conn, pn_conn)
        done(t0, f"removed {existing:,} rides")

    # ── the fixed world ────────────────────────────────────────────────────
    t0 = step("zones, drivers and riders")
    zones = world.zones()
    drivers = world.drivers(rng, DEFAULT_DRIVERS, first_day)
    riders = world.riders(rng, DEFAULT_RIDERS, first_day)
    targets.write_postgres(conn, zones, drivers, riders)
    done(t0, f"{len(zones)} zones, {len(drivers):,} drivers, {len(riders):,} riders")

    # ── the rides ──────────────────────────────────────────────────────────
    t0 = step("rides and payments")
    zone_weights = [float(z[4]) for z in zones]
    all_trips, all_payments = [], []
    trip_seq = pay_seq = 0

    for i in range(a.days):
        on = first_day + dt.timedelta(days=i)
        progress = i / max(1, a.days - 1)
        day_trips, day_payments, trip_seq, pay_seq = trip_gen.day(
            rng, on, progress, a.trips_per_day, DEFAULT_DRIVERS, DEFAULT_RIDERS,
            len(zones), zone_weights, trip_seq, pay_seq)
        all_trips.extend(day_trips)
        all_payments.extend(day_payments)

    targets.write_trips(conn, all_trips, all_payments)
    done(t0, f"{len(all_trips):,} rides, {len(all_payments):,} payments")

    # ── the processor's ledger ─────────────────────────────────────────────
    t0 = step("settlements, at the payment processor")
    now = dt.datetime.now(dt.timezone.utc)
    n = targets.write_settlements(pn_conn, all_payments, rng, now)
    done(t0, f"{n:,} settlements  (cash never reaches a processor)")

    # ── the driver app ─────────────────────────────────────────────────────
    if "mongo" not in skip:
        t0 = step("driver app documents, in mongodb")
        n = seed_mongo(all_trips, rng)
        done(t0, f"{n:,} documents")

    # ── the stream ─────────────────────────────────────────────────────────
    if "stream" not in skip:
        t0 = step("ride lifecycle events, on the stream")
        n = seed_stream(all_trips, rebuild=bool(existing))
        done(t0, f"{n:,} events on {targets.TOPIC}")

    # ── the regulator's files ──────────────────────────────────────────────
    if "files" not in skip:
        t0 = step("the regulator's nightly files, in object storage")
        n = seed_files(all_trips, first_day, a.days)
        done(t0, f"{n} gzipped CSV files in {targets.BUCKET}")

    conn.close()
    pn_conn.close()

    print("\n  the estate is seeded. Next:")
    print("    python cli.py status")
    print("    python cli.py run all\n")
    return 0


# ── the three systems that are not postgres ────────────────────────────────

def seed_mongo(all_trips, rng: random.Random) -> int:
    from pymongo import MongoClient

    collection = MongoClient(MONGO_URI).kerb_app.driver_app_events
    collection.drop()

    docs = targets.driver_app_docs(all_trips, rng)

    # Four documents where the surge value sits at pricing.surge_multiplier.
    #
    # That is the path the data team GUESSED release 4.2 would move it to, and
    # somebody on the mobile team started that refactor before changing their
    # mind. Four is not a rounding error, it is a fingerprint, and notebook 4
    # ends by finding exactly these.
    moved = [d for d in docs if d["app"]["version"] == "4.2.0"
             and d["event_type"] == "trip_offer"][:4]
    for d in moved:
        surge = d["payload"]["pricing"]["surgeFactor"]
        del d["payload"]["pricing"]
        d["pricing"] = {"surge_multiplier": surge}

    for i in range(0, len(docs), 5000):
        collection.insert_many(docs[i:i + 5000], ordered=False)

    # The index the pipeline relies on. Reading the newest documents first is
    # the difference between surge arriving in silver and a column of nulls.
    collection.create_index([("event_type", 1), ("ts", 1)])
    collection.create_index([("ts", 1)])
    collection.create_index([("app.version", 1)])
    return len(docs)


def seed_stream(all_trips, rebuild: bool = False) -> int:
    """Put one event per thing that happened on the topic.

    When we are regenerating, the old topic has to go first. A stream is not a
    table: truncating Postgres does nothing to the broker, and leaving the
    previous generation's events in place gives you a topic that disagrees with
    the database it is supposed to describe. That shows up later as an
    events-per-ride figure nobody can explain.
    """
    from confluent_kafka import Producer
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": KAFKA})
    existing = set(admin.list_topics(timeout=15).topics)

    if rebuild:
        doomed = [t for t in [targets.TOPIC, *targets.OTHER_TOPICS] if t in existing]
        if doomed:
            for topic, fut in admin.delete_topics(doomed, operation_timeout=30).items():
                try:
                    fut.result()
                except Exception as e:
                    print(f"    could not delete {topic}: {e}")
            # deletion is asynchronous, so wait for the broker to agree
            for _ in range(30):
                if not set(admin.list_topics(timeout=10).topics) & set(doomed):
                    break
                time.sleep(1)
            existing = set(admin.list_topics(timeout=15).topics)
            print(f"    cleared {len(doomed)} topic(s) from the broker")

    wanted = [NewTopic(targets.TOPIC, num_partitions=3, replication_factor=1)]
    wanted += [NewTopic(t, num_partitions=3 if "gps" not in t else 6,
                        replication_factor=1)
               for t in targets.OTHER_TOPICS if t not in existing]
    wanted = [t for t in wanted if t.topic not in existing]
    if wanted:
        for topic, fut in admin.create_topics(wanted).items():
            try:
                fut.result()
            except Exception as e:                       # already there is fine
                print(f"    {topic}: {e}")

    producer = Producer({"bootstrap.servers": KAFKA,
                         "linger.ms": 50,
                         "batch.num.messages": 10_000,
                         "queue.buffering.max.messages": 1_000_000})
    n = 0
    for key, value in targets.lifecycle_events(all_trips):
        while True:
            try:
                producer.produce(targets.TOPIC, key=key, value=value)
                break
            except BufferError:
                # the local queue is full, which means we are producing faster
                # than the broker is accepting. Let it drain rather than drop.
                producer.poll(0.5)
        n += 1
        if n % 200_000 == 0:
            print(f"      {n:,} events")
    producer.flush(60)
    return n


def seed_files(all_trips, first_day: dt.date, days: int) -> int:
    client = targets.minio_client()
    if not client.bucket_exists(targets.BUCKET):
        client.make_bucket(targets.BUCKET)

    by_day: dict[dt.date, list] = {}
    for t in all_trips:
        by_day.setdefault(t[3].date(), []).append(t)

    import io as _io
    written = 0
    for i in range(days):
        on = first_day + dt.timedelta(days=i)
        body = targets.regulator_csv(by_day.get(on, []))
        client.put_object(targets.BUCKET, targets.object_name(on),
                          _io.BytesIO(body), length=len(body),
                          content_type="application/gzip")
        written += 1
    return written


if __name__ == "__main__":
    sys.exit(main())
