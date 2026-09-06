"""BRONZE · settlements.  Ask the payment processor which charges cleared.

    reads   HTTP      PayNimbus, POST /v1/settlements/lookup
    writes  postgres  teach.bronze_settlements
    runs    daily at 03:00

WHY THIS ONE IS DIFFERENT
    The first three sources are ours. This one is not.

    When a ride ends, KERB knows what it CHARGED. Whether the money actually
    cleared, what fee the processor kept, and when it reached the bank are facts
    only PayNimbus has. So we have to ask, over HTTP, and everything about that
    is less comfortable than reading our own database.

    Three consequences, one per step below: we ask in batches, we accept that an
    answer may simply not be there, and we trust nothing about the shape.

RUN IT
    python -m pipelines.p4_bronze_settlements --limit 5000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

import psycopg

from .lib.config import SCHEMA, dsn
from .lib.run import Run, setup

TABLE = "bronze_settlements"

# Read the address from the environment, never hardcode it.
#
# On a laptop this is localhost. Inside the Airflow container "localhost" is the
# container itself, and the partner is at http://partner-api:8088. A pipeline
# that only works in one of those two places is not finished.
API = os.environ.get("PARTNER_API", "http://localhost:8088") + "/v1/settlements/lookup"


# ══ STEP 1 · Ask in batches, and pick the batch size on purpose ══
#
# We have sixty thousand payments to ask about. One HTTP call each is sixty
# thousand round trips against a partner's system. That is not a pipeline, that
# is an accidental denial of service attack on a company you have a contract
# with, and somebody will phone you about it.
#
# 250 turns 60,000 calls into 240. Why 250 and not 5,000? Because a request that
# large takes long enough to hit a timeout, and when it fails you lose the whole
# batch and retry all of it. The number is a trade between round trips and blast
# radius, and it belongs in a named constant so it can be argued about.
BATCH = 250


# ══ STEP 2 · Describe the table ══
#
# Note `trip_id`. PayNimbus does not send it: it knows about payments, not
# rides. We look it up on our side in STEP 5 and carry it along.
#
# Without that column this table is a set of numbers with nothing to attach them
# to. A settlement that cannot be joined back to a ride cannot answer any
# question anybody actually asks.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    settlement_id TEXT PRIMARY KEY,   -- the processor's id, so a re-ask is harmless
    payment_id    TEXT,               -- our id, which is what we asked them about
    trip_id       TEXT,               -- added by us, see STEP 5
    rail          TEXT,               -- card, upi, wallet
    gross         NUMERIC(12,2),      -- what the rider was charged
    fee           NUMERIC(12,2),      -- what the processor kept
    net           NUMERIC(12,2),      -- what actually reached the bank
    status        TEXT,
    currency      TEXT,
    settled_at    TIMESTAMPTZ
);
"""


# ══ STEP 3 · The contract, and why defaulting it costs real money ══
#
# Three answers we know how to file. Anything else is held.
#
# This is not theoretical. Right now, in the data, the partner returns an EMPTY
# STRING for some settlements. Not "failed". Not "settled". "".
#
# An empty status means the money can be neither recognised as revenue nor
# chased as missing. It is in a third state that no report has a column for.
# And look at what both defaults would cost:
#
#     default it to 'failed'    finance writes off money that actually arrived
#     default it to 'settled'   finance books revenue that never came
#
# Holding it is the only answer that is not a lie to somebody.
KNOWN_STATUS = {"settled", "failed", "in_flight"}


# ══ STEP 4 · One HTTP call, kept boring ══
#
# No retry logic, no backoff, no circuit breaker. Not because those are wrong,
# but because they belong in a shared client and this file is about the pipeline
# shape. Adding them here would bury the lesson under plumbing.
#
# The timeout is not optional though. Without it, a partner that hangs takes
# your pipeline with it, forever, silently.
def ask(refs: list[str]) -> list[dict]:
    request = urllib.request.Request(
        API,
        data=json.dumps({"refs": refs}).encode(),
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("settlements", [])


INSERT = f"""
    INSERT INTO {SCHEMA}.{TABLE}
        (settlement_id, payment_id, trip_id, rail, gross, fee, net, status, currency, settled_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (settlement_id) DO NOTHING
"""


# ══ STEP 5 · Ask, and understand the three possible outcomes ══
#
# Every reference we ask about ends up in exactly one of three buckets, and
# being able to tell them apart is most of the job:
#
#   written    the partner answered and we understood the answer
#   held       the partner answered and we did not understand it
#   absent     the partner did not answer at all
#
# That third one is the one people get wrong. A charge still in flight is simply
# not in the response. It is not an error and it is not a null. It is missing,
# and missing is the correct, expected, healthy state for money that has not
# moved yet. Treat absent as a failure and you will page somebody every single
# night for a system behaving exactly as designed.
def run(limit: int = 5000) -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p4_bronze_settlements") as r:
        # Carry the trip_id along, as promised in STEP 2.
        with psycopg.connect(dsn()) as c:
            pairs = c.execute("""
                SELECT payment_id, trip_id FROM kerb.payments
                WHERE status = 'captured'
                ORDER BY captured_at DESC LIMIT %s""", (limit,)).fetchall()
        trip_of = dict(pairs)
        refs = [payment_id for payment_id, _ in pairs]

        rows = []
        for i in range(0, len(refs), BATCH):
            chunk = refs[i:i + BATCH]
            r.rows_in += len(chunk)

            for s in ask(chunk):
                status = s.get("status")
                if status not in KNOWN_STATUS:
                    r.quarantine(
                        payload=s,
                        reason=f"status {status!r} is not one of {sorted(KNOWN_STATUS)}",
                        key=s.get("merchant_ref"))
                    continue

                rows.append((
                    s["settlement_id"],
                    s.get("merchant_ref"),                    # their name for our payment_id
                    trip_of.get(s.get("merchant_ref")),       # the join key we added
                    s.get("rail"), s.get("gross"), s.get("fee"), s.get("net"),
                    status, s.get("currency"), s.get("settled_at")))

        if rows:
            with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
                cur.executemany(INSERT, rows)
                c.commit()

        r.rows_out = len(rows)
        absent = len(refs) - len(rows) - len(r._held)
        r.message = (f"{len(refs):,} asked in batches of {BATCH}, "
                     f"{absent:,} still in flight")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=5000)
    return run(ap.parse_args().limit)


if __name__ == "__main__":
    sys.exit(main())
