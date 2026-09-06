"""Small helpers so the notebooks read like a lesson and not like a REPL.

Nothing clever lives here. It exists so a cell can say `show(rows)` instead of
eight lines of formatting, and so every table in the course looks the same.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pandas as pd
import psycopg
from IPython.display import HTML, display

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.lib.config import SCHEMA, dsn      # noqa: E402

INK, MUTE, LINE = "#111114", "#6B7280", "#E4E4E7"
OK, BAD, BLUE = "#047857", "#B91C1C", "#1D4ED8"
SANS = '"Helvetica Neue",Helvetica,Arial,sans-serif'
MONO = '"SF Mono",Menlo,Consolas,monospace'


def say(text: str, kind: str = "note") -> None:
    """A short statement, set apart from the code that produced it."""
    bg, fg = {"note": ("#F5F5F7", MUTE), "good": ("#ECFDF5", OK),
              "bad": ("#FEF2F2", BAD), "key": ("#EFF4FF", BLUE)}[kind]
    display(HTML(f"<div style='font-family:{SANS};background:{bg};color:{fg};padding:14px 18px;"
                 f"border-radius:8px;font-size:15px;line-height:1.6;margin:10px 0'>{text}</div>"))


def show(df, title: str = "", limit: int = 10) -> None:
    """A dataframe, styled the same way everywhere in the course."""
    if title:
        display(HTML(f"<div style='font-family:{SANS};font-weight:600;font-size:15px;"
                     f"margin:14px 0 6px'>{title}</div>"))
    head = "".join(f"<th style='text-align:left;padding:9px 16px;border-bottom:2px solid {INK};"
                   f"font-size:11px;letter-spacing:.6px;text-transform:uppercase;color:{MUTE};"
                   f"white-space:nowrap'>{c}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(
        f"<td style='padding:8px 16px;border-bottom:1px solid {LINE};font-family:{MONO};"
        f"font-size:13px;white-space:nowrap'>{'' if pd.isna(v) else v}</td>" for v in r) + "</tr>"
        for _, r in df.head(limit).iterrows())
    more = (f"<div style='color:{MUTE};font-size:13px;padding:8px 2px'>"
            f"{len(df) - limit:,} more rows</div>") if len(df) > limit else ""
    display(HTML(f"<div style='font-family:{SANS};overflow-x:auto'>"
                 f"<table style='border-collapse:collapse'><thead><tr>{head}</tr></thead>"
                 f"<tbody>{body}</tbody></table>{more}</div>"))


def sql(query: str, title: str = "", limit: int = 10) -> None:
    """Run a query and draw it.

    Returns nothing on purpose. A function that both draws a table and returns
    it makes Jupyter render the same rows twice, once styled and once raw, and
    to a room seeing the tool for the first time that looks like a bug. Use
    `fetch` when you want the frame itself.
    """
    show(fetch(query), title, limit)


def fetch(query: str):
    """The same query, handed back as a DataFrame and not drawn."""
    with psycopg.connect(dsn()) as c:
        cur = c.execute(query)
        return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])


def run(*args) -> None:
    """Run a course command and print exactly what a terminal would print."""
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip() or "(no output)"
    display(HTML(f"<pre style='font-family:{MONO};font-size:13px;background:#0F172A;"
                 f"color:#E2E8F0;padding:16px 18px;border-radius:8px;overflow-x:auto;"
                 f"line-height:1.6'>$ python {' '.join(args)}\n\n{out}</pre>"))


def counts() -> None:
    """What is in our schema right now."""
    with psycopg.connect(dsn()) as c:
        names = [r[0] for r in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=%s ORDER BY table_name", (SCHEMA,))]
        rows = [(n, c.execute(f"SELECT count(*) FROM {SCHEMA}.{n}").fetchone()[0]) for n in names]
    if not rows:
        say(f"Schema <code>{SCHEMA}</code> is empty. Nothing has been built yet.", "note")
        return
    show(pd.DataFrame(rows, columns=["table", "rows"]), f"what is in '{SCHEMA}' right now", 20)


# ── showing real code, not describing it ────────────────────────────────────
# Every pipeline file is divided by markers like:
#
#     # ══ STEP 3 · Check every record against the contract ══
#
# These two helpers pull a step straight out of the file and print it. The
# notebook therefore shows the code that actually runs, and the two can never
# drift apart, which is what happens the moment you paste code into a lesson.

import re as _re
import textwrap as _tw

STEP_RE = _re.compile(r"^\s*#\s*══\s*STEP\s+(\d+)\s*·\s*(.+?)\s*══\s*$")


def _split_steps(path: str) -> dict:
    src = (ROOT / path).read_text().splitlines()
    steps, cur, title, num = {}, [], None, None
    for line in src:
        m = STEP_RE.match(line)
        if m:
            if num is not None:
                steps[num] = (title, "\n".join(cur).rstrip())
            num, title, cur = int(m.group(1)), m.group(2), []
        elif num is not None:
            cur.append(line)
    if num is not None:
        steps[num] = (title, "\n".join(cur).rstrip())
    return steps


def code(path: str, step: int | None = None, note: str = "") -> None:
    """Print real code out of a real file, so the class reads what runs.

        code('pipelines/p2_bronze_events.py', 3)
    """
    if step is None:
        body, title = (ROOT / path).read_text().rstrip(), path
    else:
        steps = _split_steps(path)
        if step not in steps:
            say(f"No step {step} in <code>{path}</code>. "
                f"It has: {sorted(steps)}", "bad")
            return
        title_txt, body = steps[step]
        title = f"{path}   ·   STEP {step}  ·  {title_txt}"
    body = _tw.dedent(body).strip("\n")
    lines = body.split("\n")
    width = len(str(len(lines)))
    numbered = "\n".join(f"<span style='color:#475569'>{i + 1:>{width}}</span>  {_esc(l)}"
                         for i, l in enumerate(lines))
    display(HTML(
        f"<div style='font-family:{SANS};font-size:12px;letter-spacing:.1em;"
        f"text-transform:uppercase;color:{MUTE};margin:16px 0 6px'>{_esc(title)}</div>"
        f"<pre style='font-family:{MONO};font-size:13px;line-height:1.65;background:#0F172A;"
        f"color:#E2E8F0;padding:18px 20px;border-radius:9px;overflow-x:auto;"
        f"white-space:pre'>{numbered}</pre>"
        + (f"<div style='font-family:{SANS};font-size:14.5px;color:{INK};line-height:1.6;"
           f"margin:10px 0 4px'>{note}</div>" if note else "")))


def steps_in(path: str) -> None:
    """List the steps a pipeline file is divided into."""
    steps = _split_steps(path)
    rows = "".join(
        f"<tr><td style='padding:7px 18px 7px 0;font-family:{MONO};font-size:13px;"
        f"color:{BLUE};font-weight:700'>STEP {k}</td>"
        f"<td style='padding:7px 0;font-size:14.5px'>{_esc(v[0])}</td></tr>"
        for k, v in sorted(steps.items()))
    display(HTML(f"<div style='font-family:{SANS}'><div style='font-weight:600;font-size:15px;"
                 f"margin:12px 0 8px'>{_esc(path)} is built in {len(steps)} steps</div>"
                 f"<table style='border-collapse:collapse'>{rows}</table></div>"))


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
