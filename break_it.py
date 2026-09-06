"""Break something on purpose, so the class can watch a signal notice.

    python break_it.py          break it
    python break_it.py --fix    put it back

What it breaks: the driver app renames its surge field, exactly the way a real
mobile release does. Nothing errors. No pipeline fails. The rows still land.
The only thing that changes is that a value the pricing team depends on
quietly stops arriving.

This is the most useful kind of failure to show people, because it is the kind
that a row count check will never find.

Nothing here touches the source systems. It writes to a copy of the driver app
collection inside our own schema, so `reset` undoes it completely.
"""
from __future__ import annotations

import argparse
import sys

import psycopg

from pipelines.lib.config import SCHEMA, dsn

BROKEN_PATH = "pricing.surge_multiplier"


def flip(fix: bool) -> int:
    with psycopg.connect(dsn(), autocommit=True) as c:
        exists = c.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=%s AND table_name='bronze_driver_app'", (SCHEMA,)).fetchone()
        if not exists:
            print("  nothing to break yet. Run: python cli.py run all")
            return 1

        if fix:
            n = c.execute(f"UPDATE {SCHEMA}.bronze_driver_app SET surge = surge_backup "
                          f"WHERE surge IS NULL AND surge_backup IS NOT NULL").rowcount
            print(f"  put the surge value back on {n:,} records")
            print("  now run:  python cli.py board")
            return 0

        c.execute(f"ALTER TABLE {SCHEMA}.bronze_driver_app "
                  f"ADD COLUMN IF NOT EXISTS surge_backup NUMERIC(6,2)")
        c.execute(f"UPDATE {SCHEMA}.bronze_driver_app SET surge_backup = surge "
                  f"WHERE surge_backup IS NULL")

        # A release moved the field, so the break is RELEASE shaped, not time
        # shaped. That distinction is the whole lesson: blank the newest rows
        # and the evidence says "since Tuesday", which points at a schedule.
        # Blank one version's rows and the evidence says "only from 4.2.0",
        # which points at the mobile team. Only one of those is findable.
        row = c.execute(f"""SELECT app_version FROM {SCHEMA}.bronze_driver_app
                            WHERE app_version IS NOT NULL
                            GROUP BY 1 ORDER BY max(happened_at) DESC LIMIT 1""").fetchone()
        if not row:
            print("  no app versions in bronze_driver_app. Run: python cli.py run all")
            return 1
        version = row[0]

        n = c.execute(f"""UPDATE {SCHEMA}.bronze_driver_app SET surge = NULL
                          WHERE app_version = %s""", (version,)).rowcount
        print(f"  driver app {version} moved surge to '{BROKEN_PATH}'")
        print(f"  {n:,} records from that release now have no surge value we can read")
        print("  nothing failed. no pipeline errored. now run:  python cli.py board")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true")
    return flip(ap.parse_args().fix)


if __name__ == "__main__":
    sys.exit(main())
