"""Break something on purpose, so a class can watch a signal notice.

    python break_it.py --list           what can be broken, and what notices
    python break_it.py                  the default: a mobile release moves a field
    python break_it.py zones            a new zone opens, the dimension is stale
    python break_it.py stale            the daily aggregate did not rebuild
    python break_it.py --fix            put everything back
    python break_it.py --fix zones      put one thing back

## Why there are three of them and not one

Because "the agent found the problem" is only interesting if the problem is not
always the same problem. Each of these breaks in a **different layer**, is caught
by a **different signal**, belongs to a **different team**, and needs a
**different kind of fix**:

    surge     a document store     pricing         a code change, so a pull request
    zones     a stale dimension    operations      a data change, so a human gate
    stale     our own warehouse    data-platform   neither: just run the pipeline

Run any of them and then `python cli.py investigate <kpi>`, and you get three
genuinely different Confluence pages, because the evidence is genuinely
different. None of it is scripted: there is no list of incidents anywhere in
this project.

## What they have in common

Nothing fails. No pipeline errors, no row count check goes red, no retry fires.
That is the point of every one of them.

Every break is reversible, and `--fix` puts back exactly what it moved. The one
that writes to a source database keeps the original value in a backup column
first, so nothing is ever lost, and `python cli.py reset` runs the fix for you.
"""
from __future__ import annotations

import argparse
import sys

import psycopg
from pymongo import MongoClient

from pipelines.lib.config import MONGO_URI, SCHEMA, dsn


# ═══════════════════════════════════════════════════════════════════════════
# 1 · surge · a mobile release moves a field in the driver app payload
# ═══════════════════════════════════════════════════════════════════════════
#
# The release that already moved this field once, from payload.surge_multiplier
# to payload.pricing.surgeFactor. p3 learned that path the hard way. This is the
# same team doing it again, one level deeper.
#
# A break that lands on a RELEASE rather than on a DATE is the one worth
# teaching: blank the newest rows and the evidence says "since Tuesday", which
# points at a schedule. Break one version and the evidence says "only from
# 4.2.0", which points at the mobile team. Only one of those is findable.

RELEASE = "4.2.0"
WAS = "payload.pricing.surgeFactor"       # where the pipeline knows to look
NOW = "payload.pricing.surge.factor"      # where the release moved it


def _driver_app():
    return MongoClient(MONGO_URI).kerb_app.driver_app_events


def surge(fix: bool) -> str:
    col = _driver_app()
    frm, to = (NOW, WAS) if fix else (WAS, NOW)

    if col.count_documents({"app.version": RELEASE, frm: {"$exists": True}}) == 0:
        return f"surge: already {'fixed' if fix else 'broken'}"

    n = col.update_many({"app.version": RELEASE, frm: {"$exists": True}},
                        {"$rename": {frm: to}}).modified_count
    if fix:
        return f"surge: {n:,} documents put back at {WAS}"
    return (f"surge: driver app {RELEASE} moved surge to {NOW}. "
            f"{n:,} documents now put it where no contract looks")


# ═══════════════════════════════════════════════════════════════════════════
# 2 · zones · a new zone opens, and the dimension copy is stale
# ═══════════════════════════════════════════════════════════════════════════
#
# Facts and dimensions move at different speeds, and that difference is where
# this class of bug lives. Rides arrive every minute. The list of zones is
# refreshed once a day, because it barely changes.
#
# Then operations opens a new zone on Tuesday morning. Rides start arriving from
# it immediately. Our copy of the zone list is from Monday night, so the join
# finds nothing, and every one of those rides is in the warehouse with no idea
# where it started.
#
# Nothing fails. A LEFT JOIN that finds nothing is not an error, it is a null,
# and the ride count is exactly right. Only the zone name is missing.
#
# The fix is NOT code. The code is correct and the join is correct. The DIMENSION
# is out of date, which is why this one ends with the agent asking a human rather
# than opening a pull request.

NEW_ZONE = 900
NEW_ZONE_NAME = "Whitefield Extension"


def zones(fix: bool) -> str:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute("ALTER TABLE kerb.trips ADD COLUMN IF NOT EXISTS pu_zone_backup INT")

        if fix:
            n = c.execute("""UPDATE kerb.trips SET pu_zone_id = pu_zone_backup
                             WHERE pu_zone_id = %s AND pu_zone_backup IS NOT NULL""",
                          (NEW_ZONE,)).rowcount
            c.execute("DELETE FROM kerb.zones WHERE zone_id = %s", (NEW_ZONE,))
            return f"zones: {n:,} rides moved back out of the new zone"

        if c.execute("SELECT 1 FROM kerb.zones WHERE zone_id = %s", (NEW_ZONE,)).fetchone():
            return "zones: already broken"

        # The zone genuinely exists in the source. That is the whole point: this
        # is not corrupt data, it is data our copy has not caught up with.
        c.execute("""INSERT INTO kerb.zones
                     (zone_id, zone_name, borough, zone_type, demand_weight)
                     VALUES (%s, %s, 'East', 'residential', 2.5)""",
                  (NEW_ZONE, NEW_ZONE_NAME))

        n = c.execute("""
            UPDATE kerb.trips SET pu_zone_backup = pu_zone_id, pu_zone_id = %s
            WHERE pu_zone_id IN (SELECT zone_id FROM kerb.zones
                                 WHERE zone_id <> %s
                                 ORDER BY demand_weight DESC LIMIT 4)
        """, (NEW_ZONE, NEW_ZONE)).rowcount
        return (f"zones: {NEW_ZONE_NAME!r} opened this morning. {n:,} rides "
                f"started there, and our copy of the zone list is from last night")


