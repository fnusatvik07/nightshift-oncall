"""nightshift: one command for everything in this course.

    python cli.py status              what exists right now
    python cli.py run all             every pipeline, in dependency order
    python cli.py run p1_trips        just one
    python cli.py board               the signal board
    python cli.py dashboard           the signal board, in a browser
    python cli.py deploy              make Airflow re-read the DAGs, now
    python cli.py reset               back to empty: data, incidents, artifacts
    python cli.py break               break something on purpose
    python cli.py fix                 put it back

  the two services:
    python cli.py api                 start the signal service       :8091
    python cli.py agent               start the agent service        :8092
    python cli.py kpis                the KPI catalogue, and who owns each
    python cli.py signals             evaluate every KPI right now
    python cli.py watch               run the signal board on a clock
    python cli.py invariants          the things that must always be true
    python cli.py incidents           what has breached, and what came of it
    python cli.py investigate <kpi>   run the agents, showing every step live

Everything is safe to run twice. Everything can be undone with `reset`.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

import psycopg

from pipelines.lib.config import SCHEMA, describe, dsn

# The order matters: p5 reads what the first four wrote. This list IS the
# dependency graph. In a real estate Airflow holds it; here it is six lines,
# and six honest lines beat a scheduler nobody can read.
ORDER = [
    # bronze: one pipeline per source type. These four could run in parallel.
    "p1_bronze_trips",         # a database table
    "p2_bronze_events",        # a stream
    "p3_bronze_driver_app",    # a document store
    "p4_bronze_settlements",   # somebody else's API
    "p5_bronze_regulator",     # files in object storage
    "p6_bronze_zones",         # a small reference table, copied whole
    # silver and gold read what bronze wrote, so they must come after it.
    "p7_silver_rides",
    "p8_gold_daily",
]

PY = sys.executable


def sh(*args) -> int:
    return subprocess.run([PY, *args]).returncode


def cmd_status(_) -> int:
    print(f"\n{describe()}\n")
    with psycopg.connect(dsn()) as c:
        names = [r[0] for r in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name", (SCHEMA,))]
        if not names:
            print(f"  schema '{SCHEMA}' is empty. Run: python cli.py run all\n")
            return 0
        print(f"  {'table':22} {'rows':>12}")
        for n in names:
            k = c.execute(f"SELECT count(*) FROM {SCHEMA}.{n}").fetchone()[0]
            print(f"  {n:22} {k:>12,}")
        print()
        rows = c.execute(f"""SELECT pipeline, status, rows_out,
                                    to_char(started_at,'HH24:MI:SS')
                             FROM {SCHEMA}.runs ORDER BY started_at DESC LIMIT 6""").fetchall()
        if rows:
            print(f"  {'last runs':22} {'status':10} {'wrote':>10}  at")
            for p, st, out, at in rows:
                print(f"  {p:22} {st:10} {out or 0:>10,}  {at}")
        print()
    return 0


def cmd_run(a) -> int:
    todo = ORDER if a.what == "all" else [a.what]
    for name in todo:
        if name not in ORDER:
            print(f"  no pipeline called '{name}'. One of: {', '.join(ORDER)}")
            return 2
        rc = sh("-m", f"pipelines.{name}")
        if rc != 0:
            print(f"\n  {name} failed. Stopping, because everything after it "
                  f"would be built on data that is not there.\n")
            return rc
    return 0


def cmd_board(_) -> int:
    return sh("-m", "signals.board")


def cmd_dashboard(a) -> int:
    print(f"\n  opening http://localhost:{a.port}   (ctrl-C to stop)\n")
    return sh("-m", "uvicorn", "signal_service.dashboard:app", "--host", "127.0.0.1",
              "--port", str(a.port), "--log-level", "warning")


DAGS = pathlib.Path(__file__).parent / "airflow" / "dags"
CONTAINER = "nightshift-airflow"


def cmd_deploy(_) -> int:
    """Make Airflow notice the DAGs in this repo, now rather than in 5 minutes.

    There is no copying to do. `airflow/dags/` in this project is mounted
    straight into the scheduler at /opt/airflow/dags, so saving a file here IS
    deploying it. Deploying a DAG really is nothing more than putting a python
    file where the scheduler can see it: no build, no registration, no restart.

    The only catch is timing. The scheduler rescans that folder on a timer, and
    five minutes is a long time to stand in front of a class, so this asks it
    to look now.
    """
    files = sorted(DAGS.glob("*.py"))
    if not files:
        print(f"  no DAG files in {DAGS}")
        return 1

    print(f"  {DAGS}")
    for f in files:
        print(f"    {f.name}")

    r = subprocess.run(["docker", "exec", CONTAINER, "airflow", "dags", "reserialize"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"\n  could not reach the {CONTAINER} container.")
        print("  Is the estate up?   docker compose -f platform/docker-compose.yml ps")
        return 1

    errors = subprocess.run(
        ["docker", "exec", CONTAINER, "airflow", "dags", "list-import-errors"],
        capture_output=True, text=True).stdout.strip()
    print(f"\n  import errors: {errors or 'none'}")

    listing = subprocess.run(["docker", "exec", CONTAINER, "airflow", "dags", "list"],
                             capture_output=True, text=True).stdout
    for line in listing.splitlines():
        if "dag_id" in line or "teach" in line:
            print(f"  {line}")

    print("\n  open http://localhost:8080")
    return 0


# ── the two services ───────────────────────────────────────────────────────

def cmd_api(a) -> int:
    """The signal service: thirteen KPIs behind an HTTP API.

    Everything it serves can also be had from this CLI. It exists because the
    agents talk to it over HTTP like any other client, which is what keeps the
    two services genuinely separate rather than two files in one process.
    """
    print(f"\n  signal service on http://localhost:{a.port}"
          f"   (try /signals, /kpis, /invariants)\n")
    return sh("-m", "uvicorn", "signal_service.api:app", "--host", "127.0.0.1",
              "--port", str(a.port), "--log-level", "warning")


def cmd_agent(a) -> int:
    """The agent service: waits on POST /incident and investigates what arrives."""
    print(f"\n  agent service on http://localhost:{a.port}"
          f"   (waiting for POST /incident)\n")
    return sh("-m", "uvicorn", "agent_service.worker:app", "--host", "127.0.0.1",
              "--port", str(a.port), "--log-level", "warning")


def cmd_kpis(_) -> int:
    from signal_service.kpis import CATALOGUE
    print(f"\n  {len(CATALOGUE)} KPIs\n")
    print(f"  {'name':26} {'owner':15} {'judged by':12} {'severity':9} watches")
    print("  " + "-" * 92)
    for k in CATALOGUE:
        how = "a rule" if k.judgement == "fixed" else "history"
        print(f"  {k.name:26} {k.owner:15} {how:12} {k.severity:9} {k.watches}")
    print()
    return 0


def cmd_signals(_) -> int:
    from signal_service import evaluate as ev
    rows = ev.evaluate_all()
    breached = [k.name for k, _r, v in rows if v.breached]
    print(f"\n  {len(rows)} signals, {len(breached)} breached\n")
    for kpi, reading, verdict in rows:
        if not reading.measured:
            print(f"    ----  {kpi.name:26} not measurable: {reading.error[:44]}")
            continue
        flag = "BREACH" if verdict.breached else "  ok  "
        z = f"z={verdict.z_score:>6}" if verdict.z_score is not None else " " * 8
        print(f"  {flag}  {kpi.name:26} {verdict.value:>13,.2f}{kpi.unit:<7}"
              f" normally {verdict.baseline:>12,.2f}  {z}")
    print()
    if breached:
        print("  raise them and wake the agents with:  python cli.py watch\n")
    return 1 if breached else 0


def cmd_watch(a) -> int:
    return sh("-m", "signal_service.scheduler", "--every", str(a.every))


def cmd_invariants(_) -> int:
    """The things that must always be true. Zero violations is the only pass."""
    from signal_service import invariants as inv
    report = inv.check_all()
    print()
    print(inv.summary_text(report))
    if report["violations"]:
        print("\n  VIOLATIONS IN DETAIL\n")
        for v in report["violations"]:
            print(f"  {v['name']}  ({v['severity']}, {v['layer']})")
            print(f"    {v['means']}")
            print(f"    {v['violations']} violating row(s):")
            for row in v["sample"][:3]:
                print(f"      {row}")
            print()
    print()
    return 1 if report["violations"] else 0


def cmd_incidents(_) -> int:
    """One row per cause, however many signals noticed it."""
    from signal_service import store
    rows = store.open_incidents(20)
    if not rows:
        print("\n  nothing has breached yet.\n")
        return 0
    print(f"\n  {len(rows)} most recent incidents\n")
    print(f"  {'incident':16} {'lead signal':26} {'sev':9} {'signals':>7}  "
          f"{'status':12} owners")
    print("  " + "-" * 100)
    for r in rows:
        print(f"  {r['incident_id']:16} {r['primary_kpi']:26} {r['severity']:9} "
              f"{r['signal_count']:>7}  {r['status']:12} {r['owners']}")
    print()
    return 0


def cmd_investigate(a) -> int:
    """Run the five agents against one breach, and show every step as it happens.

    This is the command to run in front of a class. It prints which specialist
    is working, every tool it calls with its arguments, what came back, and the
    typed verdict it reached, live, rather than a wall of text at the end.
    """
    import sys as _sys
    import time as _time

    from agent_service import journal, live
    from agent_service.supervisor import investigate
    from agent_service.tools.publish import setup as artifacts_setup
    from signal_service import correlate, evaluate as ev, store
    from signal_service.kpis import BY_NAME, get

    if not _sys.stdout.isatty() or a.no_colour:
        live.C.off()
    live.use(live.ConsoleReporter(show_results=not a.quiet))

    target = a.what

    # Every table this command touches, created before anything runs. Doing it
    # here rather than lazily means the run cannot get all the way to the end
    # and then fail while printing what it produced.
    store.setup()
    artifacts_setup()
    journal.setup()

    # ── find or build the incident ─────────────────────────────────────────
    if target.startswith("INC"):
        incident = store.load_incident(target)
        if incident is None:
            print(f"  no incident called {target!r}")
            return 1
    elif target.startswith("BRC"):
        breach = store.load(target)
        if breach is None:
            print(f"  no breach called {target!r}")
            return 1
        incident = correlate.group([breach], board_size=len(BY_NAME))[0]
        store.record_incident(incident)
    else:
        if target not in BY_NAME:
            print(f"  no KPI called {target!r}. Try: python cli.py kpis")
            return 1
        kpi = get(target)
        reading, verdict = ev.evaluate(kpi)
        if not reading.measured:
            print(f"  {target} could not be measured: {reading.error}")
            return 1
        if not verdict.breached:
            print(f"\n  note: {target} is not currently breached "
                  f"({verdict.value}{kpi.unit}, normally {verdict.baseline:g}{kpi.unit}). "
                  f"Investigating anyway.")
        breach = ev.to_breach(kpi, reading, verdict)
        store.record(breach)
        incident = correlate.group([breach], board_size=len(BY_NAME))[0]
        store.record_incident(incident)

    # ── the header ─────────────────────────────────────────────────────────
    C = live.C
    print()
    print(f"  {C.BOLD}{'═' * 78}{C.OFF}")
    print(f"  {C.BOLD}INCIDENT {incident.incident_id}{C.OFF}   "
          f"severity {incident.severity}   owners {', '.join(incident.owners)}")
    print(f"  {C.BOLD}{'═' * 78}{C.OFF}")
    for b in incident.breaches:
        print(f"    {b.kpi:26} {b.value:>12,.2f}{b.unit:<7} normally "
              f"{b.baseline:>12,.2f}{b.unit}")
    if incident.signal_count > 1:
        print(f"\n    {C.DIM}grouped because: {incident.correlation}{C.OFF}")
    print(f"\n    {C.DIM}{incident.primary.how_unusual()}{C.OFF}")
    print(f"\n  {C.DIM}five specialists, called in order. Nothing here changes a "
          f"number.{C.OFF}")

    started = _time.time()
    journal.start(incident)
    try:
        out = investigate(incident)
    except Exception as e:                                  # noqa: BLE001
        journal.end(incident.incident_id, "failed", error=f"{type(e).__name__}: {e}")
        raise
    took = _time.time() - started
    journal.end(incident.incident_id,
                "waiting_for_human" if out["waiting_for_human"] else "done",
                steps=" -> ".join(s["tool"] for s in out["steps"]),
                handover=out["handover"])

    # ── the handover ───────────────────────────────────────────────────────
    print()
    print(f"  {C.BOLD}{'═' * 78}{C.OFF}")
    print(f"  {C.BOLD}HANDOVER{C.OFF}   {C.DIM}{' -> '.join(s['tool'] for s in out['steps'])}"
          f"   ({took:.0f}s){C.OFF}")
    print(f"  {C.BOLD}{'═' * 78}{C.OFF}\n")
    print(out["handover"])

    if out["waiting_for_human"]:
        print(f"\n  {C.AMBER}{C.BOLD}PAUSED. A data change needs a person to approve "
              f"it before anything else happens.{C.OFF}")

    _print_artifacts(incident.incident_id, C)
    return 0


def _print_artifacts(incident_id: str, C) -> None:
    """What the investigation left behind, for a person to act on."""
    from signal_service import store

    ids = [incident_id]
    incident = store.load_incident(incident_id)
    if incident:
        ids += [b.breach_id for b in incident.breaches]

    with psycopg.connect(dsn()) as c:
        pages = c.execute("SELECT page_id, url FROM oncall.pages "
                          "WHERE breach_id = ANY(%s)", (ids,)).fetchall()
        tickets = c.execute("SELECT ticket_id, kind, severity, title FROM oncall.tickets "
                            "WHERE breach_id = ANY(%s)", (ids,)).fetchall()
        changes = c.execute("SELECT request_id, kind, status, coalesce(pr_url, '') "
                            "FROM oncall.change_requests WHERE breach_id = ANY(%s)",
                            (ids,)).fetchall()

    if not (pages or tickets or changes):
        return
    print(f"\n  {C.BOLD}WHAT IT PRODUCED{C.OFF}   {C.DIM}every one of these is for a "
          f"person to decide on{C.OFF}\n")
    for page_id, url in pages:
        print(f"    {C.GREEN}page{C.OFF}    {url or page_id}")
    for tid, kind, sev, title in tickets:
        print(f"    {C.GREEN}ticket{C.OFF}  {tid}  {kind}, {sev}  {title[:52]}")
    for rid, kind, status, pr in changes:
        print(f"    {C.AMBER}change{C.OFF}  {rid}  {kind}, {status}  {pr}")
    print()


def cmd_reset(a) -> int:
    flags = ["--warehouse"] if a.warehouse else ["--oncall"] if a.oncall else []
    return sh("reset.py", *flags)


def cmd_break(_) -> int:
    return sh("break_it.py")


def cmd_fix(_) -> int:
    return sh("break_it.py", "--fix")


def main() -> int:
    ap = argparse.ArgumentParser(prog="nightshift", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    r = sub.add_parser("run"); r.add_argument("what", nargs="?", default="all")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("board").set_defaults(fn=cmd_board)
    d = sub.add_parser("dashboard"); d.add_argument("--port", type=int, default=8099)
    d.set_defaults(fn=cmd_dashboard)
    sub.add_parser("deploy").set_defaults(fn=cmd_deploy)
    ap_api = sub.add_parser("api"); ap_api.add_argument("--port", type=int, default=8091)
    ap_api.set_defaults(fn=cmd_api)
    ag = sub.add_parser("agent"); ag.add_argument("--port", type=int, default=8092)
    ag.set_defaults(fn=cmd_agent)
    sub.add_parser("kpis").set_defaults(fn=cmd_kpis)
    sub.add_parser("signals").set_defaults(fn=cmd_signals)
    watch = sub.add_parser("watch")
    watch.add_argument("--every", type=int, default=60, help="seconds between cycles")
    watch.set_defaults(fn=cmd_watch)
    sub.add_parser("invariants").set_defaults(fn=cmd_invariants)
    sub.add_parser("incidents").set_defaults(fn=cmd_incidents)
    inv = sub.add_parser("investigate")
    inv.add_argument("what", help="a KPI name, a breach id, or an incident id")
    inv.add_argument("--quiet", action="store_true",
                     help="show the steps but not what each tool returned")
    inv.add_argument("--no-colour", action="store_true")
    inv.set_defaults(fn=cmd_investigate)
    rs = sub.add_parser("reset")
    rs.add_argument("--warehouse", action="store_true",
                    help="reset only the data, keeping incidents and artifacts")
    rs.add_argument("--oncall", action="store_true",
                    help="reset only the incidents and artifacts, keeping the data")
    rs.set_defaults(fn=cmd_reset)
    sub.add_parser("break").set_defaults(fn=cmd_break)
    sub.add_parser("fix").set_defaults(fn=cmd_fix)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
