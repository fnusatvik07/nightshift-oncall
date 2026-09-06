"""Writing the generated world into the five systems the course reads from.

One function per system, all of them taking the same rides and payments, so the
five systems tell five different versions of the same day. That is the point of
the exercise: the versions disagree in exactly the ways real systems disagree.

    postgres      the app database. trips, payments, zones, drivers, riders
    paynimbus     a different company's ledger, reachable only over HTTP
    mongo         the driver app's events, nested and schemaless
    redpanda      the ride lifecycle, one event per thing that happened
    minio         the regulator's nightly file, gzipped CSV with no types
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import os
import random

from .trips import fare_of, surge_of

BUCKET = "kerb-landing"
TOPIC = "kerb.trips.lifecycle"

# The other topics on the broker. Nothing in the course reads them, and that is
# deliberate: a broker with exactly one topic on it teaches people that a topic
# and a broker are the same thing, and they are not.
OTHER_TOPICS = ["kerb.gps.pings", "kerb.payments.settled", "kerb.trips.lifecycle.dlq"]


# ── 1 · postgres, the app database ─────────────────────────────────────────

def write_postgres(conn, zones, drivers, riders) -> None:
    """The reference data. COPY rather than INSERT, because a hundred thousand
    single INSERT statements is a hundred thousand round trips."""
    with conn.cursor() as cur:
        with cur.copy("COPY kerb.zones (zone_id, zone_name, borough, zone_type, "
                      "demand_weight) FROM STDIN") as cp:
            for row in zones:
                cp.write_row(row)
        with cur.copy("COPY kerb.drivers (driver_id, joined_at, home_zone_id, rating, "
                      "tier, status) FROM STDIN") as cp:
            for row in drivers:
                cp.write_row(row)
        with cur.copy("COPY kerb.riders (rider_id, signed_up_at, home_zone_id, segment) "
                      "FROM STDIN") as cp:
            for row in riders:
                cp.write_row(row)
    conn.commit()


def write_trips(conn, trips, payments) -> None:
    with conn.cursor() as cur:
        with cur.copy("COPY kerb.trips (trip_id, rider_id, driver_id, requested_at, "
                      "accepted_at, arrived_at, started_at, ended_at, pu_zone_id, "
                      "do_zone_id, distance_km, duration_s, status, app_version) "
                      "FROM STDIN") as cp:
            for row in trips:
                cp.write_row(row)
        with cur.copy("COPY kerb.payments (payment_id, trip_id, payment_type, status, "
                      "amount, captured_at) FROM STDIN") as cp:
            for row in payments:
                cp.write_row(row)
    conn.commit()


# ── 2 · paynimbus, the processor's own ledger ──────────────────────────────

def write_settlements(conn, payments, rng: random.Random, now: dt.datetime) -> int:
    """One settlement per non-cash payment, and three ways for one to end up
    absent from an API answer.

        cash            never reaches a processor at all. No row exists.
        failed          the charge did not clear
        still in flight settled_at is in the future, so the lookup skips it

    All three are correct and healthy states. A pipeline that treats any of
    them as an error will page somebody every night for nothing.
    """
    rows, seq = [], 0
    for payment_id, _trip_id, rail, _status, amount, captured_at in payments:
        if rail == "cash":
            continue
        seq += 1
        gross = float(amount)
        fee = round(gross * rng.uniform(0.008, 0.024), 2)

        r = rng.random()
        if r < 0.004:
            status, settled_at = "failed", None
        elif captured_at + dt.timedelta(days=2) > now:
            # settlement is T+2, so the most recent days genuinely have not
            # settled yet. This is why silver shows most rides as unsettled.
            status = "in_flight"
            settled_at = captured_at + dt.timedelta(days=2)
        else:
            status = "settled"
            settled_at = captured_at + dt.timedelta(
                days=2, seconds=rng.randrange(-7200, 7200))

        rows.append((f"PNS{seq:09d}", payment_id, rail, gross, fee,
                     round(gross - fee, 2), "INR", status, captured_at,
                     settled_at, 0))

    with conn.cursor() as cur:
        with cur.copy("COPY settlements (settlement_id, merchant_ref, rail, gross, fee, "
                      "net, currency, status, captured_at, settled_at, retry_count) "
                      "FROM STDIN") as cp:
            for row in rows:
                cp.write_row(row)
    conn.commit()
    return len(rows)


# ── 3 · mongo, the driver app ──────────────────────────────────────────────

def driver_app_docs(trips, rng: random.Random) -> list[dict]:
    """Two documents per ride that had a driver: the offer, and the end.

    The surge value is nested, and WHERE it is nested depends on the app
    release. That is the whole lesson in notebook 4, and it is not invented:
    a mobile team refactoring a payload without telling the data team is the
    single most common way a warehouse column goes quietly empty.

        4.0.6, 4.1.2, 4.1.5     payload.surge_multiplier
        4.2.0                   payload.pricing.surgeFactor
    """
    docs, seq = [], 0
    for (trip_id, _rider, driver_id, requested_at, _acc, _arr, _start, ended_at,
         pu, _do, distance, duration, status, app_version) in trips:
        if driver_id is None:
            continue

        surge = surge_of(trip_id, requested_at.hour)
        payload = {"eta_s": rng.randrange(90, 420),
                   "distance_km": float(distance)}

        if app_version == "4.2.0":
            payload["pricing"] = {"surgeFactor": surge}
        else:
            payload["surge_multiplier"] = surge

        seq += 1
        docs.append({
            "event_id": f"EV{seq:09d}",
            "trip_id": trip_id,
            "driver_id": driver_id,
            "session_id": f"S{rng.randrange(10_000_000, 99_999_999)}",
            "event_type": "trip_offer",
            "ts": requested_at.replace(tzinfo=None),
            "app": {"version": app_version,
                    "platform": rng.choice(["android", "ios"]),
                    "build": 415},
            "device": {"model": rng.choice(["Samsung M14", "iPhone 12", "Pixel 7a",
                                            "iPhone SE", "Redmi Note 12"]),
                       "os": rng.choice(["Android 14", "iOS 17.4", "Android 13"]),
                       "battery": rng.randrange(5, 100),
                       "network": rng.choice(["wifi", "4g", "5g"])},
            "location": {"lat": round(12.83 + rng.random() * 0.42, 6),
                         "lng": round(77.42 + rng.random() * 0.44, 6),
                         "accuracy_m": round(rng.uniform(4, 40), 1)},
            "payload": payload,
        })

        if status == "completed" and ended_at is not None:
            seq += 1
            docs.append({
                "event_id": f"EV{seq:09d}",
                "trip_id": trip_id,
                "driver_id": driver_id,
                "event_type": "trip_end",
                "ts": ended_at.replace(tzinfo=None),
                "app": {"version": app_version, "build": 415},
                "payload": {"distance_km": float(distance),
                            "duration_s": duration,
                            "rating_given": rng.randrange(3, 6)},
            })
    return docs


# ── 4 · redpanda, the ride lifecycle stream ────────────────────────────────

# A completed ride emits five events. A cancelled one emits three, and a ride
# nobody accepted emits two. That is why the average sits a little under five,
# and why the signal watching it has a tolerance rather than an exact number.
LIFECYCLE = {
    "completed":        ["requested", "accepted", "driver_arrived", "started", "completed"],
    "cancelled_rider":  ["requested", "accepted", "cancelled"],
    "cancelled_driver": ["requested", "accepted", "cancelled"],
    "no_driver":        ["requested", "expired"],
}


def lifecycle_events(trips):
    """Yield (key, value) pairs ready to produce.

    The key is the trip id, every time. Kafka puts the same key on the same
    partition, which is the only thing that keeps the five events of one ride
    in the order they happened. Drop the key and `completed` can be read before
    `requested`, with no error, because nothing is broken: you asked for the
    impossible.
    """
    for (trip_id, _rider, driver_id, requested_at, accepted_at, arrived_at,
         started_at, ended_at, pu, _do, distance, duration, status,
         _app_version) in trips:

        at = {"requested": requested_at, "accepted": accepted_at,
              "driver_arrived": arrived_at, "started": started_at,
              "completed": ended_at, "cancelled": arrived_at or accepted_at,
              "expired": requested_at + dt.timedelta(minutes=4)}

        for name in LIFECYCLE[status]:
            when = at.get(name) or requested_at
            event = {"trip_id": trip_id,
                     "event": name,
                     "ts": when.isoformat(),
                     "driver_id": None if name == "requested" else driver_id,
                     "pu_zone_id": pu}
            if name == "completed":
                surge = surge_of(trip_id, requested_at.hour)
                event["fare"] = fare_of(float(distance), duration, surge)
            yield trip_id.encode(), json.dumps(event).encode()


# ── 5 · minio, the regulator's nightly file ────────────────────────────────

def regulator_csv(trips_for_day) -> bytes:
    """One gzipped CSV, exactly as an external body would send it.

    Two details are deliberate and both cost people an afternoon the first time.

        Zone ids are written as "9.0", because whatever produced the file held
        them as floats. int("9.0") raises.

        A handful of rows carry a value that will not convert at all. One bad
        row in a thousand must not throw away the other nine hundred and
        ninety nine.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["trip_id", "pu_zone_id", "do_zone_id", "distance_km",
                     "duration_s", "status"])

    rng = random.Random("regulator")
    for (trip_id, _rider, _driver, _req, _acc, _arr, _start, _end, pu, do,
         distance, duration, status, _app) in trips_for_day:
        if status != "completed":
            continue
        pu_out = "" if pu is None else f"{float(pu):.1f}"      # 9 becomes "9.0"
        duration_out = duration
        if rng.random() < 0.0008:
            duration_out = "n/a"                               # will not convert
        writer.writerow([trip_id, pu_out, do, distance, duration_out, status])

    return gzip.compress(buf.getvalue().encode("utf-8"))


def object_name(on: dt.date) -> str:
    """The date lives in the path, in ISO order, so sorting by name sorts by
    date. That is a convention called partitioning, and it is not luck."""
    return f"regulator/dt={on.isoformat()}/trips_audit.csv.gz"


def minio_client():
    from minio import Minio
    endpoint = os.environ["MINIO_ENDPOINT"].replace("http://", "").replace("https://", "")
    return Minio(endpoint,
                 access_key=os.environ["MINIO_ACCESS_KEY"],
                 secret_key=os.environ["MINIO_SECRET_KEY"],
                 secure=False)
