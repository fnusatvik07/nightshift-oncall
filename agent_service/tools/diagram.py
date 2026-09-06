"""Drawing the incident, rather than describing it.

An architecture diagram on an incident page answers the question everybody asks
first and nobody writes down: **where in the flow did this break?**

The drawing is not decorative. It shows the path a value takes from the source
system to the number that moved, with the step where it went wrong marked in
red, and the steps that are fine marked as fine. A reader who knows the estate
can look at it and skip the rest of the page.

This reuses `diagrams/clean.py`, the same library the course notebooks use, so
an incident diagram looks like every other diagram in the project. It shells out
to the drawio CLI to export a PNG. If drawio is not installed, the page is
published without the picture rather than not published at all.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "diagrams"

# the layers a value passes through, in order
FLOW = [
    ("SOURCE", "the system that\nproduced the value"),
    ("INGEST", "the pipeline that\ncopied it in"),
    ("BRONZE", "the faithful copy"),
    ("SILVER", "one row per thing"),
    ("GOLD", "the number\nsomebody reads"),
]


def _layer_of(text: str) -> int:
    """Guess which band an evidence string is talking about.

    Deliberately simple. A wrong guess costs a mislabelled box on a diagram,
    which a reader corrects in their head in half a second, and the alternative
    is asking a model to pick from an enum and hoping.
    """
    t = (text or "").lower()

    # Order matters, and getting it wrong is easy. A path like
    # "pipelines/p3_bronze_driver_app.py" contains the word bronze, so a naive
    # check for table names first marks the wrong box. Code beats tables.
    if any(w in t for w in (".py", "contract", "pipeline", "loader", "parser",
                            "ingest")):
        return 1
    if "gold" in t:
        return 4
    if "silver" in t:
        return 3
    if "bronze" in t or "quarantine" in t:
        return 2
    return 0


def render(breach_id: str, kpi: str, title: str, broken_at: str,
           what_broke: str, source_name: str = "the source system") -> pathlib.Path | None:
    """Draw one incident. Returns the PNG path, or None if drawio is missing."""
    sys.path.insert(0, str(ROOT / "diagrams"))
    try:
        from clean import Deck, Page          # noqa: PLC0415
    except Exception:
        return None

    OUT.mkdir(parents=True, exist_ok=True)
    bad = _layer_of(broken_at)

    p = Page(breach_id, title[:90],
             f"{kpi} moved. This is where the value it depends on stops being readable.",
             cols=5, rows=2, row_h=330)

    boxes = []
    for i, (name, sub) in enumerate(FLOW):
        label = source_name if i == 0 else name
        if i < bad:
            kind, lines = "good", [sub.replace("\n", " "), "", "unaffected"]
        elif i == bad:
            kind, lines = "bad", [sub.replace("\n", " "), "", "THE VALUE IS LOST HERE"]
        else:
            kind, lines = "gate", [sub.replace("\n", " "), "", "carries the gap forward"]
        boxes.append(p.box(label, lines, i, 0, kind=kind))

    for a, b in zip(boxes, boxes[1:]):
        p.arrow(a, b)

    p.note(f"<b>What breaks here.</b> {what_broke}<br><br>"
           "<b>Read the colours.</b> Green is proved fine. Red is where the value "
           "stops being readable. Amber is every layer after it, which keeps working "
           "perfectly and reports a number built on less data than it should be. "
           "Nothing fails, no row count changes, and that is the whole problem.",
           0, 1, span=5)

    drawio_file = Deck(f"incident-{breach_id}", [p]).save()
    png = OUT / f"incident-{breach_id}.png"

    try:
        subprocess.run(
            ["drawio", "-x", "-f", "png", "-s", "2", "--no-sandbox", "-b", "30",
             "-p", "1", "-o", str(png), str(drawio_file)],
            capture_output=True, timeout=180)
    except Exception:
        return None
    finally:
        # clean.py writes the .drawio next to itself; keep the source with the
        # artifact so a human can edit the picture rather than redraw it
        try:
            drawio_file.replace(OUT / drawio_file.name)
        except Exception:
            pass

    return png if png.exists() else None
