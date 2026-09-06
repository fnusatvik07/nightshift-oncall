"""Where everything lives, and how to reach it.

One file, because a student who is chasing a connection string across four
modules has stopped learning about pipelines and started learning about our
folder layout.

Read this once and you know every address in the system.
"""
from __future__ import annotations

import os
import pathlib

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[2]
# override=False on purpose: a variable already set in the environment WINS.
# That single flag is what lets the same code run on a laptop, where the
# database is at localhost, and inside the Airflow container, where it is at
# the hostname "postgres". Nothing in the pipelines changes between the two.
load_dotenv(ROOT / ".env", override=False)

# ── where we READ from ──────────────────────────────────────────────────────
# These are somebody else's systems. We never write to them.
SOURCE_DB = dict(
    host=os.environ["POSTGRES_HOST"], port=os.environ["POSTGRES_PORT"],
    dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
MONGO_URI = os.environ["MONGO_URI"]
KAFKA = os.environ["REDPANDA_BROKERS"]
TOPIC_RIDES = "kerb.trips.lifecycle"

# ── where we WRITE to ───────────────────────────────────────────────────────
# Everything this course builds lands in one schema, and nothing else on the
# machine writes there. That is what makes `reset` safe to run in front of a
# room: it drops this one schema and nothing of anyone else's is at risk.
SCHEMA = "teach"


def dsn() -> str:
    """A connection string, built when it is needed rather than at import.

    Built lazily on purpose. If this ran at import time, simply importing the
    module with the database down would raise, and the error would point at an
    import line rather than at the connection that actually failed.
    """
    p = SOURCE_DB
    return (f"host={p['host']} port={p['port']} dbname={p['dbname']} "
            f"user={p['user']} password={p['password']}")


def describe() -> str:
    return (f"reads   postgres {SOURCE_DB['host']}:{SOURCE_DB['port']}/{SOURCE_DB['dbname']}\n"
            f"        mongodb  {MONGO_URI.split('@')[-1]}\n"
            f"        kafka    {KAFKA}\n"
            f"writes  postgres schema '{SCHEMA}'  <- only ever this one")
