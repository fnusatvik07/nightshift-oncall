"""Tools that read code and history. They cannot read the database.

That split is deliberate and it is the most important design decision in the
agent system.

The data detective can query the warehouse and cannot open a file. The lineage
detective can open files and cannot query the warehouse. Neither can do the
other's job, so neither can quietly become a general purpose agent that does
everything badly.

An agent with every tool will use every tool. Give it four.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

from langchain.tools import tool

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Only these directories are readable. Not the .env, not the notebooks, not
# whatever else ends up in the repo later.
READABLE = ("pipelines", "signals", "signal_service", "agent_service",
            "seed", "airflow", "platform")

MAX_CHARS = 12_000


def _resolve(path: str) -> pathlib.Path | None:
    """Resolve a repo relative path, refusing anything outside the allow list."""
    p = (ROOT / path).resolve()
    try:
        rel = p.relative_to(ROOT)
    except ValueError:
        return None                      # tried to escape the repo
    if not rel.parts or rel.parts[0] not in READABLE:
        return None
    return p if p.is_file() else None


@tool
def list_pipelines() -> str:
    """List the pipeline files, so you know what can be read."""
    out = []
    for folder in ("pipelines", "signal_service", "signals"):
        for p in sorted((ROOT / folder).rglob("*.py")):
            if "__pycache__" in str(p):
                continue
            rel = p.relative_to(ROOT)
            first = ""
            try:
                for line in p.read_text().splitlines():
                    if line.startswith('"""'):
                        first = line.strip('"').strip()
                        break
            except Exception:                       # noqa: BLE001
                pass
            out.append(f"{str(rel):46} {first[:70]}")
    return "\n".join(out)


@tool
def read_source(path: str) -> str:
    """Read one source file, whole, so you can see what it actually does.

    Paths are relative to the project root, for example
    'pipelines/p3_bronze_driver_app.py'. Only pipeline and service code is
    readable.
    """
    p = _resolve(path)
    if p is None:
        return (f"REFUSED: {path!r} is not readable. "
                f"Readable directories: {', '.join(READABLE)}")
    text = p.read_text()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n... truncated at {MAX_CHARS} characters"
    return text


@tool
def search_code(pattern: str) -> str:
    """Find where a string or regex appears across the pipeline and service code.

    Use this to answer "where does this column get written" and "who reads this
    field", which is usually faster than reading whole files.
    """
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        return f"REFUSED: {pattern!r} is not a valid regex: {e}"

    hits = []
    for folder in READABLE:
        for p in sorted((ROOT / folder).rglob("*.py")):
            if "__pycache__" in str(p):
                continue
            try:
                for n, line in enumerate(p.read_text().splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
                        if len(hits) >= 60:
                            return "\n".join(hits) + "\n... truncated"
            except Exception:                       # noqa: BLE001
                continue
    return "\n".join(hits) if hits else f"no match for {pattern!r}"


@tool
def recent_changes(path: str = "", days: int = 30) -> str:
    """What changed recently, from git. Optionally for one path.

    Ask this early. Most incidents are somebody's Tuesday afternoon commit, and
    the commit message usually says what they thought they were doing.
    """
    if path:
        p = _resolve(path)
        if p is None:
            return f"REFUSED: {path!r} is not readable."

    cmd = ["git", "log", f"--since={days}.days", "--date=short",
           "--pretty=format:%h  %ad  %an  %s", "--name-only", "-n", "25"]
    if path:
        cmd += ["--", path]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
    except Exception as e:                          # noqa: BLE001
        return f"could not read git history: {type(e).__name__}: {e}"
    if r.returncode != 0:
        return ("no git history available here. "
                "Treat 'what changed recently' as unknown rather than as nothing.")
    return (r.stdout or "no commits in that window")[:MAX_CHARS]


@tool
def read_contract(pipeline: str) -> str:
    """Show just the contract of a pipeline: the values it knows how to read.

    Faster than reading the whole file when the question is "what was it
    willing to accept", which is the question most of the time.
    """
    p = _resolve(f"pipelines/{pipeline}.py") or _resolve(pipeline)
    if p is None:
        return f"REFUSED: no readable pipeline called {pipeline!r}"

    text = p.read_text()
    out = []
    for m in re.finditer(
            r"^([A-Z_]+(?:PATHS|STATUS|REQUIRED|KEYS|FIELDS))\s*=\s*[\(\{\[](.*?)[\)\}\]]",
            text, re.S | re.M):
        out.append(f"{m.group(1)} = {m.group(2).strip()[:600]}")
    return "\n\n".join(out) if out else "no contract constant found in that file"


LINEAGE_TOOLS = [list_pipelines, read_source, search_code, recent_changes, read_contract]
