"""Tools that read the warehouse. They cannot write to it.

## Two guards, and only one of them is about trust

**The syntactic guard** rejects anything that is not a single SELECT. It is
easy to read, easy to explain, and easy to fool: it is a string check.

**The read only transaction** is the one that matters. `conn.read_only = True`
means Postgres itself refuses the write, no matter what the model asked for or
how the query was spelled.

Say that distinction out loud in class, because it generalises:

> Whether an agent meant well is a judgement. Whether it CAN write is a fact.

Build on facts. The prompt is a request, not a constraint, and every rule you
enforce only in the system prompt is a rule you are hoping about.
"""
from __future__ import annotations

import re

import psycopg
from langchain.tools import tool

from pipelines.lib.config import SCHEMA, dsn

MAX_ROWS = 50
STATEMENT_TIMEOUT_MS = 15_000

# a single SELECT or WITH, and nothing else
_ALLOWED = re.compile(r"^\s*(select|with)\b", re.I)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|call|do|merge|refresh)\b", re.I)


def _query(sql: str, params: tuple = ()) -> str:
    """Run one read only statement and format the answer for a model to read."""
    stripped = sql.strip().rstrip(";")

    if not _ALLOWED.match(stripped):
        return "REFUSED: only a single SELECT or WITH statement is allowed here."
    if _FORBIDDEN.search(stripped):
        return "REFUSED: that statement would change something. These tools only read."
    if ";" in stripped:
        return "REFUSED: one statement at a time."

    try:
        with psycopg.connect(dsn()) as conn:
            # the guarantee. Not a promise in a prompt, a property of the session.
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
                cur.execute(stripped, params)
                cols = [d.name for d in cur.description] if cur.description else []
                rows = cur.fetchmany(MAX_ROWS)
                more = cur.fetchone() is not None
    except Exception as e:
        # Handing the error back is deliberate. An agent that is told its query
        # was wrong writes a better one; an agent that is told "an error
        # occurred" tries the same thing again.
        return f"QUERY FAILED: {type(e).__name__}: {e}"

    if not rows:
        return "0 rows."

    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows))
              for i, c in enumerate(cols)]
    head = "  ".join(str(c).ljust(w) for c, w in zip(cols, widths))
    body = "\n".join("  ".join(str(v).ljust(w) for v, w in zip(r, widths)) for r in rows)
    tail = f"\n... more rows, truncated at {MAX_ROWS}" if more else ""
    return f"{head}\n{'-' * len(head)}\n{body}{tail}"


# ── the tools ──────────────────────────────────────────────────────────────

@tool
def run_sql(query: str) -> str:
    """Run one read only SQL SELECT against the warehouse and return the rows.

    The warehouse schema is 'teach'. Useful tables: bronze_trips, bronze_events,
    bronze_driver_app, bronze_settlements, bronze_regulator, bronze_zones,
    silver_rides, gold_daily, runs, quarantine.

    Only a single SELECT or WITH statement is permitted. Results are capped.
    """
    return _query(query)


@tool
def list_tables() -> str:
    """List every table in the warehouse with its row count. Start here."""
    return _query(f"""
        SELECT c.relname AS table_name,
               to_char(c.reltuples::bigint, 'FM999,999,999') AS approx_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = '{SCHEMA}' AND c.relkind = 'r'
        ORDER BY c.relname
    """)


@tool
def describe_table(table: str) -> str:
    """Show the columns, types and nullability of one warehouse table."""
    return _query("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (SCHEMA, table.split(".")[-1]))


@tool
def profile_column(table: str, column: str) -> str:
    """Profile one column: how many rows, how many are null, how many distinct.

    This is usually the fastest way to see what is wrong with a number. A
    column that is 51% null did not used to be.
    """
    t = table.split(".")[-1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t) or \
       not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
        return "REFUSED: table and column must be plain identifiers."
    return _query(f"""
        SELECT count(*)                                              AS rows,
               count({column})                                       AS present,
               count(*) - count({column})                            AS missing,
               round(100.0 * (count(*) - count({column}))
                     / nullif(count(*), 0), 2)                       AS missing_pct,
               count(DISTINCT {column})                              AS distinct_values
        FROM {SCHEMA}.{t}
    """)


@tool
def recent_runs(limit: int = 15) -> str:
    """The pipeline run log: what ran, when, how many rows, and whether it worked.

    Read this before blaming the data. A pipeline that never ran leaves
    perfectly valid rows behind, and every value check will pass.
    """
    return _query(f"""
        SELECT pipeline, status, rows_in, rows_out,
               to_char(started_at, 'YYYY-MM-DD HH24:MI') AS started,
               round(extract(epoch FROM (ended_at - started_at))::numeric, 1) AS secs,
               left(coalesce(message, ''), 60) AS message
        FROM {SCHEMA}.runs ORDER BY started_at DESC LIMIT %s
    """, (min(limit, MAX_ROWS),))


@tool
def quarantine_summary() -> str:
    """What the contracts refused, grouped by pipeline and reason.

    Held records are the loudest evidence in the warehouse. If something is
    missing downstream, look here before anywhere else.
    """
    return _query(f"""
        SELECT pipeline, left(reason, 80) AS reason, count(*) AS records,
               to_char(max(seen_at), 'YYYY-MM-DD HH24:MI') AS latest
        FROM {SCHEMA}.quarantine
        GROUP BY 1, 2 ORDER BY 3 DESC
    """)


@tool
def quarantine_sample(pipeline: str, limit: int = 3) -> str:
    """Show whole held records for one pipeline, payload included.

    The payload is the original record, unchanged. This is where you find the
    field that moved, by reading it rather than guessing.
    """
    return _query(f"""
        SELECT reason, record_key, left(payload::text, 700) AS payload
        FROM {SCHEMA}.quarantine WHERE pipeline = %s
        ORDER BY seen_at DESC LIMIT %s
    """, (pipeline, min(limit, 5)))


READ_TOOLS = [run_sql, list_tables, describe_table, profile_column,
              recent_runs, quarantine_summary, quarantine_sample]
