from __future__ import annotations
import os, sys
import psycopg
from .lib.config import SCHEMA, dsn

DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.heartbeat (
    ran_at  TIMESTAMPTZ DEFAULT now(),
    slot    TEXT,            -- which scheduled minute this run is FOR
    run_id  TEXT             -- which Airflow run wrote it
);
"""

def main() -> int:
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)
        c.execute(f"INSERT INTO {SCHEMA}.heartbeat (slot, run_id) VALUES (%s, %s)",
                  (os.environ.get("SLOT", "by hand"),
                   os.environ.get("AIRFLOW_CTX_DAG_RUN_ID", "not airflow")))
    print("  heartbeat: ok  one row written")
    return 0

if __name__ == "__main__":
    sys.exit(main())
