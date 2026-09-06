"""The bookkeeping every pipeline does, so no pipeline has to write it twice.

A pipeline is not just "move some rows". Four things have to be true every
time, and if any one of them is missing you have a script rather than a
pipeline:

    1. It leaves a record that it ran, whether it worked or not.
    2. A record it cannot understand is kept, not silently dropped.
    3. A crash halfway through leaves no half-written table behind.
    4. Running it twice does not double the data.

`Run` gives you 1 and 2. `write_window` gives you 3 and 4.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager

import psycopg

from .config import SCHEMA, dsn

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};

-- every run of every pipeline, so "did it run?" is a question with an answer
CREATE TABLE IF NOT EXISTS {SCHEMA}.runs (
    run_id      TEXT PRIMARY KEY,
    pipeline    TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'running',
    rows_in     BIGINT DEFAULT 0,
    rows_out    BIGINT DEFAULT 0,
    message     TEXT
);

-- records we could not read, kept with the reason and the original payload
CREATE TABLE IF NOT EXISTS {SCHEMA}.quarantine (
    id         BIGSERIAL PRIMARY KEY,
    run_id     TEXT,
    pipeline   TEXT,
    reason     TEXT,
    record_key TEXT,
    payload    JSONB,
    seen_at    TIMESTAMPTZ DEFAULT now()
);
"""


def setup() -> None:
    """Create the schema and its two bookkeeping tables. Safe to call any time."""
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)


class Run:
    """One execution of one pipeline, recorded from start to finish.

        with Run("my_pipeline") as r:
            r.rows_in = 100
            r.rows_out = 98
            r.quarantine({"id": 7}, "amount was a word, not a number")

    The row is written the moment the block opens, so a pipeline that hangs
    still leaves evidence it started. If the block raises, the run is marked
    failed with the error text and the exception carries on: swallowing it
    would turn a broken pipeline into a quiet one.
    """

    def __init__(self, pipeline: str):
        self.pipeline = pipeline
        self.run_id = f"RUN{uuid.uuid4().hex[:12].upper()}"
        self.rows_in = 0
        self.rows_out = 0
        self.message = ""
        self._t0 = 0.0
        # Buffered. The first version opened a connection per quarantined
        # record, which turned 40,000 bad rows into three and a half minutes of
        # connection handshakes. Held rows are written in batches instead.
        self._held: list[tuple] = []

    def __enter__(self) -> "Run":
        setup()
        self._t0 = time.time()
        with psycopg.connect(dsn(), autocommit=True) as c:
            c.execute(f"INSERT INTO {SCHEMA}.runs (run_id, pipeline) VALUES (%s, %s)",
                      (self.run_id, self.pipeline))
        print(f"  {self.pipeline}: started  ({self.run_id})")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.flush()
        ok = exc_type is None
        msg = self.message if ok else f"{exc_type.__name__}: {exc}"
        with psycopg.connect(dsn(), autocommit=True) as c:
            c.execute(f"""UPDATE {SCHEMA}.runs
                          SET ended_at = now(), status = %s,
                              rows_in = %s, rows_out = %s, message = %s
                          WHERE run_id = %s""",
                      ("success" if ok else "failed",
                       self.rows_in, self.rows_out, msg[:500], self.run_id))
        secs = time.time() - self._t0
        flag = "ok" if ok else "FAILED"
        print(f"  {self.pipeline}: {flag}  read {self.rows_in:,}  wrote {self.rows_out:,}  "
              f"in {secs:.1f}s  {msg}")
        return False      # never swallow the exception

    def quarantine(self, payload: dict, reason: str, key: str | None = None) -> None:
        """Keep a record we could not read, with the reason attached.

        This is the single most important line in the whole library. The
        alternative is `except: pass`, which turns a data problem into a
        mystery three weeks later.
        """
        self._held.append((self.run_id, self.pipeline, reason, key,
                           json.dumps(payload, default=str)))
        if len(self._held) >= 2000:
            self.flush()

    def flush(self) -> None:
        """Write the held records out. Called automatically when the run ends."""
        if not self._held:
            return
        with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
            cur.executemany(f"""INSERT INTO {SCHEMA}.quarantine
                                (run_id, pipeline, reason, record_key, payload)
                                VALUES (%s, %s, %s, %s, %s)""", self._held)
            c.commit()
        self._held.clear()


@contextmanager
def write_window(table: str, partition_col: str, lo, hi):
    """Replace one window of a table, all at once or not at all.

    This is how a pipeline is made safe to re-run. Rather than appending, it
    deletes the window it is about to rebuild and inserts the new rows in the
    same transaction. Run it twice and you get the same table, not double the
    rows. Kill it halfway and the delete is rolled back with the insert, so a
    reader never sees a table with a hole in it.

        with write_window("trips", "trip_date", lo, hi) as cur:
            cur.executemany(f"INSERT INTO {SCHEMA}.trips ...", rows)
    """
    with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
        cur.execute(f"DELETE FROM {SCHEMA}.{table} "
                    f"WHERE {partition_col} >= %s AND {partition_col} < %s", (lo, hi))
        yield cur
        c.commit()
