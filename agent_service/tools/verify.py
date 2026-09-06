"""Tools for the verifier: proving a change worked, rather than claiming it did.

An agent will happily tell you it fixed something. This one has to show **a
pipeline that ran and a number that moved.**

## Why this agent may run a pipeline when nothing else may write

Every other tool in this project is read only, and that is load bearing. This
one is not, so it needs a better argument than "the deck said so".

The argument is that **the pipelines are idempotent by construction**, which is
the first thing the whole course teaches. `write_window` deletes the window it
is about to rebuild and inserts it back inside one transaction. Running
`p7_silver_rides` twice produces the same table as running it once.

So running a pipeline does not change the answer. It **recomputes** it. That is
categorically different from an `UPDATE`, and it is the only reason this is
allowed.

It is still fenced:

    only the pipelines in ALLOWED, by name. Not an arbitrary command
    a timeout, so a hung pipeline cannot hold an investigation open forever
    no arguments the agent chooses, beyond the two that are already bounded
    every run leaves a row in teach.runs, exactly like a human running it

If you take one thing from this file: **an agent's permissions should follow
from a property of the thing it is allowed to do**, not from how much you trust
the model.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

from langchain.tools import tool

from signal_service import invariants as inv

ROOT = pathlib.Path(__file__).resolve().parents[2]
TIMEOUT = 300

# The only things that may be run, by name. A pipeline is safe to re-run
# because it rebuilds a window rather than appending to one.
ALLOWED = {
    "p1_bronze_trips": "the ride table, from Postgres",
    "p2_bronze_events": "the ride lifecycle, from the stream",
    "p3_bronze_driver_app": "the driver app documents, from MongoDB",
    "p4_bronze_settlements": "settlements, from the partner API",
    "p5_bronze_regulator": "the regulator's files, from object storage",
    "p6_bronze_zones": "the zone dimension, replaced whole",
    "p7_silver_rides": "one clean row per ride",
    "p8_gold_daily": "one row per day",
}

# Which pipelines have to run after a change, and in what order, so a fix to
# bronze actually reaches the number the signal watches.
DOWNSTREAM = {
    "p1_bronze_trips": ["p7_silver_rides", "p8_gold_daily"],
    "p2_bronze_events": ["p7_silver_rides", "p8_gold_daily"],
    "p3_bronze_driver_app": ["p7_silver_rides", "p8_gold_daily"],
    "p4_bronze_settlements": ["p7_silver_rides", "p8_gold_daily"],
    "p5_bronze_regulator": [],
    "p6_bronze_zones": ["p7_silver_rides", "p8_gold_daily"],
    "p7_silver_rides": ["p8_gold_daily"],
    "p8_gold_daily": [],
}


def _run_one(name: str) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, "-m", f"pipelines.{name}"],
                       cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0, out


@tool
def run_pipeline(name: str, with_downstream: bool = True) -> str:
    """Re-run one pipeline, and by default everything downstream of it.

    Use this after a change has actually been applied, to show that the
    pipeline runs and the number moves. Running it is safe: every pipeline in
    this project rebuilds a window inside one transaction, so running it twice
    gives the same table as running it once.

    with_downstream re-runs silver and gold too, because a fix in bronze does
    not reach the number a signal watches until they have run.

    A FAILING pipeline is sometimes the correct outcome. If the fix was a guard
    that refuses bad input, the pipeline failing on that input is the guard
    working. Read the output before deciding.
    """
    if name not in ALLOWED:
        return (f"REFUSED: {name!r} is not a pipeline. "
                f"Known: {', '.join(sorted(ALLOWED))}")

    order = [name] + (DOWNSTREAM[name] if with_downstream else [])
    lines = []
    for pipeline in order:
        try:
            ok, out = _run_one(pipeline)
        except subprocess.TimeoutExpired:
            lines.append(f"{pipeline}: TIMED OUT after {TIMEOUT}s")
            break
        lines.append(f"$ python -m pipelines.{pipeline}\n{out}")
        if not ok:
            lines.append(f"\n{pipeline} FAILED, so nothing after it was run.")
            break
    return "\n\n".join(lines)


@tool
def run_invariants() -> str:
    """Check every invariant: the things that must always be true.

    An invariant is not a signal. A signal watches a number that is usually in
    a range; an invariant is a statement that is never allowed to be false, like
    "silver has one row per ride" or "no fare is negative".

    Zero violations is the only passing result. Run this after any change: it is
    how you tell "the number came back" apart from "the number came back and
    something else broke".
    """
    report = inv.check_all()
    text = inv.summary_text(report)
    if report["violations"]:
        text += "\n\nVIOLATIONS IN DETAIL\n"
        for v in report["violations"]:
            text += (f"\n  {v['name']}  ({v['severity']}, {v['layer']})\n"
                     f"    {v['means']}\n"
                     f"    {v['violations']} violating row(s), for example:\n")
            for row in v["sample"][:3]:
                text += f"      {row}\n"
    return text


@tool
def check_file_on_disk(path: str, expected_text: str) -> str:
    """Confirm a change is really in the file, rather than only in a branch.

    A proposed change lives on a branch until somebody merges it. This is how
    you tell "the fix is written" apart from "the fix is applied", and getting
    those two confused is how an incident gets closed while still broken.
    """
    target = (ROOT / path).resolve()
    try:
        target.relative_to(ROOT)
    except ValueError:
        return f"REFUSED: {path!r} is outside the project."
    if not target.is_file():
        return f"{path} does not exist."

    body = target.read_text()
    if expected_text in body:
        return (f"{path} CONTAINS that text, so the change is applied on disk, "
                f"not just proposed.")
    return (f"{path} does NOT contain that text. The change has not been "
            f"applied. If a pull request was opened it is still waiting for a "
            f"human, and the number will not have moved.")


VERIFY_TOOLS = [run_pipeline, run_invariants, check_file_on_disk]
