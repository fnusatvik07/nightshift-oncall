"""BRONZE · regulator files.  Read gzipped CSV files out of object storage.

    reads   MinIO (S3)  kerb-landing/regulator/dt=YYYY-MM-DD/trips_audit.csv.gz
    writes  postgres    teach.bronze_regulator
    runs    daily at 02:00

WHY THIS ONE IS DIFFERENT
    The city regulator does not give us a database, a stream or an API. Once a
    day they drop a gzipped CSV file into a bucket. That is how an enormous
    amount of real data still arrives, and it brings three problems the other
    four sources do not have.

    1. THE PATH IS THE SCHEMA
       The file is at .../dt=2026-08-19/trips_audit.csv.gz. That `dt=` in the
       path is not decoration, it is the only place the date is recorded. It is
       not inside the file. This is called Hive style partitioning and you have
       to parse the path to know what you are looking at.

    2. A CSV HAS NO TYPES
       Every value arrives as a string. "9.0" is not the integer 9 until
       somebody makes it one, and int("9.0") raises. STEP 4 deals with that,
       and it is the single most common bug in file based pipelines.

    3. FILES ARRIVE LATE, OR TWICE, OR NOT AT ALL
       A database is always there. A file might be missing because the
       regulator's job failed, and "no file" is a completely different problem
       from "file with no rows in it". STEP 5 tells them apart.

RUN IT
    python -m pipelines.p5_bronze_regulator
    python -m pipelines.p5_bronze_regulator --days 3
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import os
import re
import sys

import psycopg
from minio import Minio

from .lib.config import SCHEMA, dsn
from .lib.run import Run, setup

TABLE = "bronze_regulator"
BUCKET = "kerb-landing"
PREFIX = "regulator/"

# The date lives in the path, so we need a pattern to get it out.
PARTITION = re.compile(r"dt=(\d{4}-\d{2}-\d{2})/")


# ══ STEP 1 · Describe the table, and keep the file it came from ══
#
# `source_file` is the column people forget, and it is the one that saves you.
#
# When a number looks wrong in six weeks, "which file did this row come from"
# is the first question anybody asks. Without this column the answer is a
# shrug. With it, you open that exact object in the bucket and look.
#
# The primary key is (partition_date, trip_id): the regulator can send the same
# ride on two different days, and both are real. Keying on trip_id alone would
# silently throw one of them away.
DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE} (
    partition_date DATE NOT NULL,    -- parsed from the path, not from the file
    trip_id        TEXT NOT NULL,
    pu_zone_id     INT,
    do_zone_id     INT,
    distance_km    NUMERIC(8,3),
    duration_s     INT,
    status         TEXT,
    source_file    TEXT NOT NULL,    -- exactly which object this row came from
    PRIMARY KEY (partition_date, trip_id)
);
"""


# ══ STEP 2 · Open the bucket ══
#
# MinIO speaks the S3 API, so this is the same code you would write against
# real S3 with a different endpoint. Nothing here is toy.
def open_bucket() -> Minio:
    return Minio(
        os.environ["MINIO_ENDPOINT"].replace("http://", "").replace("https://", ""),
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False)      # http, because it is running on this laptop


# ══ STEP 3 · List the files, newest first, and take only what we need ══
#
# Never `list_objects` without a prefix on a real bucket. A production landing
# bucket has millions of objects and listing all of them to find yesterday's is
# how you get a very slow pipeline and a very large bill.
#
# The prefix does the filtering on the server side.
def recent_files(client: Minio, days: int) -> list:
    objects = list(client.list_objects(BUCKET, prefix=PREFIX, recursive=True))
    # sorted by name works because the date is in the path in ISO order.
    # That is not luck: whoever chose dt=YYYY-MM-DD made this sort correct.
    objects.sort(key=lambda o: o.object_name, reverse=True)
    return objects[:days]


# ══ STEP 4 · Read one file, and deal with everything being a string ══
#
# This is where file pipelines actually break.
#
# A CSV has no types. Every single value arrives as text. The regulator writes
# zone ids as "9.0" because whatever produced the file held them as floats, and
#
#     int("9.0")   ->   ValueError
#
# So we go through float first and then to int. That looks fussy until the
# first time a pipeline dies at 2am on a value that looks perfectly fine.
#
# Every conversion is wrapped, because one malformed row in a file of 1,200
# must not throw away the other 1,199.
def as_int(value: str):
    """'9.0' -> 9, '9' -> 9, '' -> None. Never raises."""
    if value is None or value == "":
        return None
    return int(float(value))       # float() first: int('9.0') raises


def as_num(value: str):
    if value is None or value == "":
        return None
    return float(value)


def read_file(client: Minio, obj, run: Run) -> list:
    match = PARTITION.search(obj.object_name)
    if not match:
        # A file in an unexpected place. Hold the fact, do not guess a date.
        run.quarantine({"object": obj.object_name}, "path has no dt= partition")
        return []
    partition_date = match.group(1)

    raw = client.get_object(BUCKET, obj.object_name).read()
    text = gzip.decompress(raw).decode("utf-8")

    rows = []
    for line_no, rec in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        run.rows_in += 1
        try:
            rows.append((
                partition_date,
                rec["trip_id"],
                as_int(rec["pu_zone_id"]),
                as_int(rec["do_zone_id"]),
                as_num(rec["distance_km"]),
                as_int(rec["duration_s"]),
                rec["status"],
                obj.object_name))
        except Exception as e:
            run.quarantine(
                payload={"line": line_no, "record": rec, "file": obj.object_name},
                reason=f"{type(e).__name__}: {e}",
                key=rec.get("trip_id"))
    return rows


INSERT = f"""
    INSERT INTO {SCHEMA}.{TABLE}
        (partition_date, trip_id, pu_zone_id, do_zone_id, distance_km,
         duration_s, status, source_file)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (partition_date, trip_id) DO NOTHING
"""


# ══ STEP 5 · Tell "no file" apart from "empty file" ══
#
# These two look identical in a row count and mean completely different things:
#
#     no file        the regulator's job failed. Somebody should call them.
#     empty file     the regulator ran and had nothing to send. Fine.
#
# A pipeline that treats them the same will either page you every quiet weekend
# or stay silent through a genuine outage. So we count files as well as rows,
# and say both numbers out loud in the run message.
def run(days: int = 7) -> int:
    setup()
    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(DDL)

    with Run("p5_bronze_regulator") as r:
        client = open_bucket()
        files = recent_files(client, days)

        if not files:
            # Not an exception. A real, reportable state: they sent nothing.
            r.message = "NO FILES FOUND - the regulator has sent us nothing"
            return 0

        all_rows = []
        for obj in files:
            all_rows.extend(read_file(client, obj, r))

        if all_rows:
            with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
                cur.executemany(INSERT, all_rows)
                c.commit()

        r.rows_out = len(all_rows)
        r.message = f"{len(files)} file(s) read, newest {files[0].object_name}"
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=7, help="how many daily files to read")
    return run(ap.parse_args().days)


if __name__ == "__main__":
    sys.exit(main())
