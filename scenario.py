"""One incident, told as a story, in seven steps.

    python cli.py scenario surge
    python cli.py scenario zones
    python cli.py scenario stale

`cli.py signals` and `cli.py investigate` each show one part of this well. Run
them back to back in front of a room and the join between them is missing: the
board goes red, and then, somehow, five agents are working. The most important
moment in the whole system happens in that gap and nobody sees it.

So this walks the whole thing, in order, and stops at each step:

    1  break it                 what moved, and where
    2  what landed              read 40,000, wrote 30,131, and the gap
    3  what was held            the record, with the reason and the payload
    4  the board measures       thirteen numbers, two of them red
    5  THE RECORD               the exact object that crosses between services
    6  handed to the agent      the POST, and what came back
    7  the agents work it       live, then what they left for a person

Step 5 is the one that earns the whole file. "The board hands the agent a
record" is abstract until somebody reads the record.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psycopg

import ui
from ui import C

ROOT = Path(__file__).parent
PY = sys.executable


def _run(*args, quiet: bool = True) -> str:
    r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


# ═══════════════════════════════════════════════════════════════════════════

def run(name: str, no_agent: bool = False) -> int:
    from break_it import AFTER, SCENARIOS
    from pipelines.lib.config import SCHEMA, dsn
    from signal_service import correlate, evaluate as ev, store
    from signal_service.kpis import BY_NAME

    if name not in SCENARIOS:
        print(f"  no scenario called {name!r}. One of: {', '.join(SCENARIOS)}")
        return 2

    _fn, owner, kpi_name, what = SCENARIOS[name]
    ui.C.auto()
    store.setup()

    ui.title(f"SCENARIO · {name}", what)
    ui.say()
    ui.kv("the signal", f"{C.BOLD}{kpi_name}{C.OFF}")
    ui.kv("who owns it", owner)
    ui.kv("what fails", f"{C.GREEN}nothing. That is the whole point{C.OFF}")

    # ── 1 · break it ───────────────────────────────────────────────────────
    ui.step(1, "BREAK IT", C.AMBER)
    out = _run("break_it.py", name)
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("python cli.py") or line.startswith("carry it"):
            continue
        if line.startswith("nothing failed"):
            ui.note(line)
        else:
            ui.say(line)

    # ── 2 · carry it into the warehouse ────────────────────────────────────
    ui.step(2, "RUN THE PIPELINES. WATCH NOTHING FAIL", C.AMBER)
    if not AFTER[name]:
        ui.note("this one needs no pipeline run: the aggregate simply never rebuilt.")
    for pipeline in AFTER[name]:
        text = _run("-m", f"pipelines.{pipeline}")
        for line in text.splitlines():
            if ": ok " in line:
                ui.good("  " + line.strip())
            elif ": started" in line:
                continue
            else:
                ui.note("  " + line.strip())

    with psycopg.connect(dsn()) as c:
        row = c.execute(f"""SELECT pipeline, rows_in, rows_out FROM {SCHEMA}.runs
                            WHERE status = 'success' AND rows_in > rows_out
                            ORDER BY started_at DESC LIMIT 1""").fetchone()
    if row:
        ui.say()
        ui.note(f"{row[0]} reported success. Look at the two numbers:")
        ui.gap(row[1], row[2])

    # ── 3 · what was held ──────────────────────────────────────────────────
    with psycopg.connect(dsn()) as c:
        held = c.execute(f"""SELECT pipeline, reason, count(*) FROM {SCHEMA}.quarantine
                             WHERE run_id IN (SELECT DISTINCT ON (pipeline) run_id
                                              FROM {SCHEMA}.runs WHERE status='success'
                                              ORDER BY pipeline, started_at DESC)
                             GROUP BY 1,2 ORDER BY 3 DESC LIMIT 3""").fetchall()
        sample = c.execute(f"""SELECT payload FROM {SCHEMA}.quarantine
                               ORDER BY seen_at DESC LIMIT 1""").fetchone()

    if held:
        ui.step(3, "WHAT WAS HELD, AND WHY", C.AMBER)
        ui.note("not dropped, not defaulted, not zeroed. Held, with the reason.")
        ui.say()
        for pipeline, reason, n in held:
            ui.say(f"{C.RED}{n:>8,}{C.OFF}  {C.DIM}{pipeline}{C.OFF}  {reason[:60]}")
        if sample:
            ui.say()
            ui.record(sample[0], "one held record, exactly as it arrived", limit=26)

    # ── 4 · the board measures ─────────────────────────────────────────────
    ui.step(4, "THE BOARD MEASURES, ON A CLOCK, OUTSIDE ALL OF THAT", C.BLUE)
    t0 = time.time()
    results = ev.evaluate_all()
    breached = [(k, r, v) for k, r, v in results if v.breached]
    ui.note(f"{len(results)} signals evaluated in {time.time() - t0:.2f}s. "
            f"It can block nothing, and it is not inside any pipeline.")
    ui.say()
    ui.signals_table([(k.name, v.value, k.unit, v.baseline, v.breached, k.owner)
                      for k, r, v in results])

    if not breached:
        ui.say()
        ui.bad("nothing breached. Something went wrong setting this up.")
        return 1

    # ── 5 · the record ─────────────────────────────────────────────────────
    ui.step(5, "THE RECORD THE BOARD WRITES", C.BLUE)
    ui.note("this is the ONLY object that crosses from the board to the agents.")
    ui.note("no shared database, no shared code. This, over HTTP.")
    ui.say()

    breaches = [ev.to_breach(k, r, v) for k, r, v in breached]
    for b in breaches:
        store.record(b)

    # Show THIS scenario's signal, not whichever happened to sort first.
    # records_held is red on a healthy estate by design, so without this the
    # story shows the wrong record at the most important moment in it.
    lead = next((b for b in breaches if b.kpi == kpi_name), breaches[0])
    ui.record(lead.model_dump(mode="json"),
              f"SignalBreach · {lead.breach_id}", limit=24)
    ui.say()
    ui.note("and the sentence that stops triage guessing:")
    ui.say(f"{C.AMBER}{lead.how_unusual()}{C.OFF}")

    # ── 6 · grouped, then handed over ──────────────────────────────────────
    ui.step(6, "GROUPED, THEN HANDED TO THE AGENT", C.BLUE)
    incidents = correlate.group(breaches, board_size=len(BY_NAME))
    for i in incidents:
        store.record_incident(i)
    incident = next((i for i in incidents
                     if any(b.kpi == kpi_name for b in i.breaches)), incidents[0])

    ui.say(f"{len(breaches)} breached signal(s)  {C.DIM}->{C.OFF}  "
           f"{C.BOLD}{len(incidents)} incident(s){C.OFF}")
    if incident.signal_count > 1:
        ui.say()
        ui.note("grouped because:")
        ui.say(f"{C.AMBER}{incident.correlation}{C.OFF}")
        ui.say()
        ui.note("one cause, one page, one person woken. Not five.")
    ui.say()
    ui.kv("incident", f"{C.BOLD}{incident.incident_id}{C.OFF}")
    ui.kv("severity", incident.severity, colour=C.RED)
    ui.kv("owners", ", ".join(incident.owners))
    ui.kv("signals", incident.signal_count)
    ui.say()
    ui.note("written to oncall.incidents FIRST. Only then is anybody told:")
    ui.say(f"  {C.GREEN}POST{C.OFF} http://localhost:8092/incident")
    ui.note("  if that POST fails the incident is still on disk, and /sweep "
            "picks it up.")
    ui.say()
    ui.record(json.dumps(incident.model_dump(mode="json"))[:0]
              or incident.brief(), "the brief the agents actually receive", limit=30)

    if no_agent:
        ui.step(7, "STOPPING HERE", C.GREY)
        ui.note("run the agents on it with:")
        ui.say(f"  python cli.py investigate {incident.incident_id}")
        print()
        return 0

    # ── 7 · the agents ─────────────────────────────────────────────────────
    ui.step(7, "THE AGENTS WORK IT. NOTHING BELOW CHANGES A NUMBER", C.GREEN)
    ui.note("five specialists, called in order, each with its own toolbox.")

    from cli import _print_artifacts
    from agent_service import journal, live
    from agent_service.supervisor import investigate
    from agent_service.tools.publish import setup as artifacts_setup

    artifacts_setup()
    journal.setup()
    live.use(live.ConsoleReporter())

    started = time.time()
    journal.start(incident)
    try:
        out = investigate(incident)
    except Exception as e:                                  # noqa: BLE001
        journal.end(incident.incident_id, "failed", error=f"{type(e).__name__}: {e}")
        raise
    journal.end(incident.incident_id,
                "waiting_for_human" if out["waiting_for_human"] else "done",
                steps=" -> ".join(s["tool"] for s in out["steps"]),
                handover=out["handover"])

    ui.title("HANDOVER", f"{' -> '.join(s['tool'] for s in out['steps'])}   "
                         f"({time.time() - started:.0f}s)", C.GREEN)
    print()
    print(out["handover"])

    if out["waiting_for_human"]:
        ui.say()
        ui.bad("PAUSED. A data change needs a person to approve it.")

    _print_artifacts(incident.incident_id, C)
    ui.note("every one of those is a proposal. Nothing was merged and no number "
            "was changed.")
    ui.say()
    ui.note(f"put it back with:  python cli.py fix")
    print()
    return 0
