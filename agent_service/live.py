"""Watching the agents work, while they work.

An investigation takes a minute or two and, by default, prints nothing until it
is finished. In a service that is correct. In a classroom it is useless: the
room stares at a blank terminal and then a wall of conclusions, and learns
nothing about how the answer was reached.

So the specialists report as they go, through a reporter object that is installed
by whoever is running them.

    ConsoleReporter   prints a live trace. Used by `python cli.py investigate`
    NullReporter      prints nothing. Used by the service, which has logs

Nothing in the agents knows which one it has, so watching them costs the service
nothing and the classroom gets the whole story.
"""
from __future__ import annotations

import contextlib
import json
import threading
import time

# ── colours, on only when the terminal can show them ───────────────────────

class C:
    DIM = "\033[2m"
    BOLD = "\033[1m"
    OFF = "\033[0m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    AMBER = "\033[33m"
    RED = "\033[31m"
    GREY = "\033[90m"

    @classmethod
    def off(cls) -> None:
        for name in ("DIM", "BOLD", "OFF", "BLUE", "GREEN", "AMBER", "RED", "GREY"):
            setattr(cls, name, "")


class NullReporter:
    """Says nothing. The default, so importing this costs a service nothing."""

    def agent_start(self, name: str, question: str) -> None: ...
    def tool_call(self, agent: str, tool: str, args: dict) -> None: ...
    def tool_result(self, agent: str, tool: str, result: str) -> None: ...
    def agent_done(self, name: str, verdict, seconds: float) -> None: ...
    def note(self, text: str) -> None: ...


class ConsoleReporter(NullReporter):
    """A live trace of who is working, what they ran, and what they concluded."""

    # Colours are looked up by NAME and resolved when printing. Storing the
    # escape codes here would bake them in at import time, and C.off() called
    # later by a --no-colour flag would arrive too late to matter.
    LABEL = {
        "triage":            ("AMBER", "1 TRIAGE",            "is this real?"),
        "data_detective":    ("BLUE",  "2 DATA DETECTIVE",    "what is wrong with the rows?"),
        "lineage_detective": ("BLUE",  "3 LINEAGE DETECTIVE", "where did it enter?"),
        "remediation":       ("GREEN", "4 REMEDIATION",       "what is the smallest fix?"),
        "verifier":          ("GREEN", "5 VERIFIER",          "did it actually work?"),
    }

    @staticmethod
    def _colour(name: str) -> str:
        return getattr(C, name, "")

    def __init__(self, show_results: bool = True, width: int = 78):
        self.show_results = show_results
        self.width = width
        self._lock = threading.Lock()
        self._t0 = time.time()

    def _stamp(self) -> str:
        return f"{C.GREY}{time.time() - self._t0:6.1f}s{C.OFF}"

    def agent_start(self, name: str, question: str) -> None:
        key, label, asks = self.LABEL.get(name, ("BOLD", name.upper(), question))
        colour = self._colour(key)
        with self._lock:
            print()
            print(f"  {colour}{C.BOLD}{'─' * self.width}{C.OFF}")
            print(f"  {colour}{C.BOLD}{label}{C.OFF}   {C.DIM}{asks}{C.OFF}")
            print(f"  {colour}{'─' * self.width}{C.OFF}")

    def tool_call(self, agent: str, tool: str, args: dict) -> None:
        shown = ", ".join(f"{k}={_short(v, 46)}" for k, v in (args or {}).items())
        with self._lock:
            print(f"  {self._stamp()}  {C.BOLD}{tool}{C.OFF}({C.DIM}{shown}{C.OFF})")

    def tool_result(self, agent: str, tool: str, result: str) -> None:
        if not self.show_results:
            return
        lines = [ln for ln in str(result).splitlines() if ln.strip()][:6]
        with self._lock:
            for ln in lines:
                print(f"          {C.GREY}{ln[:self.width + 4]}{C.OFF}")
            if len(str(result).splitlines()) > 6:
                print(f"          {C.GREY}...{C.OFF}")

    def agent_done(self, name: str, verdict, seconds: float) -> None:
        colour = self._colour(self.LABEL.get(name, ("BOLD",))[0])
        with self._lock:
            print(f"  {self._stamp()}  {colour}{C.BOLD}-> {name} answered{C.OFF} "
                  f"{C.DIM}({seconds:.1f}s){C.OFF}")
            for line in _verdict_lines(verdict):
                print(f"          {line}")

    def note(self, text: str) -> None:
        with self._lock:
            print(f"\n  {C.DIM}{text}{C.OFF}")


def _short(value, n: int) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= n else text[:n - 1] + "…"


def _verdict_lines(verdict) -> list[str]:
    """A typed verdict, printed as fields rather than as JSON."""
    if verdict is None:
        return []
    data = verdict if isinstance(verdict, dict) else getattr(verdict, "__dict__", None)
    if data is None:
        with contextlib.suppress(Exception):
            data = json.loads(str(verdict))
    if not isinstance(data, dict):
        return [f"{C.DIM}{_short(verdict, 100)}{C.OFF}"]

    out = []
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        colour = ""
        if key in ("is_real", "resolved", "change_applied", "invariants_held"):
            colour = C.GREEN if value else C.RED
        elif key in ("severity", "confidence"):
            colour = C.AMBER
        text = _short(value, 96)
        out.append(f"{C.DIM}{key:18}{C.OFF} {colour}{text}{C.OFF}")
    return out


# ── the installed reporter ─────────────────────────────────────────────────

_reporter: NullReporter = NullReporter()


def use(reporter: NullReporter) -> None:
    global _reporter
    _reporter = reporter


def get() -> NullReporter:
    return _reporter
