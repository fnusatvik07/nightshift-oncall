"""How the command line looks, in one place.

The output of this project is the lesson. A wall of undifferentiated text is a
wall whatever it says, and a room reading a wall is a room that has stopped
listening, so the shape on the screen has to carry the argument: this is a step,
this is a number that moved, this is the record we hand over, this is what came
back.

Nothing here is decoration. Every device means one thing:

    a numbered step      one move in the story, in order
    a dim rail           everything indented under a step belongs to it
    green and red        a value that is fine, a value that is not
    a boxed record       an object crossing a boundary between two services

Colour turns itself off when the output is not a terminal, so a log file or a
notebook cell gets the same text without the escape codes.
"""
from __future__ import annotations

import json
import shutil
import sys

WIDTH = min(shutil.get_terminal_size((100, 24)).columns, 100)


class C:
    """Every colour used anywhere, and the switch that turns them all off."""

    DIM = "\033[2m"
    BOLD = "\033[1m"
    OFF = "\033[0m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    AMBER = "\033[33m"
    RED = "\033[31m"
    GREY = "\033[90m"
    CYAN = "\033[36m"
    INVERT = "\033[7m"

    NAMES = ("DIM", "BOLD", "OFF", "BLUE", "GREEN", "AMBER", "RED", "GREY",
             "CYAN", "INVERT")

    @classmethod
    def off(cls) -> None:
        for name in cls.NAMES:
            setattr(cls, name, "")

    @classmethod
    def auto(cls) -> None:
        """Colours on a terminal, plain text anywhere else."""
        if not sys.stdout.isatty():
            cls.off()


def plain(text: str) -> str:
    """The same string with the escape codes taken out, for measuring width."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "\033":
            while i < len(text) and text[i] != "m":
                i += 1
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def w(text: str) -> int:
    return len(plain(text))


# ── the shapes ─────────────────────────────────────────────────────────────

def title(text: str, subtitle: str = "", colour: str = "") -> None:
    """The heading a whole command sits under."""
    col = colour or C.BOLD
    print()
    print(f"  {col}{'═' * WIDTH}{C.OFF}")
    print(f"  {col}{C.BOLD}{text}{C.OFF}"
          + (f"   {C.DIM}{subtitle}{C.OFF}" if subtitle else ""))
    print(f"  {col}{'═' * WIDTH}{C.OFF}")


def step(number, heading: str, colour: str = "") -> None:
    """One move in the story. Everything after it is indented under it."""
    col = colour or C.CYAN
    badge = f" {number} "
    line = f"{col}{C.INVERT}{C.BOLD}{badge}{C.OFF}{col}{C.BOLD} {heading} {C.OFF}"
    print()
    print(f"  {line}{col}{'─' * max(0, WIDTH - w(line) - 1)}{C.OFF}")


def say(text: str = "", indent: int = 5) -> None:
    print(" " * indent + text)


def note(text: str, indent: int = 5) -> None:
    print(" " * indent + f"{C.DIM}{text}{C.OFF}")


def good(text: str, indent: int = 5) -> None:
    print(" " * indent + f"{C.GREEN}{text}{C.OFF}")


def bad(text: str, indent: int = 5) -> None:
    print(" " * indent + f"{C.RED}{C.BOLD}{text}{C.OFF}")


def kv(key: str, value, width: int = 18, indent: int = 5, colour: str = "") -> None:
    print(" " * indent + f"{C.DIM}{key:<{width}}{C.OFF} {colour}{value}{C.OFF}")


def arrow(text: str, indent: int = 5) -> None:
    print(" " * indent + f"{C.DIM}->{C.OFF} {text}")


def record(obj, heading: str = "", limit: int = 40, indent: int = 5) -> None:
    """An object crossing a boundary, boxed so it reads as a THING.

    This exists because "the board hands the agent a record" is abstract until
    somebody sees the record. It is the only object that crosses between the two
    services, and a class should be able to read every field of it.
    """
    body = obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str)
    lines = body.splitlines()
    clipped = len(lines) > limit
    lines = lines[:limit]

    pad = " " * indent
    inner = WIDTH - indent + 1
    if heading:
        print(f"{pad}{C.DIM}┌─ {C.OFF}{C.BOLD}{heading}{C.OFF}"
              f"{C.DIM} {'─' * max(0, inner - w(heading) - 4)}┐{C.OFF}")
    else:
        print(f"{pad}{C.DIM}┌{'─' * (inner - 2)}┐{C.OFF}")

    for line in lines:
        print(f"{pad}{C.DIM}│{C.OFF} {_colour_json(line)}")
    if clipped:
        print(f"{pad}{C.DIM}│  ... {len(body.splitlines()) - limit} more line(s){C.OFF}")
    print(f"{pad}{C.DIM}└{'─' * (inner - 2)}┘{C.OFF}")


def _colour_json(line: str) -> str:
    """Keys dim, strings plain, numbers and booleans picked out."""
    if ":" not in line:
        return f"{C.GREY}{line}{C.OFF}"
    key, _, rest = line.partition(":")
    rest = rest.rstrip()
    tail = rest.strip().rstrip(",")
    colour = C.OFF
    if tail in ("true", "false", "null"):
        colour = C.AMBER
    elif tail[:1] == '"':
        colour = C.OFF
    elif tail.replace("-", "").replace(".", "").isdigit():
        colour = C.CYAN
    return f"{C.DIM}{key}:{C.OFF}{colour}{rest}{C.OFF}"


def signals_table(rows, indent: int = 5) -> None:
    """The board, with the breached lines made impossible to miss.

    rows: (name, value, unit, baseline, breached, owner)
    """
    for name, value, unit, baseline, breached, owner in rows:
        v = "--" if value is None else f"{value:,.2f}"
        b = "--" if baseline is None else f"{baseline:,.2f}"
        if breached:
            print(" " * indent
                  + f"{C.RED}{C.BOLD}BREACH{C.OFF}  {C.BOLD}{name:<24}{C.OFF}"
                  f"{C.RED}{C.BOLD}{v:>14}{unit:<7}{C.OFF}"
                  f"{C.DIM}normally {b:>12}{unit:<7} {owner}{C.OFF}")
        else:
            print(" " * indent
                  + f"{C.GREEN}  ok  {C.OFF}  {C.DIM}{name:<24}{v:>14}{unit:<7}"
                  f"normally {b:>12}{unit:<7} {owner}{C.OFF}")


def gap(rows_in: int, rows_out: int, indent: int = 5) -> None:
    """read N, wrote M, and the difference drawn so it cannot be skimmed past."""
    missing = rows_in - rows_out
    print(" " * indent + f"{C.DIM}read {C.OFF}{rows_in:>10,}"
          f"{C.DIM}    wrote {C.OFF}{rows_out:>10,}")
    if missing > 0:
        print(" " * indent + " " * 26 + f"{C.RED}{'─' * 11}{C.OFF}")
        print(" " * indent + " " * 15 + f"{C.RED}{C.BOLD}{missing:>10,} did not land{C.OFF}")