# ═══════════════════════════════════════════════════════════════════════════
# 3 · stale · the daily aggregate did not rebuild
# ═══════════════════════════════════════════════════════════════════════════
#
# The most common production incident there is, and the most boring: a job did
# not run. Somebody paused a DAG, a machine was rotated, a dependency was
# renamed. Bronze is current. Gold is a day behind.
#
# Nothing is wrong with any row anywhere. The warehouse is simply telling you
# about yesterday while calling it today, and every dashboard built on it is
# confidently out of date.
#
# This one is broken in OUR warehouse rather than in a source, because that is
# where it happens. And the fix is not a code change and not a data change: it
# is running the pipeline that did not run.


def stale(fix: bool) -> str:
    with psycopg.connect(dsn(), autocommit=True) as c:
        if fix:
            return "stale: run `python cli.py run p8_gold_daily` to rebuild it"

        row = c.execute(f"SELECT max(trip_date) FROM {SCHEMA}.gold_daily").fetchone()
        if not row or row[0] is None:
            return "stale: gold_daily is empty already. Run: python cli.py run all"

        # Two days, not one. One missed run is 24 hours behind, and the signal
        # deliberately allows 30: a nightly job finishing late is not an
        # incident. Two missed runs is a job that has stopped.
        n = c.execute(f"""DELETE FROM {SCHEMA}.gold_daily
                          WHERE trip_date > %s::date - 2""", (row[0],)).rowcount

        # And take the run log with it, because a break has to be a state the
        # system could actually reach. Leave the log saying p8 succeeded two
        # minutes ago while gold is two days behind and the evidence contradicts
        # itself: anybody investigating, human or otherwise, is being asked to
        # explain something that never happened. A job that did not run has no
        # run rows. That absence IS the evidence.
        runs = c.execute(f"""DELETE FROM {SCHEMA}.runs
                             WHERE pipeline = 'p8_gold_daily'
                               AND started_at > now() - interval '2 days'""").rowcount
        return (f"stale: p8_gold_daily has not run for two days. {n} day(s) gone "
                f"from gold_daily and {runs} run(s) gone from the log. "
                f"Bronze is current, gold is behind, and nothing failed")


# ═══════════════════════════════════════════════════════════════════════════

SCENARIOS = {
    "surge": (surge, "pricing",       "surge_coverage_pct",
              "a mobile release moves a field in the driver app payload"),
    "zones": (zones, "operations",    "zone_coverage_pct",
              "a new zone opens and the dimension copy is stale"),
    "stale": (stale, "data-platform", "warehouse_lag_hours",
              "the daily aggregate did not rebuild"),
}

# Which pipelines carry the break into the warehouse. Note what is NOT in the
# zones list: p6, the one that copies the zone dimension. Running it would fix
# the break, because the new zone really is in the source. That absence is the
# scenario.
AFTER = {
    "surge": ["p3_bronze_driver_app", "p7_silver_rides", "p8_gold_daily"],
    "zones": ["p1_bronze_trips", "p7_silver_rides", "p8_gold_daily"],
    "stale": [],
}


def show_list() -> int:
    print()
    print(f"  {'scenario':10} {'owner':15} {'the signal that notices':24} what happens")
    print("  " + "-" * 100)
    for name, (_fn, owner, kpi, what) in SCENARIOS.items():
        print(f"  {name:10} {owner:15} {kpi:24} {what}")
    print()
    print("    python break_it.py <scenario>          break it")
    print("    python cli.py run <pipeline>           carry it into the warehouse")
    print("    python cli.py signals                  watch the board notice")
    print("    python cli.py investigate <signal>     watch the agents work it")
    print("    python break_it.py --fix               put everything back")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scenario", nargs="?", default=None,
                    help=f"one of: {', '.join(SCENARIOS)}. Default: surge")
    ap.add_argument("--fix", action="store_true", help="put it back")
    ap.add_argument("--list", action="store_true", help="what can be broken")
    a = ap.parse_args()

    if a.list:
        return show_list()

    if a.scenario and a.scenario not in SCENARIOS:
        print(f"  no scenario called {a.scenario!r}. Try: python break_it.py --list")
        return 2

    # --fix with no scenario puts everything back, because after a lesson you do
    # not want to remember which of the three you showed.
    todo = [a.scenario] if a.scenario else (list(SCENARIOS) if a.fix else ["surge"])

    print()
    for name in todo:
        fn, owner, kpi, _what = SCENARIOS[name]
        try:
            print(f"  {fn(a.fix)}")
        except Exception as e:                          # noqa: BLE001
            print(f"  {name}: could not reach the source ({type(e).__name__}: {e})")
            print("  Is the estate up?   docker compose -f platform/docker-compose.yml ps")
            return 1
        if not a.fix:
            print(f"  {'':10} nothing failed. {kpi} is {owner}'s signal.")

    if a.fix:
        print("\n  now rebuild, so the warehouse catches up:  python cli.py run all\n")
        return 0

    steps = AFTER[todo[0]]
    print("\n  carry it into the warehouse, then look:")
    for p in steps:
        print(f"    python cli.py run {p}")
    print("    python cli.py signals")
    print(f"    python cli.py investigate {SCENARIOS[todo[0]][2]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
