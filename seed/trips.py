"""Rides, and the payments that follow them.

One function generates one day of trading. Everything downstream, the events on
the stream, the documents in Mongo, the files in the bucket and the settlements
at the processor, is derived from these rides, so all five systems agree with
each other the way five real systems would.

The shape of a day matters. Rides cluster into a morning peak and an evening
peak, because a flat distribution across twenty four hours produces a dataset
where every hour looks the same and no query about time is ever interesting.
"""
from __future__ import annotations

import datetime as dt
import random

# what share of rides end each way. These four are the entire contract in
# notebook 2: a fifth status appearing is the thing the contract is watching for.
STATUS_WEIGHTS = [
    ("completed", 89.0),
    ("cancelled_rider", 6.0),
    ("cancelled_driver", 4.0),
    ("no_driver", 1.0),
]

# rides per hour, as a share of the day. Two peaks, a quiet night.
HOUR_SHAPE = [
    0.6, 0.4, 0.3, 0.3, 0.5, 1.2, 3.0, 6.4, 8.6, 7.2, 5.4, 4.6,
    4.4, 4.2, 4.0, 4.4, 5.6, 7.8, 9.2, 8.0, 5.6, 3.8, 2.4, 1.4,
]

PAYMENT_TYPES = ["upi", "card", "wallet", "cash"]
PAYMENT_WEIGHTS = [52, 26, 14, 8]     # cash never reaches a processor

# How busy each weekday is, Monday first. Friday and Saturday nights carry a
# city; Sunday does not.
#
# This is not decoration. A dataset where every day has exactly the same ride
# count makes the rides_per_day signal in notebook 8 meaningless: the spread is
# zero, so either nothing ever breaches or everything does. Real days vary, and
# a baseline is only useful when it has something to be a baseline of.
WEEKDAY_SHAPE = [1.00, 1.02, 1.05, 1.09, 1.24, 1.18, 0.84]


def fare_of(distance_km: float, duration_s: int, surge: float) -> float:
    """A fare a person could check with a calculator.

    Base plus distance plus time, multiplied by surge, with a floor. Nothing
    here is clever: the point is that the number is explainable, because a
    teaching dataset where nobody can say why a fare is what it is teaches
    people to stop asking.
    """
    fare = 30.0 + 13.5 * distance_km + 1.6 * (duration_s / 60.0)
    return round(max(45.0, fare * surge), 2)


def day(rng: random.Random, on: dt.date, progress: float, n_rides: int,
        n_drivers: int, n_riders: int, n_zones: int, zone_weights: list[float],
        trip_seq: int, pay_seq: int) -> tuple[list, list, int, int]:
    """One day of trading.

    `progress` is how far through the dataset this day sits, 0.0 for the first
    day and 1.0 for the last. It decides which app release the rides were
    booked on, so the newest release only shows up near the end.

    Returns (trips, payments, next_trip_seq, next_pay_seq). Sequence numbers
    are carried in and out so trip ids run in time order across the whole
    dataset, which is what makes `ORDER BY trip_id` and `ORDER BY requested_at`
    agree, and saves a class from a confusing afternoon.
    """
    statuses = [s for s, _ in STATUS_WEIGHTS]
    status_w = [w for _, w in STATUS_WEIGHTS]
    zone_ids = list(range(1, n_zones + 1))

    # a busy Friday and a quiet Sunday, plus a few percent of ordinary noise
    n_rides = int(round(n_rides * WEEKDAY_SHAPE[on.weekday()] * rng.uniform(0.97, 1.03)))

    # how many rides land in each hour
    total_shape = sum(HOUR_SHAPE)
    per_hour = [int(round(n_rides * h / total_shape)) for h in HOUR_SHAPE]

    trips, payments = [], []

    for hour, count in enumerate(per_hour):
        for _ in range(count):
            trip_seq += 1
            trip_id = f"TRP{trip_seq:08d}"

            # UTC throughout. Every timestamp in this dataset is timezone
            # aware, because a naive datetime is a bug waiting for the first
            # person who runs the course in a different timezone.
            requested = dt.datetime.combine(
                on, dt.time(hour=hour), dt.timezone.utc
            ) + dt.timedelta(seconds=rng.randrange(3600))

            status = rng.choices(statuses, weights=status_w)[0]
            pu = rng.choices(zone_ids, weights=zone_weights)[0]
            do = rng.choices(zone_ids, weights=zone_weights)[0]

            # About four rides in a thousand never resolve to a service zone.
            # They still happened and still earned money, which is why the
            # dimension join in notebook 7 has to be a LEFT JOIN.
            if rng.random() < 0.004:
                pu = None

            distance = round(min(38.0, max(0.6, rng.lognormvariate(1.2, 0.62))), 3)
            duration = int(distance * rng.uniform(105, 240) + rng.randrange(60, 400))

            driver = (None if status == "no_driver"
                      else f"DRV{rng.randrange(1, n_drivers + 1):06d}")
            rider = f"RDR{rng.randrange(1, n_riders + 1):07d}"

            accepted = arrived = started = ended = None
            if status != "no_driver":
                accepted = requested + dt.timedelta(seconds=rng.randrange(8, 90))
                arrived = accepted + dt.timedelta(seconds=rng.randrange(60, 600))
            if status == "completed":
                started = arrived + dt.timedelta(seconds=rng.randrange(15, 300))
                ended = started + dt.timedelta(seconds=duration)

            app_version = _version_for(rng, progress)

            trips.append((trip_id, rider, driver, requested, accepted, arrived,
                          started, ended, pu, do, distance,
                          duration if status == "completed" else None,
                          status, app_version))

            # Only a completed ride is charged for.
            if status == "completed":
                pay_seq += 1
                surge = surge_of(trip_id, hour)
                amount = fare_of(distance, duration, surge)
                payments.append((
                    f"PAY{pay_seq:08d}", trip_id,
                    rng.choices(PAYMENT_TYPES, weights=PAYMENT_WEIGHTS)[0],
                    "captured", amount,
                    ended + dt.timedelta(seconds=rng.randrange(2, 40)),
                ))

    return trips, payments, trip_seq, pay_seq


# ── the derived values every other system needs ────────────────────────────
# Both of these are pure functions of the ride. The stream, the documents and
# the files all call them and land on exactly the same answer, rather than the
# generator having to carry state between five systems.
#
# That is not only convenient. It is why the fare on the Kafka event matches
# the fare in the payments table, which is what makes the join in notebook 7
# produce numbers that reconcile.

def surge_of(trip_id: str, hour: int) -> float:
    """Surge is higher in the peaks, which is the entire point of surge.

    Seeded from the trip id, so any system can recompute it without being told.
    """
    r = random.Random(f"surge-{trip_id}")
    peak = HOUR_SHAPE[hour] / max(HOUR_SHAPE)
    return round(1.0 + peak * r.uniform(0.05, 1.35), 2)


def _version_for(rng: random.Random, progress: float) -> str:
    """Which app release a ride was booked on.

    4.2.0 only exists in the last stretch of the dataset, because that is what
    a release looks like. A version that appears evenly across a month looks
    like noise, and the incident in notebook 4 stops being findable.
    """
    if progress > 0.87 and rng.random() < 0.25:
        return "4.2.0"
    r = rng.random()
    if r < 0.17:
        return "4.0.6"
    if r < 0.50:
        return "4.1.2"
    return "4.1.5"
