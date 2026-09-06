"""The clock.

    python -m signal_service.scheduler                 every 60 seconds, forever
    python -m signal_service.scheduler --every 300     every five minutes
    python -m signal_service.scheduler --once          one cycle, then stop

This is the whole difference between a board you run and a board that runs. It
is thirty lines, and the thirty lines are not the interesting part: the
decisions around them are.

## Why a loop and not cron

Cron is fine, and for many teams it is the right answer. A loop is used here
because it can hold one thing cron cannot: **the memory of what it has already
raised.** Suppression, backoff and "this is the fourth time tonight" all need
state that survives between cycles, and a process that exits every minute has
none.

## Why it never dies

A scheduler that stops on the first error is a scheduler that was running
yesterday. Every cycle is wrapped: if the warehouse is down, it says so, waits,
and tries again. The only thing that stops this process is somebody stopping it.

## Why it is not the API

The API answers questions. The scheduler asks them on a timer. Keeping them
apart means a dashboard hammering `/signals` cannot slow down the clock, and a
slow clock cannot make the dashboard time out. They share a package and share
nothing else.
"""
from __future__ import annotations

import argparse
import datetime as dt
import signal
import sys
import time

from . import evaluate as ev
from . import store
from .emit import emit

_stopping = False


def _stop(signum, frame) -> None:            # noqa: ARG001
    """Finish the cycle we are in, then exit.

    Being killed halfway through an evaluation would leave readings written and
    breaches not, so the loop asks to be told and stops at a boundary.
    """
    global _stopping
    _stopping = True
    print("\n  stop requested. Finishing this cycle.")


def cycle(notify: bool = True) -> dict:
    """One pass over the catalogue. Never raises."""
    started = time.time()
    try:
        results = ev.evaluate_all()
    except Exception as e:                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "seconds": time.time() - started}

    try:
        store.save_readings([
            (k.name, v.value, r.error, v.breached, v.baseline, v.z_score)
            for k, r, v in results
        ])
    except Exception as e:                   # noqa: BLE001
        # Losing a reading is a shame. Losing the cycle is worse.
        print(f"    could not save readings: {type(e).__name__}: {e}")

    breached, actions = [], []
    for kpi, reading, verdict in results:
        if verdict.breached:
            breached.append(kpi.name)
            try:
                actions.append({"kpi": kpi.name,
                                **emit(ev.to_breach(kpi, reading, verdict), notify)})
            except Exception as e:           # noqa: BLE001
                actions.append({"kpi": kpi.name, "action": "failed",
                                "why": f"{type(e).__name__}: {e}"})

    return {
        "evaluated": len(results),
        "unmeasured": sum(1 for _, r, _ in results if not r.measured),
        "breached": breached,
        "actions": actions,
        "seconds": round(time.time() - started, 2),
    }


def _print_cycle(n: int, result: dict) -> None:
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    if "error" in result:
        print(f"  {stamp}  cycle {n}: could not evaluate. {result['error'][:70]}")
        return

    breached = result["breached"]
    head = (f"  {stamp}  cycle {n}: {result['evaluated']} evaluated, "
            f"{len(breached)} breached, {result['seconds']}s")
    if result["unmeasured"]:
        head += f", {result['unmeasured']} not measurable"
    print(head)
    for a in result["actions"]:
        why = a.get("why") or a.get("notify_failed") or ""
        print(f"             {a['kpi']:24} {a['action']:12} {a.get('breach_id', '')} {why}"
              .rstrip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--every", type=int, default=60, help="seconds between cycles")
    ap.add_argument("--once", action="store_true", help="one cycle, then stop")
    ap.add_argument("--no-notify", action="store_true",
                    help="record breaches but do not wake the agent system")
    a = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        store.setup()
    except Exception as e:                   # noqa: BLE001
        print(f"  cannot reach the warehouse: {type(e).__name__}: {e}")
        if a.once:
            return 1

    print(f"\n  signal board, every {a.every}s. Ctrl-C to stop.\n")

    n = 0
    while not _stopping:
        n += 1
        _print_cycle(n, cycle(notify=not a.no_notify))
        if a.once or _stopping:
            break
        # sleep in short steps so a stop is noticed quickly rather than after
        # a full interval
        for _ in range(a.every):
            if _stopping:
                break
            time.sleep(1)

    print("  stopped.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
