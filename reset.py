"""Put everything back, so the same lesson can be taught twice.

    python cli.py reset                 everything: warehouse, incidents, artifacts
    python cli.py reset --warehouse     only the data, keep what the agents found
    python cli.py reset --oncall        only the incidents and artifacts, keep the data

The third one is the one to use between demos of the agent. It forgets every
breach and every artifact without making you rebuild the warehouse, so the same
break can be shown twice in one lesson.

There are five kinds of state in this project, and a reset that forgets one of
them is the reason a demo works in rehearsal and not in the room:

    the warehouse        schema 'teach'    bronze, silver, gold, runs, quarantine
    the on-call record   schema 'oncall'   readings, breaches, incidents, tickets
    the stream position  on the broker     which messages the consumer has read
    the artifacts        artifacts/        specs and tickets written to disk,
                                           plus the git branches the agent opened
    the break            mongodb           the field break_it.py moved

That last one is the one people forget, and it is the worst to forget: reset the
warehouse without undoing the break and the pipelines faithfully rebuild a
broken warehouse, which looks exactly like a reset that did not work.

Undoing the break is the one thing here that writes to a source system, and it
writes back exactly what it moved. Everything else in this project is read only
against the sources, and that is enforced rather than promised.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg

from pipelines.lib.config import KAFKA, SCHEMA, dsn
from pipelines.lib.run import setup

ROOT = Path(__file__).parent
ONCALL = "oncall"

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
            print("  kafka      no saved position to forget")
            return
        for g, fut in admin.delete_consumer_groups(todo, request_timeout=15).items():
            fut.result()
            print(f"  kafka      forgot the saved position for '{g}'")
    except Exception as e:
        print(f"  kafka      could not clear the offset ({type(e).__name__}: {e})")


def put_the_field_back() -> None:
    """Undo break_it.py, if it is still in place.

    Rebuilding the warehouse without this rebuilds it broken: the pipelines do
    exactly what they are told, and what they are told to read is still moved.
    """
    r = subprocess.run([sys.executable, "break_it.py", "--fix"],
                       cwd=ROOT, capture_output=True, text=True)
    line = (r.stdout + r.stderr).strip().splitlines()
    print(f"  source     {line[0].strip() if line else 'nothing to undo'}")


def count_rows(schema: str) -> list[tuple[str, int]]:
    try:
        with psycopg.connect(dsn()) as c:
            names = [r[0] for r in c.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s ORDER BY table_name", (schema,))]
            return [(n, c.execute(f"SELECT count(*) FROM {schema}.{n}").fetchone()[0])
                    for n in names]
    except Exception:
        return []


def drop(schema: str) -> None:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


def forget_artifacts() -> None:
    """The specs, tickets and diffs the agents wrote, and the branches they opened.

    Deleting the branches matters more than it looks. `propose_code_change`
    refuses to open a branch that already exists, which is correct behaviour and
    a confusing thing to hit live, because the second demo of the day reports
    'a branch for this change already exists' instead of raising a PR.
    """
    folder = ROOT / "artifacts"
    if folder.exists():
        kept = sum(1 for _ in folder.rglob("*") if _.is_file())
        shutil.rmtree(folder)
        print(f"  artifacts  removed {kept} file(s) from artifacts/")
    else:
        print("  artifacts  nothing written yet")

    branches = subprocess.run(
        ["git", "-C", str(ROOT), "branch", "--list", "oncall/*"],
        capture_output=True, text=True).stdout.split()
    for b in branches:
        subprocess.run(["git", "-C", str(ROOT), "branch", "-D", b],
                       capture_output=True, text=True)
    subprocess.run(["git", "-C", str(ROOT), "worktree", "prune"],
                   capture_output=True, text=True)
    print(f"  git        deleted {len(branches)} leftover oncall/ branch(es)")


def main() -> int:
    ap = argparse.ArgumentParser(prog="reset", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--warehouse", action="store_true",
                    help="reset only the data, and keep the incidents and artifacts")
    ap.add_argument("--oncall", action="store_true",
                    help="reset only the incidents and artifacts, and keep the data")
    a = ap.parse_args()
    if a.warehouse and a.oncall:
        print("  --warehouse and --oncall together is just a plain reset")
        a.warehouse = a.oncall = False

    wanted = [SCHEMA, ONCALL]
    if a.warehouse:
        wanted = [SCHEMA]
    elif a.oncall:
        wanted = [ONCALL]

    print()
    for schema in wanted:
        rows = count_rows(schema)
        total = sum(k for _, k in rows)
        print(f"  {'schema':10} '{schema}': {len(rows)} table(s), {total:,} row(s)")
        for n, k in rows:
            print(f"             {n:26} {k:>10,}")
        drop(schema)

    if SCHEMA in wanted:
        put_the_field_back()
        setup()                  # recreates 'teach', empty
        forget_stream_position()
    if ONCALL in wanted:
        from agent_service import journal
        from agent_service.tools.publish import setup as artifacts_setup
        from signal_service import store
        store.setup()            # readings, breaches, incidents
        artifacts_setup()        # pages, tickets, change requests
        journal.setup()          # investigations
        forget_artifacts()

    print("\n  back to empty.")
    print(f"  Next:  {'python cli.py run all' if SCHEMA in wanted else 'python cli.py investigate surge_coverage_pct'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
