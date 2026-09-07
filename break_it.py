"""Break something on purpose, so the class can watch a signal notice.

    python break_it.py          break it
    python break_it.py --fix    put it back

What it breaks: **the driver app moves its surge field**, exactly the way a real
mobile release does. Version 4.2.0 currently sends the multiplier at
`payload.pricing.surgeFactor`. A point release moves it to
`payload.pricing.surge.factor`, one level deeper, and tells nobody.

Nothing errors. No pipeline fails. Nobody gets an email. The only thing that
changes is that the ingestion contract in `p3_bronze_driver_app` no longer has a
path that matches, so every document from that release is **held** rather than
landed, and a value the pricing team depends on quietly stops arriving.

This is the most useful kind of failure to show people, because it is the kind
that a row count check will never find, and because the fix is real: one more
entry in `SURGE_PATHS`.

## Why this writes to mongodb and the old version did not

An earlier version of this script blanked the `surge` column in our own copy.
It was safer and it was a lie: `p3` never writes a null surge. A document it
cannot read is held, with a reason. Simulating the break in the warehouse
produced a state the pipeline cannot actually produce, and an agent that went
looking for the cause in the code found code that was already correct.

So the break happens where a real one happens: in the source. `--fix` moves the
field back, and re-seeding restores it too. Nothing here is destructive: it is a
rename inside a local container holding generated data.
"""
from __future__ import annotations

import argparse
import sys

from pymongo import MongoClient

from pipelines.lib.config import MONGO_URI

# The release that moves the field. The newest one, because a break that lands
# on a RELEASE rather than on a DATE is the one worth teaching: blank the newest
# rows and the evidence says "since Tuesday", which points at a schedule. Break
# one version and the evidence says "only from 4.2.0", which points at the
# mobile team. Only one of those is findable.
RELEASE = "4.2.0"

# 4.2.0 is the release that already moved this field once, from
# payload.surge_multiplier to payload.pricing.surgeFactor. p3 learned that path
# the hard way. This is the same team doing it again.
WAS = "payload.pricing.surgeFactor"       # where the pipeline knows to look
NOW = "payload.pricing.surge.factor"      # where the release moved it


def collection():
    return MongoClient(MONGO_URI).kerb_app.driver_app_events


def flip(fix: bool) -> int:
    col = collection()
    frm, to = (NOW, WAS) if fix else (WAS, NOW)

    matched = col.count_documents({"app.version": RELEASE, frm: {"$exists": True}})
    if matched == 0:
        other = col.count_documents({"app.version": RELEASE, to: {"$exists": True}})
        if other:
            print(f"  already {'fixed' if fix else 'broken'}: "
                  f"{other:,} documents from {RELEASE} carry surge at {to}")
            return 0
        print(f"  no {RELEASE} documents with a surge value at {frm}.")
        print("  Is the estate seeded?   python -m seed")
        return 1

    # $rename moves the field in place. It is one write per document and mongodb
    # does it without reading the value back, so 12,000 documents take about a
    # second.
    result = col.update_many({"app.version": RELEASE, frm: {"$exists": True}},
                             {"$rename": {frm: to}})
    if result.modified_count != matched:
        print(f"  warning: {matched:,} documents matched but "
              f"{result.modified_count:,} were changed")

    if fix:
        print(f"  driver app {RELEASE} put surge back at {WAS}")
        print(f"  {result.modified_count:,} documents restored")
        print("\n  now re-run the pipeline that reads them, and the two below it:")
        print("    python cli.py run p3_bronze_driver_app")
        print("    python cli.py run p7_silver_rides")
        print("    python cli.py run p8_gold_daily")
    else:
        print(f"  driver app {RELEASE} moved surge from {WAS} to {NOW}")
        print(f"  {result.modified_count:,} documents from that release now put the "
              f"value somewhere no contract in p3_bronze_driver_app looks")
        print("\n  nothing failed. no pipeline errored. Re-run the pipelines and look:")
        print("    python cli.py run p3_bronze_driver_app")
        print("    python cli.py run p7_silver_rides")
        print("    python cli.py run p8_gold_daily")
        print("    python cli.py signals")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true", help="put the field back")
    a = ap.parse_args()
    try:
        return flip(a.fix)
    except Exception as e:                              # noqa: BLE001
        print(f"  could not reach mongodb: {type(e).__name__}: {e}")
        print("  Is the estate up?   docker compose -f platform/docker-compose.yml ps")
        return 1


if __name__ == "__main__":
    sys.exit(main())
