"""Generate the course notebooks.

The rule this rewrite is built on: a notebook must SHOW the code, not run a
script and describe what happened. Every pipeline file is divided into numbered
steps, and the notebook prints each step straight out of the file, so the class
reads exactly what runs and the two can never drift apart.
"""
import nbformat as nbf

KERNEL = {"display_name": "NIGHTSHIFT oncall", "language": "python", "name": "nightshift-oncall"}


import sys as _sys, textwrap as _tw
_sys.path.insert(0, ".")
from nb import _split_steps      # the same extractor the helpers use


class NB:
    def __init__(self, filename):
        self.filename, self.cells = filename, []

    def step(self, path, n, note=""):
        """Embed one STEP of a real pipeline file as a markdown code fence.

        Read from disk when the notebook is generated, so the lesson and the
        code cannot drift. Rendered as markdown so it picks up the reader's own
        theme and syntax highlighting, rather than a black block that fights it.
        """
        title, body = _split_steps(path)[n]
        body = _tw.dedent(body).strip("\n")
        head = f"**`{path}`**  ·  STEP {n}  ·  {title}"
        tail = f"\n\n{note}" if note else ""
        self.md(f"{head}\n\n```python\n{body}\n```{tail}")
        return self

    def md(self, t):
        self.cells.append(nbf.v4.new_markdown_cell(t.strip())); return self

    def code(self, t):
        self.cells.append(nbf.v4.new_code_cell(t.strip())); return self

    def save(self):
        nb = nbf.v4.new_notebook(cells=self.cells)
        nb.metadata.kernelspec = KERNEL
        nb.metadata.language_info = {"name": "python", "version": "3.13"}
        nbf.write(nb, self.filename)
        c = sum(1 for x in self.cells if x.cell_type == "code")
        print(f"  {self.filename:44} {len(self.cells):>3} cells ({c} code)")


HEAD = """import sys; sys.path.insert(0, '.')
from nb import say, show, sql, fetch, run, counts, code, steps_in"""

# ═══════════════════════════════════════════════════════════════════════════
n = NB("01-what-is-a-pipeline.ipynb")
n.md("""
# 1 · What a data pipeline actually is

No experience needed. By the end of this notebook you will know what the job is
and what the words mean. In notebook 2 you write one.

---

## Start with a problem you already understand

KERB is a ride hailing company. When you book a ride, a row goes into a
PostgreSQL table called `kerb.trips`. That database has exactly one job: serve
riders and drivers, fast, right now.

Now the finance team asks: **how much did we earn last month?**

The obvious answer is *"query `kerb.trips`"*. Three things go wrong.

![](img/intro-1-why.png)

## So: make a copy

On our own hardware, on our own clock, shaped for the questions people actually
ask. **Everything in this course is that one idea, done carefully.**
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import psycopg
from pipelines.lib.config import dsn, SCHEMA

print('our schema is', SCHEMA)""")
n.md("""
---

## Look at the source before writing anything

Rule one of this job, and the one people skip.
""")
n.code("""sql(\"\"\"
    SELECT trip_id, requested_at, rider_id, driver_id, pu_zone_id,
           distance_km, duration_s, status
    FROM kerb.trips ORDER BY requested_at DESC LIMIT 5
\"\"\", 'kerb.trips, the newest five rides')""")
n.code("""sql(\"\"\"
    SELECT count(*) AS rides,
           min(date(requested_at)) AS first_day,
           max(date(requested_at)) AS last_day
    FROM kerb.trips
\"\"\", 'how much is there')""")
n.md("""
---

## The words you will hear, defined once

| word | what it means |
|---|---|
| **source** | a system that already exists and is not yours. You are a guest |
| **warehouse** | your copy, on your clock, shaped for questions |
| **pipeline** | a program that moves a defined slice from one to the other |
| **batch** | the records one run of a pipeline is holding |
| **window** | the slice of time this run is responsible for |
| **contract** | the values you already know how to read |
| **quarantine** | where a record goes when it breaks the contract |
| **run log** | one row per run, saying what happened |
| **idempotent** | running it twice is the same as running it once |

## Bronze, silver, gold

![](img/intro-2-layers.png)

The names do not matter. **The discipline does.** Each layer has one job, and
you can always walk backwards: from a number in gold, to the row in silver, to
the row in bronze, to the source.

---

## The sources you will actually read

Four of them, all real, all running on this laptop right now. Each one has a
different way of being awkward, and that is the point.
""")
n.code("""import subprocess

out = subprocess.run(['docker', 'ps', '--format', '{{.Names}}\\t{{.Status}}'],
                     capture_output=True, text=True).stdout

for line in sorted(out.strip().splitlines()):
    name, _, status = line.partition('\\t')
    if name.startswith('kerb-'):
        print(f'  {name:24} {status}')""")
n.md("""
| notebook | source | the awkward part |
|---|---|---|
| 2 | PostgreSQL `kerb.trips` | enormous, so you take a window |
| 3 | Kafka `kerb.trips.lifecycle` | your position lives on the broker, not in your database |
| 4 | MongoDB `driver_app_events` | no schema. Every release can change the shape |
| 5 | PayNimbus, over HTTP | a partner. Answers late, partially, or not at all |
| 6 | MinIO, gzipped CSV | no types at all. Everything is a string |

---

## What separates a pipeline from a script

![](img/intro-3-rules.png)

Those four rules are the entire course. Every pipeline you write obeys all four,
and `pipelines/lib/run.py` is where they are written down once so you do not
have to remember them.

## Here is one of them, right now
""")
n.code("""sql(f\"\"\"
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = '{SCHEMA}' ORDER BY table_name
\"\"\", f\"what is in '{SCHEMA}' before you start\")""")
n.code("""run('cli.py', 'status')""")
n.md("""
---

## Where everything lives

| | |
|---|---|
| `pipelines/` | the eight pipelines, one file each |
| `pipelines/lib/` | the four rules, written once |
| `signals/` | the board that notices when a number moves |
| `notebooks/` | these lessons |
| `cli.py` | `status`, `run all`, `board`, `reset`, `break`, `fix` |

And one command matters more than the rest:

```bash
python cli.py reset
```

**Everything in this course can be put back to nothing and rebuilt in seconds.**
Nothing you do can leave the estate in a state you cannot get out of, which is
what makes it safe to break things on purpose in notebook 9.

## What you learned

- A warehouse exists so reporting does not compete with the product
- **Look at the source first.** Shape, size, date range
- **Bronze copies. Silver joins. Gold answers.**
- A pipeline is idempotent, atomic, honest and observable. A script is none of those
- Four sources, four different ways of being awkward
- There is always a way back to zero
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("02-bronze-from-a-database.ipynb")
n.md("""
# 2 · Bronze, from a database

In notebook 1 you learned what a pipeline is. Now you write one, **in these
cells**, one component at a time, and watch each part produce output before the
next part uses it.

At the end you run the packaged version and confirm it does exactly the same
thing.

| | |
|---|---|
| **reads** | `kerb.trips` in PostgreSQL, somebody else's live table |
| **writes** | `teach.bronze_trips` in PostgreSQL, our copy |
| **runs** | hourly |

![](img/bronze-1-copy.png)
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts      # formatting helpers, nothing clever

import datetime as dt
import psycopg
from pipelines.lib.config import dsn, SCHEMA      # the one file that knows the addresses

print('our schema:', SCHEMA)""")
n.md("""
---

## Step 0 · Look at the source before you touch it

Nobody writes a pipeline against a table they have not looked at. Two questions
first: what does a row look like, and how much of it is there.
""")
n.code("""sql(\"\"\"
    SELECT trip_id, requested_at, rider_id, driver_id, pu_zone_id,
           distance_km, duration_s, status
    FROM kerb.trips
    ORDER BY requested_at DESC
    LIMIT 5
\"\"\", 'kerb.trips, the newest five rides')""")
n.code("""sql(\"\"\"
    SELECT count(*)                    AS rides,
           min(date(requested_at))     AS first_day,
           max(date(requested_at))     AS last_day,
           count(DISTINCT status)      AS distinct_statuses
    FROM kerb.trips
\"\"\", 'how much is there')""")
n.md("""
Three hundred and sixty thousand rides across a month. **A pipeline never reads
all of that.** In six months this table has fifty million rows and copying them
hourly is absurd.

So we rebuild a small window of recent days, over and over.

---

## Step 1 · Choose the window, and get it right

![](img/bronze-2-window.png)

The obvious answer is *"the last seven days, counting back from today"*, and it
is wrong here, twice over. Run this and see why.
""")
n.code("""with psycopg.connect(dsn()) as c:
    today_style = c.execute(\"\"\"
        SELECT count(*) FROM kerb.trips
        WHERE requested_at >= current_date - interval '7 days'
    \"\"\").fetchone()[0]

    max_day = c.execute('SELECT max(date(requested_at)) FROM kerb.trips').fetchone()[0]

    rides_on_max = c.execute(
        'SELECT count(*) FROM kerb.trips WHERE date(requested_at) = %s', (max_day,)).fetchone()[0]

print(f'counting back from today   : {today_style:,} rides')
print(f'max(date) in the table     : {max_day}, which holds {rides_on_max:,} rides')""")
n.md("""
**Zero.** The dataset was generated once and then sat still, so nothing is near
today, and you would spend twenty minutes wondering why your pipeline reads
nothing.

And `max(date)` is only safe until one stray test row dated next year drags the
anchor to a day holding a single ride.

So anchor on **the newest day that actually looks like a day of trading**.
""")
n.code("""def choose_window(days):
    \"\"\"Return (lo, hi) for the last `days` real days of trading.\"\"\"
    with psycopg.connect(dsn()) as c:
        newest = c.execute(\"\"\"
            SELECT date(requested_at)
            FROM kerb.trips
            GROUP BY 1
            HAVING count(*) > 100        -- ignore days with a handful of stray rows
            ORDER BY 1 DESC
            LIMIT 1
        \"\"\").fetchone()[0]

    # lo is inclusive, hi is exclusive. Always. Mixing those up is how you get a
    # pipeline that double counts one day, every single run.
    lo = newest - dt.timedelta(days=days - 1)
    hi = newest + dt.timedelta(days=1)
    return lo, hi

lo, hi = choose_window(7)
print(f'rebuilding {lo}  <=  requested_at  <  {hi}')""")
n.md("""
### Say the two bounds out loud

> **lo is inclusive. hi is exclusive.**

`hi` is the day *after* the last day we want. That is why the query below uses
`>= lo` and `< hi`, never `BETWEEN`. `BETWEEN` is inclusive at both ends, and a
pipeline that double counts one day every run is almost impossible to spot,
because every total looks *almost* right.

---

## Step 2 · Read that window out of the source

One query, one window. **No JOIN and no aggregation.** Bronze copies one source
table and nothing else. If you find yourself joining in a bronze pipeline, you
are building silver and should say so.
""")
n.code("""READ = \"\"\"
    SELECT trip_id,
           date(requested_at) AS trip_date,
           rider_id,
           driver_id,
           pu_zone_id,
           distance_km,
           duration_s,
           status
    FROM kerb.trips
    WHERE requested_at >= %s        -- inclusive
      AND requested_at <  %s        -- exclusive
    ORDER BY requested_at
\"\"\"

with psycopg.connect(dsn()) as c:
    rows = c.execute(READ, (lo, hi)).fetchall()

print(f'{len(rows):,} rides in the window')
print()
for r in rows[:3]:
    print(' ', r)""")
n.md("""
`rows` is now a list of plain python tuples. **That is all a pipeline ever
holds**: a batch of records it read, on the way to somewhere else.

---

## Step 3 · Make somewhere to put them

The table is created by the pipeline, not by a human running SQL by hand at some
point in the past that nobody wrote down. `IF NOT EXISTS` means a brand new
laptop and a three year old production database end up with exactly the same
shape.
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.bronze_trips (
    trip_id      TEXT PRIMARY KEY,   -- one row per ride, enforced by the database
    trip_date    DATE NOT NULL,      -- derived from requested_at, so we can rebuild a window
    rider_id     TEXT,
    driver_id    TEXT,               -- empty until a driver accepts, so nullable
    pickup_zone  INT,
    distance_km  NUMERIC(8,2),
    duration_s   INT,                -- seconds, exactly as the source has it
    status       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bronze_trips_date ON {SCHEMA}.bronze_trips (trip_date);
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

sql(f\"\"\"
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = '{SCHEMA}' AND table_name = 'bronze_trips'
    ORDER BY ordinal_position
\"\"\", 'the table we just created')""")
n.md("""
### Every column maps to one column in the source

Nothing invented, nothing renamed for taste. `trip_date` is the only derived
column, and it exists only so we have something to partition the window on in
step 5.

---

## Step 4 · The contract

A contract is **the set of values we already know how to interpret**. It is not
a validation rule and it is not a preference. It is a written record of what the
rest of the company has agreed a ride can be.
""")
n.code("""KNOWN_STATUS = {'completed', 'cancelled_rider', 'cancelled_driver', 'no_driver'}

sql(\"\"\"
    SELECT status, count(*) AS rides
    FROM kerb.trips
    GROUP BY 1 ORDER BY 2 DESC
\"\"\", 'what the source actually sends today')""")
n.md("""
Four statuses, and our contract knows all four. **If a fifth ever appears**, one
of two things has happened: the product team shipped a new state and forgot to
tell anybody, or something upstream is corrupting the field.

Both are things you want to hear about on the day, not in three weeks.

![](img/bronze-3-piles.png)

## Now sort the batch into two piles

To see the held pile do its job, we pretend the source sent us one ride with a
status nobody has ever agreed on.
""")
n.code("""batch = list(rows)
batch.append(('TRP-PRETEND-1', lo, 'RDR000001', 'DRV000001', 42, 3.4, 600,
              'refunded_by_support'))       # <- a status nobody agreed on

keep, held = [], []
for rec in batch:
    status = rec[7]
    if status not in KNOWN_STATUS:
        held.append((rec, f'status {status!r} is not one of {sorted(KNOWN_STATUS)}'))
    else:
        keep.append(rec)

print(f'landed : {len(keep):,}')
print(f'held   : {len(held):,}')
for rec, reason in held:
    print(f'\\n  {rec[0]}')
    print(f'  {reason}')""")
n.md("""
### Held, not dropped, and not defaulted

The held record keeps **the record, the reason, and the original values**, so
the person who picks it up tomorrow has everything they need and does not have
to guess.

In the packaged pipeline this is `run.quarantine(...)`, which writes to a real
`teach.quarantine` table. You will read that table in notebook 9.

---

## Step 5 · Write the window, all at once or not at all

This is what makes the pipeline safe to run twice, and it is four lines.

Instead of appending, we **delete the window we are about to rebuild** and
insert the new rows **inside the same transaction**.
""")
n.code("""INSERT = f\"\"\"
    INSERT INTO {SCHEMA}.bronze_trips
        (trip_id, trip_date, rider_id, driver_id, pickup_zone, distance_km, duration_s, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
\"\"\"

def write_window(records, lo, hi):
    # autocommit=False: nothing is visible to anyone else until we commit
    with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
        cur.execute(f'DELETE FROM {SCHEMA}.bronze_trips '
                    f'WHERE trip_date >= %s AND trip_date < %s', (lo, hi))
        deleted = cur.rowcount
        cur.executemany(INSERT, records)
        c.commit()
    return deleted

deleted = write_window(keep, lo, hi)
print(f'deleted {deleted:,} rows, then inserted {len(keep):,}')

after = fetch(f'SELECT count(*) AS n FROM {SCHEMA}.bronze_trips').n[0]
print(f'the table now holds {after:,} rows')""")
n.md("""
## Run the exact same cell again

This is the property worth proving in front of the room.
""")
n.code("""deleted = write_window(keep, lo, hi)
again = fetch(f'SELECT count(*) AS n FROM {SCHEMA}.bronze_trips').n[0]

print(f'deleted {deleted:,}, inserted {len(keep):,}')
print(f'the table now holds {again:,} rows')
print()
print('same number' if again == after else 'DIFFERENT, something is wrong')""")
n.md("""
### Two properties fell out of those four lines

**Run it twice and you get the same table, not double the rows.** The delete
removes what the previous run wrote before the insert puts it back. That is
called being **idempotent**, and without it nobody can ever safely rerun
anything.

**Kill it halfway and nothing is lost.** The delete is rolled back along with
the insert, so a reader never sees a table with a hole in it. There is no moment
where the data is half deleted.

---

## And now the packaged pipeline

Everything above, in one file, plus the run log and the real quarantine table.
""")
n.code("""run('-m', 'pipelines.p1_bronze_trips', '--days', '7')""")
n.code("""sql(f\"\"\"
    SELECT pipeline, status, rows_in, rows_out,
           round(extract(epoch from (ended_at - started_at))::numeric, 2) AS secs, message
    FROM {SCHEMA}.runs
    WHERE pipeline = 'p1_bronze_trips'
    ORDER BY started_at DESC LIMIT 3
\"\"\", 'the run log, which every pipeline writes')""")
n.md("""
Note `rows_in` and `rows_out` are the **same number**. Nothing was held, because
the real source only ever sends the four statuses we agreed on. The one held
record earlier was our own invention.

## What is in the warehouse now
""")
n.code("""counts()""")
n.md("""
---

## What you learned

- **Look at the source first.** Shape, size, and date range, before any code
- A pipeline rebuilds **a window**, never the whole table
- Anchor the window **on the data**, not on today, and not on `max(date)`
- **lo inclusive, hi exclusive**, and never `BETWEEN`
- Bronze **copies**. No joins, no renames, no cleaning
- A contract is what you already know how to read. An unknown value is **held**,
  not dropped and not defaulted
- **Delete the window, then insert, in one transaction.** That one habit is what
  makes a pipeline safe to rerun
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("03-bronze-from-a-stream.ipynb")
n.md("""
# 3 · Bronze, from a stream

The last pipeline read **a table**. This one reads **a stream**, and almost
everything that is different about it comes from one fact:

> A table is a statement about how things **are**.
> A stream is a record of how they **got that way**.

| | |
|---|---|
| **reads** | Kafka topic `kerb.trips.lifecycle` |
| **writes** | `teach.bronze_events` in PostgreSQL |
| **runs** | every few minutes |

![](img/kafka-1-shape.png)

If the words **broker, topic, partition, offset, consumer group** are new, do
**notebook 10** first. It builds all of them from nothing. This notebook uses
them to write a pipeline.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import json
import psycopg
from confluent_kafka import Consumer, TopicPartition
from pipelines.lib.config import dsn, SCHEMA, KAFKA, TOPIC_RIDES

print('broker :', KAFKA)
print('topic  :', TOPIC_RIDES)""")
n.md("""
---

## Step 0 · Look at the source before you touch it

Same rule as last time. For a stream that means: how many messages are there,
and how far behind are we.
""")
n.code("""GROUP = 'teach-bronze-events'          # the name our position is stored under

def topic_facts():
    c = Consumer({'bootstrap.servers': KAFKA, 'group.id': GROUP,
                  'enable.auto.commit': False})
    parts = sorted(c.list_topics(TOPIC_RIDES, timeout=10).topics[TOPIC_RIDES].partitions)
    tps = [TopicPartition(TOPIC_RIDES, p) for p in parts]

    total = behind = 0
    print(f'{\"partition\":>10} {\"messages\":>12} {\"our position\":>14} {\"behind\":>10}')
    for tp, committed in zip(tps, c.committed(tps, timeout=10)):
        low, high = c.get_watermark_offsets(tp, timeout=10)
        at = committed.offset if committed.offset and committed.offset >= 0 else low
        total  += high - low
        behind += high - at
        print(f'{tp.partition:>10} {high - low:>12,} {at:>14,} {high - at:>10,}')
    c.close()
    print(f'{\"total\":>10} {total:>12,} {\"\":>14} {behind:>10,}')
    return behind

behind = topic_facts()""")
n.md("""
That last number has a name: **lag**. It is the single most watched number on
any streaming system, and it means *how many messages have been sent that we
have not read yet*.

## Read one message, and look at it
""")
n.code("""c = Consumer({'bootstrap.servers': KAFKA, 'group.id': 'notebook-peek',
              'enable.auto.commit': False})

# go to the last message on partition 0: high watermark minus one
low, high = c.get_watermark_offsets(TopicPartition(TOPIC_RIDES, 0), timeout=10)
c.assign([TopicPartition(TOPIC_RIDES, 0, high - 1)])

msg = None
for _ in range(20):
    m = c.poll(1.0)
    if m is not None and not m.error():
        msg = m
        break
c.close()

print(f'partition {msg.partition()}, offset {msg.offset()}\\n')
print(json.dumps(json.loads(msg.value()), indent=2))""")
n.md("""
### Note what a message is

**Bytes.** Not a row, not a dict, not a typed object. Somebody else's code
produced that JSON and pushed it, and nothing checked it on the way. It might
not be JSON at all. It might be JSON with the fields missing.

Everything below is written knowing that.

---

## Step 1 · The table, with a key that makes replays harmless

Look at the primary key. It is not one id column, it is **the pair
`(trip_id, event)`**.
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.bronze_events (
    trip_id     TEXT NOT NULL,
    event       TEXT NOT NULL,        -- requested, accepted, driver_arrived, started, completed
    happened_at TIMESTAMPTZ,
    driver_id   TEXT,
    fare        NUMERIC(10,2),        -- only present on the 'completed' event
    PRIMARY KEY (trip_id, event)      -- the whole reason a replay is boring
);
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

print('table ready')""")
n.md("""
That key is **a statement about the real world**: a given ride can only ever
have one `completed` event.

Saying it in the table definition means the database itself refuses a duplicate.
We do not write deduplication code, and we cannot forget to.

---

## Step 2 · The contract for a message
""")
n.code("""REQUIRED = ('trip_id', 'event', 'ts')

def parse(raw_bytes):
    \"\"\"Turn one raw message into a row, or explain why it cannot be one.

    Returns (row, None) or (None, reason). Never raises: one poison message
    must not stop the four hundred thousand behind it.
    \"\"\"
    try:
        d = json.loads(raw_bytes)
        missing = [k for k in REQUIRED if d.get(k) in (None, '')]
        if missing:
            return None, f\"missing required field(s): {', '.join(missing)}\"
    except Exception as e:
        return None, str(e)

    # .get() for the optional fields, [] for the required ones. That is not
    # style: a required field missing here would already have been caught above.
    return (d['trip_id'], d['event'], d['ts'], d.get('driver_id'), d.get('fare')), None

print('a real message :', parse(msg.value()))
print()
print('no ts          :', parse(b'{\"trip_id\":\"TRP1\",\"event\":\"started\",\"ts\":\"\"}'))
print('not even json  :', parse(b'<html>502 Bad Gateway</html>'))""")
n.md("""
**Three inputs, three different answers, no exception raised.** The good one
becomes a row. The other two come back with a reason a human can read.

---

## Give the pipeline something to read

The pipeline may already be caught up, in which case the loop below reads
nothing and proves nothing. So put ten rides on the topic first.
""")
n.code("""from confluent_kafka import Producer
import datetime as dt, random

producer = Producer({'bootstrap.servers': KAFKA})
LIFECYCLE = ['requested', 'accepted', 'driver_arrived', 'started', 'completed']
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

sent = 0
for _ in range(10):
    trip_id = f'TRP-NB3-{random.randint(10000, 99999)}'
    driver  = f'DRV{random.randint(1, 2800):06d}'
    for i, name in enumerate(LIFECYCLE):
        e = {'trip_id': trip_id, 'event': name,
             'ts': (now + dt.timedelta(minutes=i * 3)).isoformat(),
             'driver_id': None if name == 'requested' else driver,
             'pu_zone_id': random.randint(1, 60)}
        if name == 'completed':
            e['fare'] = round(random.uniform(60, 420), 2)
        # same key every time, so all five events of a ride stay on one partition
        producer.produce(TOPIC_RIDES, key=trip_id.encode(), value=json.dumps(e).encode())
        sent += 1

# one message nobody can read, so the held pile has something to do
producer.produce(TOPIC_RIDES, key=b'TRP-NB3-BROKEN',
                 value=json.dumps({'trip_id': 'TRP-NB3-BROKEN',
                                   'event': 'started', 'ts': ''}).encode())
producer.flush(10)

print(f'{sent} good events and 1 unreadable one are now on the topic')""")
n.code("""behind = topic_facts()""")
n.md("""
---

## Step 3 · Open a consumer, with auto-commit turned OFF

Four lines of configuration, and one of them is the most important line in the
whole pipeline.
""")
n.code("""consumer = Consumer({
    'bootstrap.servers': KAFKA,
    'group.id': GROUP,                # the name our position is stored under
    'auto.offset.reset': 'earliest',  # never read before? start at the beginning
    'enable.auto.commit': False,      # WE commit, after the write. See below.
})
consumer.subscribe([TOPIC_RIDES])

print('subscribed as', GROUP)""")
n.md("""
### Why `enable.auto.commit = False` is the line that matters

By default the Kafka library quietly saves your position **on a timer, in the
background**, whether or not your database write succeeded. Picture the order:

1. library reads 5,000 messages
2. the library's timer fires and saves *"I have read up to here"*
3. your process dies before writing them to Postgres

Those 5,000 messages are **gone**. Not delayed. Gone. The next run starts after
them, and nobody will ever know they existed, because there is no error and no
gap that anything can detect.

![](img/kafka-4-commit.png)

---

## Step 4 · Read, write, and only then save your position

Here is the whole loop. Read it, then run it.
""")
n.code("""INSERT = f\"\"\"
    INSERT INTO {SCHEMA}.bronze_events (trip_id, event, happened_at, driver_id, fare)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING          -- the same (trip, event) twice is fine, keep the first
\"\"\"

read_n = written = held = 0

while True:
    # Ask for a batch. Nothing within 3 seconds means we have caught up, and
    # catching up is how this pipeline ends.
    batch = consumer.consume(num_messages=5000, timeout=3.0)
    if not batch:
        break

    rows = []
    for m in batch:
        if m.error():
            continue
        read_n += 1
        row, reason = parse(m.value())
        if row is None:
            held += 1                      # the real pipeline writes these to quarantine
        else:
            rows.append(row)

    if rows:
        # FIRST: make the rows durable, in their own transaction.
        with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
            cur.executemany(INSERT, rows)
            c.commit()
        written += len(rows)

    # ONLY NOW is it true that we have consumed these messages, so only now do
    # we say so. asynchronous=False waits for the broker to confirm.
    consumer.commit(asynchronous=False)
    print(f'  batch: read {len(batch):,}  wrote {len(rows):,}  committed')

consumer.close()
print(f'\\ncaught up. read {read_n:,}, wrote {written:,}, held {held:,}')""")
n.md("""
## Are we caught up?
""")
n.code("""behind = topic_facts()""")
n.md("""
---

## Now prove a replay is harmless

This is the property the primary key bought us. Insert **the exact same rows
again** and watch the table not change.
""")
n.code("""before = fetch(f'SELECT count(*) AS n FROM {SCHEMA}.bronze_events').n[0]

# take 1,000 rows straight back out of the table and insert them again
with psycopg.connect(dsn()) as c:
    same = c.execute(f\"\"\"SELECT trip_id, event, happened_at, driver_id, fare
                        FROM {SCHEMA}.bronze_events LIMIT 1000\"\"\").fetchall()

with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    cur.executemany(INSERT, same)
    c.commit()

after = fetch(f'SELECT count(*) AS n FROM {SCHEMA}.bronze_events').n[0]
print(f'before  {before:,}')
print(f'after   {after:,}   (we just re-inserted 1,000 rows)')
print('\\nno change' if before == after else 'DIFFERENT, the key is not doing its job')""")
n.md("""
### That is why we can afford at-least-once

> **Duplicates you can remove. Missing data you cannot invent.**

Reading a message more than once is called **at-least-once** delivery, and it is
what almost every real streaming pipeline chooses. It only works because the
table refuses the second copy.

---

## And now the packaged pipeline

Same loop, plus quarantine and the run log.
""")
n.code("""run('-m', 'pipelines.p2_bronze_events')""")
n.code("""sql(f\"\"\"
    SELECT pipeline, status, rows_in, rows_out,
           round(extract(epoch from (ended_at - started_at))::numeric, 2) AS secs, message
    FROM {SCHEMA}.runs
    WHERE pipeline = 'p2_bronze_events'
    ORDER BY started_at DESC LIMIT 3
\"\"\", 'the run log')""")
n.md("""
## What one ride looks like once it has landed
""")
n.code("""sql(f\"\"\"
    SELECT trip_id, event, happened_at, driver_id, fare
    FROM {SCHEMA}.bronze_events
    WHERE trip_id = (SELECT trip_id FROM {SCHEMA}.bronze_events
                     WHERE event = 'completed' ORDER BY happened_at DESC LIMIT 1)
    ORDER BY happened_at
\"\"\", 'every event of one ride, in order')""")
n.md("""
**Five rows, one ride.** That is the difference from notebook 2, in one table.
`bronze_trips` has one row saying how that ride ended. `bronze_events` has the
whole story of how it got there.

---

## What you learned

- A stream is **bytes somebody else produced**. Nothing checked it on the way
- **Lag** is how many messages have been sent that you have not read
- The primary key `(trip_id, event)` is **a statement about the real world**,
  and it is what makes a replay boring
- `enable.auto.commit = False`, always. **You** decide when the position moves
- **Write the rows, then commit the offset.** Never the other way round
- `ON CONFLICT DO NOTHING` plus that key is the entire deduplication strategy
- One poison message must never block the ones behind it
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("04-bronze-from-documents.ipynb")
n.md("""
# 4 · Bronze, from documents

A third source, a third shape. This one is a **document store**: MongoDB.

| | |
|---|---|
| **reads** | MongoDB `kerb_app.driver_app_events` |
| **writes** | `teach.bronze_driver_app` in PostgreSQL |
| **runs** | hourly |

A table has a schema the database enforces. **A collection does not.** Two
documents sitting next to each other can have different fields, and nothing
anywhere complains.

That single fact is what this notebook is about.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import json
import psycopg
from pymongo import MongoClient
from pipelines.lib.config import dsn, SCHEMA, MONGO_URI

collection = MongoClient(MONGO_URI).kerb_app.driver_app_events
print(f'{collection.estimated_document_count():,} documents')
print('event types:', collection.distinct('event_type'))""")
n.md("""
---

## Step 0 · Look at one document

Not at the schema. There is no schema. Look at **a document**.
""")
n.code("""doc = collection.find_one({'event_type': 'trip_offer'})

print(json.dumps(doc, indent=2, default=str))""")
n.md("""
### Read the shape, not just the values

`app`, `device`, `location` and `payload` are **not values, they are more
documents**. The surge multiplier the pricing team cares about is buried at
`payload.surge_multiplier`.

![](img/docs-1-shape.png)

---

## Step 1 · The flat table we are landing into

Someone has to decide which nested values become columns, and that decision is
this DDL. We take **six fields out of a document that has eleven**.
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.bronze_driver_app (
    event_id    TEXT PRIMARY KEY,     -- the app's own id, so a re-read is harmless
    trip_id     TEXT,                 -- how this joins to rides later
    driver_id   TEXT,
    event_type  TEXT,
    happened_at TIMESTAMPTZ,
    app_version TEXT,                 -- nested at app.version
    surge       NUMERIC(6,2)          -- nested at payload.surge_multiplier
);
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

print('table ready')""")
n.md("""
---

## Step 2 · Walk a nested path without crashing

`doc['payload']['surge_multiplier']` raises `KeyError` if either level is
missing, and one `KeyError` stops the whole run over a single odd document.
""")
n.code("""def dig(doc, path):
    \"\"\"Follow a nested path, returning None the moment a level is not there.\"\"\"
    cur = doc
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur

print('surge       :', dig(doc, ('payload', 'surge_multiplier')))
print('app version :', dig(doc, ('app', 'version')))
print('missing     :', dig(doc, ('pricing', 'surge_multiplier')))
print('nonsense    :', dig(doc, ('payload', 'surge_multiplier', 'deeper')))""")
n.md("""
Four calls, no exception. `None` means **not found**, and step 4 decides what to
do about that.
""")
n.md("""
---

## Step 3 · The contract, which is a list of places

This is the most important cell in the notebook.

![](img/docs-2-moved.png)

Here is the contract as it was written **in July**, when three paths covered
every document anyone had seen.
""")
n.code("""SURGE_PATHS = (
    ('payload', 'surge_multiplier'),      # what the app sends today
    ('pricing', 'surge_multiplier'),      # where we GUESS release 4.2 will move it
    ('surge_multiplier',),                # the old flat shape, still in older documents
)

def surge_of(doc):
    \"\"\"The surge value, from whichever field this app version happened to use.\"\"\"
    for path in SURGE_PATHS:
        value = dig(doc, path)
        if value is not None:
            return value
    return None          # none of the known paths matched

today   = {'payload': {'surge_multiplier': 1.4}}
guessed = {'pricing': {'surge_multiplier': 1.4}}
ancient = {'surge_multiplier': 1.4}
unknown = {'payload': {'pricing': {'surgeFactor': 1.4}}}

for name, d in [('today', today), ('guessed', guessed),
                ('ancient', ancient), ('unknown', unknown)]:
    print(f'{name:9} -> {surge_of(d)}')""")
n.md("""
### Why a list, and not one path

Picture the failure this prevents.

The mobile team ships 4.2 and moves the field. A perfectly reasonable refactor.
They do not tell the data team, because why would they. And then:

| | |
|---|---|
| the pipeline does not fail | it reads the document fine |
| the rows still land | the count is unchanged |
| surge is just empty | on some rows, starting Tuesday |
| nobody notices | for three weeks |

**Every row count check you can write stays green through that.**

---

## Step 4 · Read the documents, and never default a missing value

![](img/docs-3-zero.png)

When `surge_of` returns `None` we **hold** the document. We do **not** write a
zero.

One detail in the query below matters more than it looks.
""")
n.code("""def read_batch(paths, limit=20000):
    \"\"\"Read the NEWEST documents and sort each into landed or held.\"\"\"
    keep, held = [], []

    # .sort('ts', -1) is not decoration. A collection hands back its OLDEST
    # documents first, and the oldest documents describe rides that fell out of
    # the bronze window weeks ago. Read from the wrong end and every column you
    # worked for arrives full of nulls in silver, with no error anywhere.
    for d in collection.find({'event_type': 'trip_offer'}).sort('ts', -1).limit(limit):
        surge = None
        for path in paths:
            surge = dig(d, path)
            if surge is not None:
                break

        if surge is None:
            held.append(d)
            continue

        keep.append((
            str(d.get('event_id') or d['_id']),
            d.get('trip_id'),
            d.get('driver_id'),
            d.get('event_type'),
            d.get('ts'),
            dig(d, ('app', 'version')),      # also nested, same problem, same solution
            surge))
    return keep, held

keep, held = read_batch(SURGE_PATHS)

print(f'landed : {len(keep):,}')
print(f'held   : {len(held):,}')""")
n.md("""
## There it is

Documents that match **none** of the three paths we wrote down. Nothing failed.
Nothing logged an error. They are simply held.

**Now look at one.** This is the whole job, in one cell.
""")
n.code("""print(json.dumps(held[0], indent=2, default=str))""")
n.md("""
### Find the value with your eyes

It is there. `payload.pricing.surgeFactor`.

Not the path we guessed. **A different name, at a different depth.** That is the
real shape of this problem: you cannot predict where a field will go. What you
can do is notice, on the day, that some documents match none of your known
paths, because those documents are sitting in front of you with the reason
attached.

## Who is sending it?
""")
n.code("""from collections import Counter

versions = Counter(dig(d, ('app', 'version')) for d in held)
for version, n_docs in versions.most_common():
    print(f'  app {version}   {n_docs:>7,} held')

print()
# keep holds tuples, and app_version is the sixth column of each
all_versions = Counter(row[5] for row in keep)
for version, n_docs in sorted(all_versions.items()):
    print(f'  app {version}   {n_docs:>7,} landed')""")
n.md("""
**One release. Every held document comes from 4.2.0.**

That is the sentence you take to the mobile team, and it took one notebook cell
rather than three weeks.

---

## Step 5 · The fix is one line

Add the path. Nothing else changes.
""")
n.code("""SURGE_PATHS = (
    ('payload', 'surge_multiplier'),          # 4.0.6, 4.1.2, 4.1.5
    ('payload', 'pricing', 'surgeFactor'),    # 4.2.0. Found by looking, above
    ('pricing', 'surge_multiplier'),          # what we guessed 4.2 would do. It did not
    ('surge_multiplier',),                    # the old flat shape
)

keep, held = read_batch(SURGE_PATHS)

print(f'landed : {len(keep):,}')
print(f'held   : {len(held):,}')""")
n.md("""
## And where is the value actually living, across the whole collection?

Ask the collection rather than assuming. This is a real aggregation over all
three hundred thousand documents.
""")
n.code("""report = collection.aggregate([
    {'$match': {'event_type': 'trip_offer'}},
    {'$project': {
        'at_payload': {'$cond': [{'$ifNull': ['$payload.surge_multiplier', False]}, 1, 0]},
        'at_nested':  {'$cond': [{'$ifNull': ['$payload.pricing.surgeFactor', False]}, 1, 0]},
        'at_pricing': {'$cond': [{'$ifNull': ['$pricing.surge_multiplier', False]}, 1, 0]},
        'at_flat':    {'$cond': [{'$ifNull': ['$surge_multiplier', False]}, 1, 0]},
    }},
    # a $group output name cannot contain a dot, so the readable names come later
    {'$group': {'_id': None,
                'at_payload': {'$sum': '$at_payload'},
                'at_nested':  {'$sum': '$at_nested'},
                'at_pricing': {'$sum': '$at_pricing'},
                'at_flat':    {'$sum': '$at_flat'},
                'documents':  {'$sum': 1}}},
]).next()

NAMES = {'at_payload': 'payload.surge_multiplier',
         'at_nested':  'payload.pricing.surgeFactor',
         'at_pricing': 'pricing.surge_multiplier',
         'at_flat':    'surge_multiplier'}

total = report['documents']
print(f'in {total:,} documents, the surge value lives at:\\n')
for key, label in NAMES.items():
    n_found = report[key]
    print(f'  {label:30} {n_found:>8,}   {n_found / total:>6.1%}')""")
n.md("""
**Four documents at the path we guessed.** Somebody on the mobile team started
the refactor we expected, then changed their mind. That is a report worth having
on a wall.

---

## Step 6 · Write in one batch, not one row at a time
""")
n.code("""INSERT = f\"\"\"
    INSERT INTO {SCHEMA}.bronze_driver_app
        (event_id, trip_id, driver_id, event_type, happened_at, app_version, surge)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (event_id) DO NOTHING
\"\"\"

import time
t0 = time.time()

with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    cur.executemany(INSERT, keep)        # ONE connection, ONE transaction
    c.commit()

print(f'wrote {len(keep):,} rows in {time.time() - t0:.2f}s')""")
n.md("""
### A story worth telling in class

The first version of this pipeline opened **a fresh database connection for
every held record**. Forty thousand of them took **212 seconds**. Batching made
it **0.7**. Same code, same result, three hundred times faster.

The lesson is not *"batch your writes"*. It is:

> **When something is inexplicably slow, count how many times you are opening a
> connection.**

---

## And now the packaged pipeline, over the whole collection
""")
n.code("""run('-m', 'pipelines.p3_bronze_driver_app')""")
n.code("""sql(f\"\"\"
    SELECT pipeline, status, rows_in, rows_out,
           round(extract(epoch from (ended_at - started_at))::numeric, 2) AS secs, message
    FROM {SCHEMA}.runs
    WHERE pipeline = 'p3_bronze_driver_app'
    ORDER BY started_at DESC LIMIT 3
\"\"\", 'the run log')""")
n.code("""sql(f\"\"\"
    SELECT app_version, count(*) AS events, round(avg(surge), 3) AS avg_surge
    FROM {SCHEMA}.bronze_driver_app
    GROUP BY 1 ORDER BY 2 DESC
\"\"\", 'what landed, by app version')""")
n.md("""
**That average is only trustworthy because nothing was defaulted.** Every row
behind it had a surge value we actually found.

In notebook 9 you will move the field, run this again, and watch the held pile
fill up while the row count stays exactly the same.

---

## What you learned

- A collection **has no schema**. Two documents can disagree, and nothing complains
- Bronze takes **the fields the business agreed on**, not every field that exists
- Walk nested paths with something that returns `None`, never with `[]`
- A contract for documents is **a list of every path a value has legitimately
  lived at**
- **Zero is not the same as unknown.** Holding costs a day. Defaulting costs
  a wrong number forever
- Ask the source **which shape it is actually sending**, rather than assuming
- When something is inexplicably slow, count your connections
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("05-bronze-from-an-api.ipynb")
n.md("""
# 5 · Bronze, from somebody else's API

A fourth source, and the first one **we do not control**.

| | |
|---|---|
| **reads** | PayNimbus, a payment processor, over HTTP |
| **writes** | `teach.bronze_settlements` in PostgreSQL |
| **runs** | hourly |

A database answers instantly and always. A partner's API answers **when it feels
like it**, sometimes not at all, and it is entitled to change its mind about
what a field means without telling you.

Everything different about this pipeline follows from that.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import json, os, time, urllib.request
import psycopg
from pipelines.lib.config import dsn, SCHEMA

# Read the address from the environment, never hardcode it. On a laptop this is
# localhost. Inside the Airflow container "localhost" is the container itself,
# and the partner is at http://partner-api:8088. A pipeline that only works in
# one of those two places is not finished.
API = os.environ.get('PARTNER_API', 'http://localhost:8088') + '/v1/settlements/lookup'
print(API)""")
n.md("""
---

## Step 0 · What are we even asking about?

We hold payments. PayNimbus holds settlements. **They are not the same thing.**

A payment is *"the rider was charged"*. A settlement is *"the money actually
reached our bank"*. Days can pass between the two, and some payments never
settle at all.
""")
n.code("""sql(\"\"\"
    SELECT payment_id, trip_id, amount, status, captured_at
    FROM kerb.payments
    WHERE status = 'captured'
    ORDER BY captured_at DESC
    LIMIT 5
\"\"\", 'our side: payments we captured')""")
n.md("""
## Step 1 · One HTTP call, kept boring

No retries, no backoff, no circuit breaker. Not because those are wrong, but
because they belong in a shared client, and putting them here would bury the
lesson under plumbing.

**The timeout is not optional.** Without it, a partner that hangs takes your
pipeline with it, forever, silently.
""")
n.code("""def ask(refs):
    \"\"\"Ask the partner about a list of our payment ids.\"\"\"
    request = urllib.request.Request(
        API,
        data=json.dumps({'refs': refs}).encode(),
        headers={'content-type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:   # <- the timeout
        return json.load(response).get('settlements', [])

with psycopg.connect(dsn()) as c:
    pairs = c.execute(\"\"\"SELECT payment_id, trip_id FROM kerb.payments
                        WHERE status = 'captured'
                        ORDER BY captured_at DESC LIMIT 10\"\"\").fetchall()

refs = [p for p, _ in pairs]
answer = ask(refs)

print(f'we asked about {len(refs)} payments')
print(f'they answered about {len(answer)}\\n')
print(json.dumps(answer[0], indent=2))""")
n.md("""
### Read those two numbers again

We asked about ten. They answered about fewer.

![](img/api-1-outcomes.png)

**The missing ones are not an error.** A charge still in flight is simply not in
the response. Treat absent as a failure and you page somebody every night for a
system behaving exactly as designed.

## See it for yourself
""")
n.code("""came_back = {s.get('merchant_ref') for s in answer}

for ref in refs:
    print(f\"  {ref}  {'answered' if ref in came_back else 'absent, still in flight'}\")""")
n.md("""
---

## Step 2 · Ask in batches, and pick the size on purpose

We have thousands of payments to ask about. One HTTP call each is thousands of
round trips against a partner's system. That is not a pipeline, that is an
accidental denial of service on a company you have a contract with, and somebody
will phone you about it.

![](img/api-2-batching.png)
""")
n.code("""BATCH = 250        # a named constant, so it can be argued about

with psycopg.connect(dsn()) as c:
    pairs = c.execute(\"\"\"SELECT payment_id, trip_id FROM kerb.payments
                        WHERE status = 'captured'
                        ORDER BY captured_at DESC LIMIT 2000\"\"\").fetchall()

trip_of = dict(pairs)                       # the join key we add ourselves, see step 4
refs    = [p for p, _ in pairs]

t0, answers = time.time(), []
for i in range(0, len(refs), BATCH):
    chunk = refs[i:i + BATCH]
    got = ask(chunk)
    answers.extend(got)
    print(f'  asked {len(chunk):>4}, answered {len(got):>4}')

print(f'\\n{len(refs):,} payments in {len(refs) // BATCH + 1} calls, {time.time() - t0:.1f}s')""")
n.md("""
---

## Step 3 · The contract, and why defaulting costs real money

Three answers we know how to file. Look at what the partner actually sends.
""")
n.code("""from collections import Counter

KNOWN_STATUS = {'settled', 'failed', 'in_flight'}

seen = Counter(s.get('status') for s in answers)
for status, n_seen in seen.most_common():
    known = 'known' if status in KNOWN_STATUS else 'NOT IN THE CONTRACT'
    print(f'  {str(status)!r:14} {n_seen:>6,}   {known}')""")
n.md("""
### That empty string is real, and it is in your data right now

Not `failed`. Not `settled`. **`""`**.

An empty status means the money can be neither recognised as revenue nor chased
as missing. It is in a third state that no report has a column for. And look at
what both defaults would cost:

| | |
|---|---|
| default it to `failed` | finance **writes off money that actually arrived** |
| default it to `settled` | finance **books revenue that never came** |

Holding it is the only answer that is not a lie to somebody.

---

## Step 4 · The table, and the column the partner never sends
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.bronze_settlements (
    settlement_id TEXT PRIMARY KEY,   -- the processor's id, so a re-ask is harmless
    payment_id    TEXT,               -- our id, which is what we asked them about
    trip_id       TEXT,               -- added by us. They do not send it
    rail          TEXT,               -- card, upi, wallet
    gross         NUMERIC(12,2),      -- what the rider was charged
    fee           NUMERIC(12,2),      -- what the processor kept
    net           NUMERIC(12,2),      -- what actually reached the bank
    status        TEXT,
    currency      TEXT,
    settled_at    TIMESTAMPTZ
);
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

print('table ready')""")
n.md("""
### Why `trip_id` is in that table

PayNimbus does not send it. **It knows about payments, not rides.**

Without that column this table is a set of numbers with nothing to attach them
to, and a settlement that cannot be joined back to a ride cannot answer any
question anybody actually asks. So we carry it across ourselves, from the
`trip_of` lookup we built in step 2.

---

## Step 5 · Sort every answer, and count all three outcomes
""")
n.code("""INSERT = f\"\"\"
    INSERT INTO {SCHEMA}.bronze_settlements
        (settlement_id, payment_id, trip_id, rail, gross, fee, net, status, currency, settled_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (settlement_id) DO NOTHING
\"\"\"

rows, held = [], []
for s in answers:
    status = s.get('status')
    if status not in KNOWN_STATUS:
        held.append((s.get('merchant_ref'),
                     f'status {status!r} is not one of {sorted(KNOWN_STATUS)}'))
        continue

    rows.append((
        s['settlement_id'],
        s.get('merchant_ref'),                    # their name for our payment_id
        trip_of.get(s.get('merchant_ref')),       # the join key we added
        s.get('rail'), s.get('gross'), s.get('fee'), s.get('net'),
        status, s.get('currency'), s.get('settled_at')))

with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    cur.executemany(INSERT, rows)
    c.commit()

absent = len(refs) - len(rows) - len(held)
print(f'asked   {len(refs):>6,}')
print(f'written {len(rows):>6,}   they answered and we understood')
print(f'held    {len(held):>6,}   they answered and we did not')
print(f'absent  {absent:>6,}   they did not answer. Still in flight')""")
n.md("""
**Three numbers that always add up to what you asked for.** If they ever do not,
you have a bug, and you can see it in one line.

---

## And now the packaged pipeline
""")
n.code("""run('-m', 'pipelines.p4_bronze_settlements', '--limit', '5000')""")
n.code("""sql(f\"\"\"
    SELECT pipeline, status, rows_in, rows_out,
           round(extract(epoch from (ended_at - started_at))::numeric, 2) AS secs, message
    FROM {SCHEMA}.runs
    WHERE pipeline = 'p4_bronze_settlements'
    ORDER BY started_at DESC LIMIT 3
\"\"\", 'the run log')""")
n.code("""sql(f\"\"\"
    SELECT status, rail, count(*) AS settlements,
           to_char(sum(gross), '999,999,999.99') AS gross,
           to_char(sum(fee),   '999,999,999.99') AS fee
    FROM {SCHEMA}.bronze_settlements
    GROUP BY 1, 2 ORDER BY 1, 3 DESC
\"\"\", 'what landed')""")
n.md("""
## And what is being held
""")
n.code("""sql(f\"\"\"
    SELECT reason, count(*) AS records
    FROM {SCHEMA}.quarantine
    WHERE pipeline = 'p4_bronze_settlements'
    GROUP BY 1 ORDER BY 2 DESC
\"\"\", 'held, with the reason attached')""")
n.md("""
---

## What you learned

- A partner's API is **not a database**. It answers late, partially, or not at all
- **Three outcomes, not two**: written, held, absent
- **Absent is healthy.** Money that has not moved has nothing to report
- Batch your requests, and put the batch size in **a named constant**
- **Always set a timeout.** A hanging partner should not hang you
- An unreadable status is held. Defaulting it either writes off real money or
  books revenue that never came
- If the partner cannot give you the join key, **carry it across yourself**
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("06-bronze-from-files-and-a-dimension.ipynb")
n.md("""
# 6 · Bronze, from files. And the first thing that is not a fact.

Two pipelines in one notebook, because the second one is short and the contrast
is the lesson.

| | |
|---|---|
| **p5** reads | gzipped CSV files in object storage (MinIO, which speaks S3) |
| **p5** writes | `teach.bronze_regulator` |
| **p6** reads | `kerb.zones`, a small reference table |
| **p6** writes | `teach.bronze_zones` |

The regulator does not have an API. Once a night they drop a file in a bucket
and that is the whole integration. This is far more common than anybody admits.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import csv, gzip, io, os, re
import psycopg
from minio import Minio
from pipelines.lib.config import dsn, SCHEMA

BUCKET, PREFIX = 'kerb-landing', 'regulator/'

def open_bucket():
    # MinIO speaks the S3 API, so this is the same code you would write against
    # real S3 with a different endpoint. Nothing here is toy.
    return Minio(
        os.environ['MINIO_ENDPOINT'].replace('http://', '').replace('https://', ''),
        access_key=os.environ['MINIO_ACCESS_KEY'],
        secret_key=os.environ['MINIO_SECRET_KEY'],
        secure=False)          # http, because it is running on this laptop

client = open_bucket()
print('buckets:', [b.name for b in client.list_buckets()])""")
n.md("""
---

## Step 0 · What is actually in the bucket?
""")
n.code("""objects = list(client.list_objects(BUCKET, prefix=PREFIX, recursive=True))

# sorting by name works because the date is in the path in ISO order. That is
# not luck: whoever chose dt=YYYY-MM-DD made this sort correct.
objects.sort(key=lambda o: o.object_name, reverse=True)

print(f'{len(objects)} objects under {PREFIX!r}\\n')
for o in objects[:7]:
    print(f'  {o.object_name:<58} {o.size / 1024:>8,.1f} KB')""")
n.md("""
### Two things to notice in those paths

**The date is in the path**, not in the file. `dt=2026-08-19/` is a convention
called partitioning, and it is why sorting by name sorts by date.

**Never list a bucket without a prefix.** A production landing bucket has
millions of objects, and listing all of them to find yesterday's is how you get
a very slow pipeline and a very large bill. The prefix filters on the server.

---

## Step 1 · Open one file and look at it

It is gzipped, so there are two steps before you have text.
""")
n.code("""newest = objects[0]

raw  = client.get_object(BUCKET, newest.object_name).read()
text = gzip.decompress(raw).decode('utf-8')

print(f'{newest.object_name}')
print(f'{len(raw):,} bytes compressed  ->  {len(text):,} bytes of text\\n')
print('\\n'.join(text.splitlines()[:4]))""")
n.md("""
## Step 2 · Get the date out of the path
""")
n.code("""PARTITION = re.compile(r'dt=(\\d{4}-\\d{2}-\\d{2})/')

match = PARTITION.search(newest.object_name)
partition_date = match.group(1)
print('partition date:', partition_date)

# and a file in an unexpected place, which we must not guess a date for
print('a stray file  :', PARTITION.search('regulator/oops/data.csv.gz'))""")
n.md("""
**We parse the date from the path, never from `now()`.** A file that arrives
three days late is still Tuesday's file, and everything downstream depends on
that being true.

---

## Step 3 · Everything in a CSV is a string

This is where file pipelines actually break.

![](img/files-1-types.png)
""")
n.code("""print('int(\"9\")    ->', int('9'))

try:
    int('9.0')
except ValueError as e:
    print('int(\"9.0\")  -> ValueError:', e)""")
n.md("""
The regulator writes zone ids as `9.0`, because whatever produced the file held
them as floats. So we go through `float` first.
""")
n.code("""def as_int(value):
    \"\"\"'9.0' -> 9, '9' -> 9, '' -> None. Never raises.\"\"\"
    if value is None or value == '':
        return None
    return int(float(value))       # float() first: int('9.0') raises

def as_num(value):
    if value is None or value == '':
        return None
    return float(value)

for v in ['9.0', '9', '', None, '12.75']:
    print(f'  as_int({v!r:8}) = {as_int(v)!r:8}   as_num({v!r:8}) = {as_num(v)!r}')""")
n.md("""
---

## Step 4 · Read the file into rows, holding the ones that will not convert

One malformed row in a file of a thousand must not throw away the other nine
hundred and ninety nine.
""")
n.code("""rows, held = [], []

for line_no, rec in enumerate(csv.DictReader(io.StringIO(text)), start=2):
    try:
        rows.append((
            partition_date,
            rec['trip_id'],
            as_int(rec['pu_zone_id']),
            as_int(rec['do_zone_id']),
            as_num(rec['distance_km']),
            as_int(rec['duration_s']),
            rec['status'],
            newest.object_name))          # keep the file this row came from
    except Exception as e:
        held.append((line_no, f'{type(e).__name__}: {e}'))

print(f'read   {len(rows) + len(held):,} lines')
print(f'landed {len(rows):,}')
print(f'held   {len(held):,}\\n')
for r in rows[:3]:
    print(' ', r)""")
n.md("""
### That last column is the one people forget

`source_file` is the column that saves you. When a number looks wrong in six
weeks, *"which file did this row come from"* is the first question anybody asks.

Without it the answer is a shrug. With it you open that exact object and look.

---

## Step 5 · The table, and a key that admits the same ride twice
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.bronze_regulator (
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
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

INSERT = f\"\"\"
    INSERT INTO {SCHEMA}.bronze_regulator
        (partition_date, trip_id, pu_zone_id, do_zone_id, distance_km,
         duration_s, status, source_file)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (partition_date, trip_id) DO NOTHING
\"\"\"

with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    cur.executemany(INSERT, rows)
    c.commit()

print(f'wrote {len(rows):,} rows from one file')""")
n.md("""
The primary key is **`(partition_date, trip_id)`**, not `trip_id` alone. The
regulator can send the same ride on two different days, and **both are real**.
Keying on `trip_id` alone would silently throw one away.

---

## Step 6 · No file is not the same as an empty file

![](img/files-2-missing.png)

So count **files** as well as rows.
""")
n.code("""from collections import Counter

per_day = Counter()
for o in objects:
    m = PARTITION.search(o.object_name)
    if m:
        per_day[m.group(1)] += 1

for day in sorted(per_day, reverse=True)[:7]:
    print(f'  {day}   {per_day[day]} file(s)')

missing = [d for d in sorted(per_day) if per_day[d] == 0]
print(f'\\ndays with no file at all: {len(missing)}')""")
n.md("""
---

## Now the packaged file pipeline, over the last seven days
""")
n.code("""run('-m', 'pipelines.p5_bronze_regulator', '--days', '7')""")
n.code("""sql(f\"\"\"
    SELECT partition_date, count(*) AS rides, count(DISTINCT source_file) AS files
    FROM {SCHEMA}.bronze_regulator
    GROUP BY 1 ORDER BY 1 DESC
\"\"\", 'what landed, by day and by file')""")
n.md("""
---

# The second pipeline, and the first thing that is not a fact

Everything so far has been **a fact**: something that happened, with a date.

`kerb.zones` is not that. It is a list of the sixty one zones the city is
divided into. It has no date because it is not about a moment, it is about **what
is true right now**.

![](img/files-3-dimension.png)
""")
n.code("""sql(\"\"\"
    SELECT zone_id, zone_name, borough, zone_type
    FROM kerb.zones ORDER BY zone_id LIMIT 6
\"\"\", 'kerb.zones, the dimension')

print()
print('rows in the dimension:', fetch('SELECT count(*) AS n FROM kerb.zones').n[0])""")
n.md("""
## Replace the whole thing, inside one transaction

No window. No partition. **Delete everything, insert everything, commit once.**
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.bronze_zones (
    zone_id     INT PRIMARY KEY,
    zone_name   TEXT,
    borough     TEXT,
    zone_type   TEXT
);
\"\"\"                      # note: no date column anywhere in that table

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

with psycopg.connect(dsn()) as c:
    zones = c.execute(\"\"\"SELECT zone_id, zone_name, borough, zone_type
                        FROM kerb.zones ORDER BY zone_id\"\"\").fetchall()

with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    cur.execute(f'DELETE FROM {SCHEMA}.bronze_zones')
    cur.executemany(f'INSERT INTO {SCHEMA}.bronze_zones '
                    f'(zone_id, zone_name, borough, zone_type) VALUES (%s,%s,%s,%s)', zones)
    c.commit()

print(f'replaced the whole dimension: {len(zones)} rows')""")
n.md("""
### Why deleting everything is fine here, and would be madness in bronze_trips

Sixty one rows. Replacing all of them costs nothing.

`bronze_trips` has eighty four thousand rows for one week and millions in total,
which is exactly why it is rebuilt **one window at a time**.

**The transaction still matters**, for the same reason it always does: a reader
who queries halfway through must never see an empty table.

### And what a full snapshot loses

**History.** If a zone is renamed, the old name is gone and nothing records that
it ever existed.

That is usually fine for reference data. When it is not, the technique you reach
for is called a **slowly changing dimension**. Worth having heard the phrase.
Not worth building today.
""")
n.code("""run('-m', 'pipelines.p6_bronze_zones')""")
n.code("""counts()""")
n.md("""
---

## What you learned

- Files are a real integration. Plenty of partners have nothing else
- **The date lives in the path.** Parse it from there, never from `now()`
- Always list a bucket **with a prefix**
- **A CSV has no types.** `float()` before `int()`, and wrap every conversion
- Keep **`source_file`**. It is the column that answers the six week old question
- **No file and empty file are different events.** Count files as well as rows
- A **fact** has a date and is rebuilt by window.
  A **dimension** has no date and is replaced whole
- Replacing a dimension loses history. The fix has a name: slowly changing dimension
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("07-silver-joining-it-together.ipynb")
n.md("""
# 7 · Silver, where the sources stop being separate

You now have five bronze tables. Each is a faithful copy of one source, shaped
the way that source happens to be shaped. **Nobody outside the team can use any
of them.**

Silver is one clean row per ride, with everything attached.

![](img/silver-1-shape.png)

| | |
|---|---|
| **reads** | all five bronze tables |
| **writes** | `teach.silver_rides` |
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import psycopg
from pipelines.lib.config import dsn, SCHEMA

counts()""")
n.md("""
---

## Step 0 · What each source can tell us about one ride

Pick a real ride and ask all five tables about it.
""")
n.code("""trip_id = fetch(f\"\"\"
    SELECT t.trip_id FROM {SCHEMA}.bronze_trips t
    JOIN {SCHEMA}.bronze_settlements s ON s.trip_id = t.trip_id
    WHERE t.status = 'completed' LIMIT 1
\"\"\").trip_id[0]

print('looking at', trip_id, '\\n')

with psycopg.connect(dsn()) as c:
    for table, q in [
        ('bronze_trips',       f'SELECT status, distance_km, duration_s, pickup_zone FROM {SCHEMA}.bronze_trips WHERE trip_id = %s'),
        ('bronze_events',      f'SELECT event, fare FROM {SCHEMA}.bronze_events WHERE trip_id = %s ORDER BY happened_at'),
        ('bronze_driver_app',  f'SELECT app_version, surge FROM {SCHEMA}.bronze_driver_app WHERE trip_id = %s'),
        ('bronze_settlements', f'SELECT status, gross, fee, net FROM {SCHEMA}.bronze_settlements WHERE trip_id = %s'),
    ]:
        rows = c.execute(q, (trip_id,)).fetchall()
        print(f'{table}')
        for r in rows or [('nothing',)]:
            print('   ', r)
        print()""")
n.md("""
**Four tables, four shapes, one ride.** One of them has five rows for it. One
has none. That is the problem silver exists to solve.

---

## Step 1 · The join, and the most expensive word in this job

![](img/silver-2-join.png)

Every join below is a `LEFT JOIN`, and every one is deliberate.
""")
n.code("""BUILD = f\"\"\"
SELECT
    t.trip_id,
    t.trip_date,
    t.status,
    t.driver_id,
    t.pickup_zone,
    z.zone_name                     AS pickup_zone_name,
    z.borough                       AS pickup_borough,
    t.distance_km,
    round(t.duration_s / 60.0, 1)   AS duration_min,
    e.fare,
    a.surge,
    s.net                           AS settled_net,
    (s.settlement_id IS NOT NULL)   AS is_settled
FROM {SCHEMA}.bronze_trips t
LEFT JOIN {SCHEMA}.bronze_events e
       ON e.trip_id = t.trip_id
      AND e.event = 'completed'     -- in the ON, never the WHERE. See below.
LEFT JOIN {SCHEMA}.bronze_driver_app a
       ON a.trip_id = t.trip_id
LEFT JOIN {SCHEMA}.bronze_settlements s
       ON s.trip_id = t.trip_id
      AND s.status = 'settled'
LEFT JOIN {SCHEMA}.bronze_zones z
       ON z.zone_id = t.pickup_zone
\"\"\"

print(BUILD)""")
n.md("""
### Now count what each choice actually costs

This is the cell to put on the projector.
""")
n.code("""with psycopg.connect(dsn()) as c:
    left_n = c.execute(f'SELECT count(*) FROM ({BUILD}) x').fetchone()[0]

    inner_n = c.execute(f\"\"\"
        SELECT count(*) FROM {SCHEMA}.bronze_trips t
        JOIN {SCHEMA}.bronze_events e
          ON e.trip_id = t.trip_id AND e.event = 'completed'
        JOIN {SCHEMA}.bronze_driver_app a  ON a.trip_id = t.trip_id
        JOIN {SCHEMA}.bronze_settlements s ON s.trip_id = t.trip_id AND s.status = 'settled'
        JOIN {SCHEMA}.bronze_zones z       ON z.zone_id = t.pickup_zone
    \"\"\").fetchone()[0]

print(f'LEFT  JOIN : {left_n:>8,} rides')
print(f'INNER JOIN : {inner_n:>8,} rides')
print(f'\\ndifference : {left_n - inner_n:>8,} rides, {(left_n - inner_n) / left_n:.1%}, gone')""")
n.md("""
### Where exactly did they go?

Four separate reasons, and every one of them is a real ride.
""")
n.code("""qs = {
 'no completed event (cancelled rides)':
   f\"\"\"SELECT count(*) FROM {SCHEMA}.bronze_trips t WHERE NOT EXISTS (
        SELECT 1 FROM {SCHEMA}.bronze_events e
        WHERE e.trip_id = t.trip_id AND e.event = 'completed')\"\"\",
 'no driver app record':
   f\"\"\"SELECT count(*) FROM {SCHEMA}.bronze_trips t WHERE NOT EXISTS (
        SELECT 1 FROM {SCHEMA}.bronze_driver_app a WHERE a.trip_id = t.trip_id)\"\"\",
 'not settled yet (settlement is T+2)':
   f\"\"\"SELECT count(*) FROM {SCHEMA}.bronze_trips t WHERE NOT EXISTS (
        SELECT 1 FROM {SCHEMA}.bronze_settlements s
        WHERE s.trip_id = t.trip_id AND s.status = 'settled')\"\"\",
 'never resolved to a zone':
   f\"\"\"SELECT count(*) FROM {SCHEMA}.bronze_trips t WHERE NOT EXISTS (
        SELECT 1 FROM {SCHEMA}.bronze_zones z WHERE z.zone_id = t.pickup_zone)\"\"\",
}

with psycopg.connect(dsn()) as c:
    for label, q in qs.items():
        print(f'  {c.execute(q).fetchone()[0]:>7,}   {label}')""")
n.md("""
### Read that list again

A cancelled ride **is a ride**. A ride the app did not report **happened**.
Money that has not settled yet **will**. And a ride with no zone id **still
carried somebody somewhere**.

An `INNER JOIN` deletes all four, and:

> **No error. No failed run. No log line. The number is just smaller.**

Somebody changes a join to make a query faster, the ride count drops four
percent, and it takes three weeks to notice and a day to find.

**A wrong answer that runs successfully is worse than a crash, because a crash
tells you.**

---

## Step 2 · ON, or WHERE. Not a style choice.

![](img/silver-3-where.png)

Same condition, one word moved, and the LEFT JOIN quietly becomes an INNER one.
Prove it.
""")
n.code("""with psycopg.connect(dsn()) as c:
    on_clause = c.execute(f\"\"\"
        SELECT count(*) FROM {SCHEMA}.bronze_trips t
        LEFT JOIN {SCHEMA}.bronze_events e
               ON e.trip_id = t.trip_id AND e.event = 'completed'
    \"\"\").fetchone()[0]

    where_clause = c.execute(f\"\"\"
        SELECT count(*) FROM {SCHEMA}.bronze_trips t
        LEFT JOIN {SCHEMA}.bronze_events e
               ON e.trip_id = t.trip_id
        WHERE e.event = 'completed'
    \"\"\").fetchone()[0]

print(f\"condition in ON    : {on_clause:>8,}\")
print(f\"condition in WHERE : {where_clause:>8,}\")
print(f\"\\n{on_clause - where_clause:,} rides lost to moving one word\")""")
n.md("""
**The WHERE runs after the join.** The LEFT JOIN carefully kept the rides with
no completed event and gave them `NULL`, and then the WHERE threw every one of
those NULL rows away.

Same rows lost as an INNER JOIN, with a `LEFT JOIN` sitting in the query looking
reassuring.

---

## Step 3 · The table silver writes into
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.silver_rides (
    trip_id      TEXT PRIMARY KEY,
    trip_date    DATE NOT NULL,
    status       TEXT,
    driver_id    TEXT,
    pickup_zone  INT,
    pickup_zone_name TEXT,        -- from the zones dimension
    pickup_borough   TEXT,        -- an id nobody can read is not an answer
    distance_km  NUMERIC(8,2),
    duration_min NUMERIC(8,1),    -- converted from seconds
    fare         NUMERIC(10,2),   -- from the event stream
    surge        NUMERIC(6,2),    -- from the driver app
    settled_net  NUMERIC(12,2),   -- from the payment processor
    is_settled   BOOLEAN          -- a plain yes/no, so nobody downstream guesses
);
CREATE INDEX IF NOT EXISTS ix_silver_rides_date ON {SCHEMA}.silver_rides (trip_date);
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

print('table ready')""")
n.md("""
### Three things silver did that bronze was forbidden to do

| | |
|---|---|
| `duration_s` became `duration_min` | **a unit conversion.** Bronze was not allowed one |
| `fare`, `surge`, `settled_net` | **columns that existed in no single source.** The whole point |
| no `rider_id` | **dropped.** Nothing downstream uses it, and carrying a personal identifier you do not need is a liability, not an asset |

---

## Step 4 · Build it, in one transaction
""")
n.code("""with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    rows_in = cur.execute(f'SELECT count(*) FROM {SCHEMA}.bronze_trips').fetchone()[0]

    # Both statements inside one transaction. A crash between them rolls back
    # the delete too, so a reader never sees an empty table.
    cur.execute(f'DELETE FROM {SCHEMA}.silver_rides')
    cur.execute(f'INSERT INTO {SCHEMA}.silver_rides {BUILD}')
    rows_out = cur.rowcount
    c.commit()

print(f'read {rows_in:,} rides, wrote {rows_out:,}')""")
n.md("""
### Why a full rebuild is defensible here, and would not be at scale

Bronze rebuilt **a window** because the source table is enormous. Here we delete
everything and rebuild, which would be indefensible at real scale.

It is fine here because `silver_rides` holds eighty thousand rows and the
rebuild takes under a second. Being clever about incremental windows would cost
more in explanation than it saves in runtime.

When this table reaches tens of millions it grows a window, exactly like bronze
did. The honest rule is not *"always full rebuild"*, it is:

> **Match the technique to the size, and say out loud which one you chose.**

---

## Step 5 · Look at what you built
""")
n.code("""sql(f\"\"\"
    SELECT trip_id, trip_date, status, pickup_zone_name, pickup_borough,
           distance_km, duration_min, fare, surge, settled_net, is_settled
    FROM {SCHEMA}.silver_rides
    WHERE fare IS NOT NULL
    ORDER BY trip_date DESC
    LIMIT 8
\"\"\", 'silver_rides, one row per ride')""")
n.md("""
**A person who has never heard of Kafka can read that table.** That is the test
silver has to pass.

## How complete is it?

Silver keeps the ride even when a source had nothing. So say plainly how often
each column is actually filled.
""")
n.code("""sql(f\"\"\"
    SELECT count(*)                                                   AS rides,
           round(100.0 * count(fare)        / count(*), 1) AS pct_with_fare,
           round(100.0 * count(surge)       / count(*), 1) AS pct_with_surge,
           round(100.0 * count(settled_net) / count(*), 1) AS pct_settled,
           round(100.0 * count(pickup_zone_name) / count(*), 1) AS pct_with_zone
    FROM {SCHEMA}.silver_rides
\"\"\", 'how filled in is each column')""")
n.md("""
**Those gaps are the truth, not a bug.** Every one of them has a reason you
counted a moment ago. A table that reported 100% everywhere would be lying.

---

## And the packaged pipeline
""")
n.code("""run('-m', 'pipelines.p7_silver_rides')""")
n.code("""sql(f\"\"\"
    SELECT pipeline, status, rows_in, rows_out,
           round(extract(epoch from (ended_at - started_at))::numeric, 2) AS secs, message
    FROM {SCHEMA}.runs WHERE pipeline = 'p7_silver_rides'
    ORDER BY started_at DESC LIMIT 3
\"\"\", 'the run log')""")
n.md("""
---

## What you learned

- Silver is **one clean row per thing**, and the first table a stranger can read
- Silver **may** convert units, add derived columns, and drop what nothing needs
- **`LEFT` versus `INNER` is silent data loss.** Count it before you choose
- A cancelled ride, an unreported ride, an unsettled ride and a zoneless ride
  are all still rides
- Put the condition in the **`ON`**, never the `WHERE`, or your LEFT JOIN is a
  lie
- Full rebuild or window is **a size decision**, and you should say which you made
- **Report your gaps.** 100% everywhere means somebody is not looking
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("08-gold-and-the-signal-board.ipynb")
n.md("""
# 8 · Gold, and the thing that notices when a number stops making sense

Two ideas in one notebook.

**Gold** is the answer, aggregated to the grain somebody actually asks for.
**The signal board** is what tells you when that answer stops being trustworthy.

| | |
|---|---|
| **reads** | `teach.silver_rides` |
| **writes** | `teach.gold_daily`, one row per day |
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import psycopg
from pipelines.lib.config import dsn, SCHEMA

print('silver rides:', f\"{fetch(f'SELECT count(*) AS n FROM {SCHEMA}.silver_rides').n[0]:,}\")""")
n.md("""
---

## Step 1 · The test for a gold column

> **If you cannot say the column name out loud in a sentence to a finance
> manager, it does not belong in gold.**

`avg_duration_min` passes. `duration_s` does not. `rides` passes. `trip_id`
does not, because a gold table is not about one ride.
""")
n.code("""DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.gold_daily (
    trip_date        DATE PRIMARY KEY,
    rides            BIGINT,
    completed        BIGINT,
    cancelled        BIGINT,
    avg_distance_km  NUMERIC(8,2),
    avg_duration_min NUMERIC(8,1),
    avg_surge        NUMERIC(6,3),
    revenue          NUMERIC(14,2),
    settled_rides    BIGINT,
    unsettled_rides  BIGINT
);
\"\"\"

with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(DDL)

print('table ready')""")
n.md("""
---

## Step 2 · Aggregate with FILTER, not with three queries

`count(*) FILTER (WHERE ...)` counts only the rows matching a condition, **in
the same pass as everything else**. The alternative is three queries joined
together, which is slower and much harder to read.
""")
n.code("""BUILD = f\"\"\"
SELECT
    trip_date,
    count(*)                                          AS rides,
    count(*) FILTER (WHERE status = 'completed')      AS completed,
    count(*) FILTER (WHERE status LIKE 'cancelled%%') AS cancelled,
    round(avg(distance_km), 2)                        AS avg_distance_km,
    round(avg(duration_min), 1)                       AS avg_duration_min,
    round(avg(surge), 3)                              AS avg_surge,
    round(coalesce(sum(fare), 0), 2)                  AS revenue,
    count(*) FILTER (WHERE is_settled)                AS settled_rides,
    count(*) FILTER (WHERE NOT is_settled)            AS unsettled_rides
FROM {SCHEMA}.silver_rides
GROUP BY trip_date
\"\"\"

with psycopg.connect(dsn(), autocommit=False) as c, c.cursor() as cur:
    rows_in = cur.execute(f'SELECT count(*) FROM {SCHEMA}.silver_rides').fetchone()[0]
    cur.execute(f'DELETE FROM {SCHEMA}.gold_daily')
    cur.execute(f'INSERT INTO {SCHEMA}.gold_daily {BUILD}')
    rows_out = cur.rowcount
    c.commit()

print(f'{rows_in:,} rides  ->  {rows_out} days')""")
n.code("""sql(f\"\"\"
    SELECT trip_date, rides, completed, cancelled, avg_distance_km,
           avg_duration_min, avg_surge, revenue, settled_rides, unsettled_rides
    FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC
\"\"\", 'gold_daily, the whole table')""")
n.md("""
### Two details in that query worth a minute

**`avg()` ignores NULLs by itself.** `avg_surge` is therefore the average across
rides that *have* a surge value, not across all rides with the missing ones
counted as zero.

That is what you want, and it has a consequence: when a field goes missing
upstream, this number does **not** drag downwards. The row count behind it drops
instead, which is a completely different signal. You will watch exactly that
happen in notebook 9.

**`coalesce(sum(fare), 0)`** because `sum()` of nothing is `NULL`, not zero, and
a day with no fares should report `0` revenue rather than an empty cell.

---

## Step 3 · Rebuild it, for the same reason as silver

Thirty rows. A full rebuild takes milliseconds. Anything cleverer would be
complexity nobody is paying for.
""")
n.code("""run('-m', 'pipelines.p8_gold_daily')""")
n.md("""
---

# Now the second half. Who tells you when this is wrong?

You have eight pipelines. They all say `ok`. **That is not the same as the
numbers being right.**

Three completely different things can check your work, and people collapse them
into one word, quality, and then argue past each other.

![](img/gold-1-checkpoints.png)

| | the contract | the tests | the signal board |
|---|---|---|---|
| **where** | inside the pipeline | inside the transaction | outside everything |
| **when** | per record, on the way in | after the write, before the commit | on a clock, after the run |
| **can it block?** | **yes** | **yes**, it rolls back | **no. Nothing. Ever.** |

> **A check that can block a write is a contract. A check that cannot is a
> signal.**

You have already built the first one, eight times over. This is the third.

---

## Step 4 · A signal is four things

![](img/gold-2-signal.png)

Build one, here, in a cell.
""")
n.code("""from dataclasses import dataclass

@dataclass
class Signal:
    name: str            # so a person can talk about it
    owner: str           # who gets told when it moves
    sql: str             # returns exactly one number
    baseline: float      # what that number normally is
    tolerance: float = 0.0
    means: str = ''

held = Signal(
    name='records_held',
    owner='data-platform',
    sql=f'SELECT count(*) FROM {SCHEMA}.quarantine',
    baseline=0,
    means='Records a contract refused. Not lost, not wrong, just not published.')

with psycopg.connect(dsn()) as c:
    value = float(c.execute(held.sql).fetchone()[0])

gap = abs(value - held.baseline)
breached = gap > max(held.tolerance, 0.0001)

print(f'{held.name:16} = {value:,.0f}   baseline {held.baseline}   '
      f'{\"BREACH\" if breached else \"ok\"}')
if breached:
    print(f'  -> this one is {held.owner}\\'s. {held.means}')""")
n.md("""
**That is the whole idea.** There is no model here and no intelligence.

Deciding that 34% is far from 0.09% is **arithmetic**, and pretending otherwise
is how people end up buying something they could have written in an afternoon.

### The field that actually matters is `owner`

A breach with no name attached is a number on a screen that everybody assumes
somebody else is looking at.

---

## Step 5 · Two kinds of baseline

![](img/gold-3-baselines.png)

Some numbers have **a history**. Some have **a rule**.
""")
n.code("""import statistics

# a baseline computed from history: what have the other days looked like?
with psycopg.connect(dsn()) as c:
    today   = float(c.execute(
        f'SELECT rides FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1').fetchone()[0])
    history = [float(r[0]) for r in c.execute(
        f'SELECT rides FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1')]

baseline = statistics.mean(history)
spread   = max(statistics.pstdev(history), 0.01)
z        = (today - baseline) / spread

print(f'most recent day : {today:>10,.0f} rides')
print(f'the days before : {baseline:>10,.0f} on average, spread {spread:,.0f}')
print(f'z score         : {z:>10.2f}   (how many spreads away from normal)')
print()
print('BREACH' if abs(z) > 4 else 'ok, within normal variation')""")
n.md("""
### Why 4 and not 2

A z score of 2 fires on a quiet Tuesday. A z score of 4 fires when something
genuinely broke.

Set it too tight and the board cries wolf, people stop reading it, and you have
spent effort building something that made you *less* safe than having nothing.

### And one signal needs both kinds

`events_per_ride` has a **fixed** baseline of `4.7` with a **tolerance** of
`1.0`. A completed ride emits five events and a cancelled one emits three, so
the true average sits a little under five, and that is correct, not a fault.

Set that baseline to exactly `5` and the board breaches on day one, for a
perfectly healthy system. That happened while building this course.

---

## Step 6 · The whole board

Six signals. Between them they answer the four questions that go wrong: **did it
arrive, is it the right amount, is it the right shape, and does it still add
up.**
""")
n.code("""from signals.board import SIGNALS

for s in SIGNALS:
    kind = ('fixed at %g' % s.fixed_baseline) if s.fixed_baseline is not None else 'from history'
    print(f'  {s.name:22} {s.owner:16} {kind}')
    print(f'  {\"\":22} watches {s.watches}')
    print()""")
n.code("""run('-m', 'signals.board')""")
n.md("""
### Read the one that is not about data at all

`pipelines_failing` looks at `teach.runs`, not at any table of records. It asks
**whether the work happened.**

That matters because **a pipeline that never ran leaves perfectly valid data
behind.** Every row is correct. Every row is old. No check that looks only at
values will ever notice.

---

## Step 7 · Where the board runs, and where it must not

**Beside the warehouse, on a clock, after the pipelines have finished.**

Never inside a pipeline. A check that can block a write is a different thing
with a different name, and you already built that one: it is the contract.

There is a dashboard for the same six signals:

```bash
python cli.py dashboard        #  http://localhost:8099
```

Put it on the second screen and leave it there.

---

## What you learned

- Gold is **the answer at the grain somebody asks for**. If you cannot say the
  column name to a finance manager, it does not belong
- `FILTER (WHERE ...)` beats three joined queries
- `avg()` ignores nulls, so a missing field moves **the count**, not the average
- **Three checkpoints**: contract, tests, signal board. Only the first two can block
- A signal is **a name, a query, a baseline, and an owner**. The owner is the point
- **Two kinds of baseline**: computed from history, or decided by a person
- A threshold that is too tight makes you **less** safe, because people stop reading
- `pipelines_failing` is the signal that catches the failure no data check can see
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("09-break-it-and-put-it-back.ipynb")
n.md("""
# 9 · Break it, watch nothing fail, and find it anyway

Everything works. That is the worst moment to stop, because you have not yet
seen **the failure this whole course is built around**.

> A field moves upstream. The pipeline does not fail. No run errors. Every row
> count stays exactly the same. And a number quietly stops being true.

You are going to cause it, on purpose, and then find it.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import psycopg
from pipelines.lib.config import dsn, SCHEMA""")
n.md("""
---

## Step 1 · Write down what "healthy" looks like, before you break anything

You cannot notice a change you never measured. Take the reading first.
""")
n.code("""def reading():
    with psycopg.connect(dsn()) as c:
        return dict(zip(
            ['driver_app_rows', 'with_surge', 'avg_surge', 'gold_days', 'gold_avg_surge'],
            c.execute(f\"\"\"
                SELECT (SELECT count(*)  FROM {SCHEMA}.bronze_driver_app),
                       (SELECT count(surge) FROM {SCHEMA}.bronze_driver_app),
                       (SELECT round(avg(surge), 3) FROM {SCHEMA}.bronze_driver_app),
                       (SELECT count(*) FROM {SCHEMA}.gold_daily),
                       (SELECT round(avg(avg_surge), 3) FROM {SCHEMA}.gold_daily)
            \"\"\").fetchone()))

before = reading()
for k, v in before.items():
    print(f'  {k:18} {v}')""")
n.code("""run('-m', 'signals.board')""")
n.md("""
### Five green, one red, and the red one is real

`records_held` is above zero because the payment processor genuinely sends
settlements with an empty status, and the contract genuinely refuses them. That
is an open issue somebody owns, not a bug in the board.

**Write the number down.** The point of the next few cells is not that a light
goes red, it is that **a second, different light** goes red, for a reason
nothing else in the estate would have told you.

---

## Step 2 · Now break it

`break_it.py` simulates one thing: the mobile team ships a release that moves
the surge field, so our reader finds nothing at any path it knows.

It does **not** delete rows. It does **not** corrupt anything. It does exactly
what a real rename does: the value stops arriving.
""")
n.code("""run('break_it.py')""")
n.md("""
## Look at what just happened. Or rather, at what did not.
""")
n.code("""after = reading()

print(f'{\"\":18} {\"before\":>12} {\"after\":>12}')
for k in before:
    b, a = before[k], after[k]
    flag = '' if b == a else '   <- moved'
    print(f'  {k:18} {str(b):>12} {str(a):>12}{flag}')""")
n.md("""
### Read the first row again

**`driver_app_rows` did not change.**

Every row count check you could write is still green. Nothing failed. No
pipeline errored. There is no log line anywhere describing this.

The only thing that changed is that a column stopped being filled in.
""")
n.code("""run('-m', 'pipelines.p7_silver_rides')""")
n.code("""run('-m', 'pipelines.p8_gold_daily')""")
n.md("""
Both pipelines say **ok**. Both wrote the same number of rows they always write.

---

## Step 3 · Now ask the board
""")
n.code("""run('-m', 'signals.board')""")
n.md("""
### There it is

**Two breaches now, not one.** `surge_missing_pct` moved from 0 to fifteen
percent, and the line under the board says **whose it is**: pricing.

That is the entire value of the exercise. Not that a check went red, but that:

| | |
|---|---|
| **what moved** | one named number, with its normal value beside it |
| **whose it is** | pricing, not "the data team" |
| **what to say** | *"the share of driver app records with no surge value went from 0% to 30% on Tuesday"* |

Compare that to the alternative, which is somebody in finance noticing a
quarterly number looks odd, six weeks later.

## And what did it cost downstream?
""")
n.code("""sql(f\"\"\"
    SELECT trip_date, rides, avg_surge, revenue
    FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC
\"\"\", 'gold_daily, after the break')""")
n.md("""
### Notice which number moved and which did not

**`rides` is unchanged.** **`revenue` is unchanged.** Only `avg_surge` moved,
and it moved because it is now averaging **fewer** rows, not wrong ones.

That is `avg()` ignoring nulls, which you met in notebook 8. A missing field
does not drag an average down. It shrinks the population behind it silently.

**Which is worse**, because a number that moved is visible and a number computed
from half the data is not.

---

## Step 4 · Put it back
""")
n.code("""run('break_it.py', '--fix')""")
n.code("""run('-m', 'pipelines.p7_silver_rides')
run('-m', 'pipelines.p8_gold_daily')""")
n.code("""run('-m', 'signals.board')""")
n.md("""
**Back to one breach: the one that was already there when you started.**

`surge_missing_pct` is green again and the numbers match the reading you took at
the start. That is what "fixed" looks like: not an empty board, but a board that
says exactly what it said before, and nothing more.

---

## Step 5 · The reset that always works

Every demo in this course is repeatable, because there is one command that puts
the warehouse back to nothing.
""")
n.code("""sql(f\"\"\"
    SELECT reason, count(*) AS records
    FROM {SCHEMA}.quarantine GROUP BY 1 ORDER BY 2 DESC LIMIT 5
\"\"\", 'what is being held right now, and why')""")
n.md("""
### What reset actually does, and what it deliberately does not

| | |
|---|---|
| drops the `teach` schema | every table you built, gone |
| deletes the Kafka consumer groups | **the bit people forget** |
| touches the source systems | **never.** `kerb.trips`, Mongo, MinIO and the partner API are untouched |

The Kafka part is worth saying out loud. **Our position in the stream lives on
the broker, not in our database.** Drop the tables without deleting the consumer
group and the pipeline wakes up believing it has already read everything, reads
zero messages, reports success, and leaves you with an empty table and no error.

That bug cost an hour while this course was being built.

```bash
python cli.py reset          # then: python cli.py run all
```

## Prove it is repeatable

Run the reset, then rebuild everything from cold. It takes a few seconds.
""")
n.code("""run('reset.py')""")
n.code("""counts()""")
n.code("""run('cli.py', 'run', 'all')""")
n.code("""counts()""")
n.code("""run('-m', 'signals.board')""")
n.md("""
**From an empty schema to a working board in one command**, back to the same
single honest breach it started with.

That is the property that makes this safe to teach with. Nothing you do in this
notebook can put the estate in a state you cannot get out of.

---

## What you learned

- **Take the reading before you break anything.** You cannot notice a change you
  never measured
- The failure that matters most is the one where **nothing fails**
- A row count check stays green through a field rename. Every time
- `avg()` ignoring nulls means a missing field **shrinks the population**, it
  does not move the average. That is harder to see, not easier
- A signal is only useful if it names **an owner** and **a normal value**
- Your position in a stream lives **on the broker**. A reset that forgets that
  is not a reset
- **Always have a way back to zero.** A demo you cannot repeat is a demo you
  will not run
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("11-mongodb-live.ipynb")
n.md("""
# 11 · MongoDB, live

Short notebook, and every cell writes to the **real** collection the pipeline
reads.

You insert a document. You run the pipeline. It lands. Then you insert one where
a field has **moved**, and you watch the contract deal with it in front of the
room.

In notebook 4 you found a moved field in data somebody else generated. Here you
are the mobile team.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import show, sql, fetch, run, counts

import datetime as dt, json, random
import psycopg
from pymongo import MongoClient
from pipelines.lib.config import dsn, SCHEMA, MONGO_URI

collection = MongoClient(MONGO_URI).kerb_app.driver_app_events
print(f'{collection.estimated_document_count():,} documents in the collection')""")
n.md("""
---

## Step 1 · Send one document, the way the app sends it today

Release 4.1.5. Surge at `payload.surge_multiplier`.
""")
n.code("""def send(surge_path, version, trip_id=None):
    \"\"\"Insert one driver app document, putting surge wherever you say.\"\"\"
    trip_id = trip_id or f'TRP-NB11-{random.randint(10000, 99999)}'
    doc = {
        'event_id':   f'EV-NB11-{random.randint(100000, 999999)}',
        'trip_id':    trip_id,
        'driver_id':  f'DRV{random.randint(1, 2800):06d}',
        'event_type': 'trip_offer',
        'ts':         dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None),
        'app':        {'version': version, 'platform': 'ios', 'build': 415},
        'payload':    {'eta_s': 240, 'distance_km': 3.1},
    }

    # walk the path, creating each level, and put the value at the end
    cur, surge = doc, round(random.uniform(1.0, 2.4), 2)
    for key in surge_path[:-1]:
        cur = cur.setdefault(key, {})
    cur[surge_path[-1]] = surge

    collection.insert_one(dict(doc))
    print(f\"sent {doc['event_id']}  app {version}  surge {surge} at {'.'.join(surge_path)}\")
    return doc['event_id'], trip_id

good_id, good_trip = send(('payload', 'surge_multiplier'), '4.1.5')""")
n.md("""
## Run the pipeline and watch it land
""")
n.code("""run('-m', 'pipelines.p3_bronze_driver_app')""")
n.code("""sql(f\"\"\"
    SELECT event_id, trip_id, app_version, surge, happened_at
    FROM {SCHEMA}.bronze_driver_app
    WHERE event_id LIKE 'EV-NB11-%'
    ORDER BY happened_at DESC LIMIT 5
\"\"\", 'documents you sent, in the warehouse')""")
n.md("""
---

## Step 2 · Now be the mobile team

Ship release 5.0, and move the field somewhere nobody agreed on.

The pipeline knows four paths:

```
payload.surge_multiplier
payload.pricing.surgeFactor
pricing.surge_multiplier
surge_multiplier
```

Put it at a fifth.
""")
n.code("""moved_id, moved_trip = send(('payload', 'fare', 'multiplier'), '5.0.0')""")
n.code("""run('-m', 'pipelines.p3_bronze_driver_app')""")
n.md("""
### Read that run line carefully

`rows_in` is larger than `rows_out`. **Nothing failed.** The pipeline read the
document perfectly well and refused to publish it, because it could not find a
value it was asked to carry.

## Where did it go?
""")
n.code("""landed = fetch(f\"\"\"
    SELECT count(*) AS n FROM {SCHEMA}.bronze_driver_app WHERE event_id = '{moved_id}'
\"\"\").n[0]

print(f'rows in the warehouse for {moved_id}: {landed}\\n')

sql(f\"\"\"
    SELECT reason, payload
    FROM {SCHEMA}.quarantine
    WHERE pipeline = 'p3_bronze_driver_app'
      AND payload::text LIKE '%{moved_trip}%'
    LIMIT 1
\"\"\", 'held, with the reason and the original document')""")
n.md("""
**Zero rows landed. One record held, with the whole document attached.**

That is the difference between *"surge looks low this week"* and *"here is the
document, here is the release that sent it, here is the path it used"*.

---

## Step 3 · The fix is one line

The contract is a tuple. Add the path to it.

Here it is done live, in this kernel, so you can watch the held record land
without leaving the notebook.
""")
n.code("""import pipelines.p3_bronze_driver_app as p3

print('before:')
for path in p3.SURGE_PATHS:
    print('   ', '.'.join(path))

p3.SURGE_PATHS = p3.SURGE_PATHS + (('payload', 'fare', 'multiplier'),)   # release 5.0

print('\\nafter:')
for path in p3.SURGE_PATHS:
    print('   ', '.'.join(path))""")
n.code("""p3.run()""")
n.md("""
**No migration. No backfill script. No redeploy.** One tuple grew by one line
and the record that could not be published now can be.

To make it permanent, add the same line to `SURGE_PATHS` in
`pipelines/p3_bronze_driver_app.py`:

```python
SURGE_PATHS = (
    ("payload", "surge_multiplier"),
    ("payload", "pricing", "surgeFactor"),
    ("payload", "fare", "multiplier"),        # <- release 5.0
    ("pricing", "surge_multiplier"),
    ("surge_multiplier",),
)
```
""")
n.code("""sql(f\"\"\"
    SELECT event_id, app_version, surge
    FROM {SCHEMA}.bronze_driver_app
    WHERE event_id IN ('{good_id}', '{moved_id}')
\"\"\", 'both documents, once the contract knows the new path')""")
n.md("""
---

## Step 4 · What the shape of the collection looks like now
""")
n.code("""report = collection.aggregate([
    {'$match': {'event_type': 'trip_offer'}},
    {'$project': {
        'at_payload': {'$cond': [{'$ifNull': ['$payload.surge_multiplier', False]}, 1, 0]},
        'at_nested':  {'$cond': [{'$ifNull': ['$payload.pricing.surgeFactor', False]}, 1, 0]},
        'at_fare':    {'$cond': [{'$ifNull': ['$payload.fare.multiplier', False]}, 1, 0]},
        'at_pricing': {'$cond': [{'$ifNull': ['$pricing.surge_multiplier', False]}, 1, 0]},
    }},
    {'$group': {'_id': None,
                'at_payload': {'$sum': '$at_payload'},
                'at_nested':  {'$sum': '$at_nested'},
                'at_fare':    {'$sum': '$at_fare'},
                'at_pricing': {'$sum': '$at_pricing'},
                'documents':  {'$sum': 1}}},
]).next()

NAMES = {'at_payload': 'payload.surge_multiplier',
         'at_nested':  'payload.pricing.surgeFactor',
         'at_fare':    'payload.fare.multiplier',
         'at_pricing': 'pricing.surge_multiplier'}

total = report['documents']
print(f'{total:,} trip_offer documents, and the surge value lives at:\\n')
for key, label in NAMES.items():
    n_found = report[key]
    print(f'  {label:30} {n_found:>8,}   {n_found / total:>7.3%}')""")
n.md("""
**Four different shapes in one collection, all of them real, none of them
wrong.** That is what a schemaless store looks like after two years.

The contract is the only thing standing between that and a column full of nulls
nobody can explain.

---

## Tidy up

The documents you sent stay in Mongo, which is honest: you really did send them.
Remove them if you want a clean collection for the next class.
""")
n.code("""deleted = collection.delete_many({'event_id': {'$regex': '^EV-NB11-'}}).deleted_count
print(f'removed {deleted} documents you sent')

with psycopg.connect(dsn(), autocommit=True) as c:
    n = c.execute(f\"DELETE FROM {SCHEMA}.bronze_driver_app WHERE event_id LIKE 'EV-NB11-%'\").rowcount
print(f'removed {n} rows from the warehouse')""")
n.md("""
---

## What you learned

- A document store lets **every release invent its own shape**, and nothing complains
- A moved field is **not an error**. The pipeline reads the document fine
- The contract turns an invisible problem into **a held record with the document
  attached**
- Fixing it is **one line**, with no migration and no backfill
- Ask the collection what shapes it holds. The answer is rarely one
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("12-airflow-scheduling.ipynb")
n.md("""
# 12 · Scheduling, with Airflow

Every notebook so far ended with **you** typing a command. In production nobody
is awake to type it.

This notebook is one straight line:

1. write a tiny pipeline, and run it yourself
2. write a DAG that says when to run it
3. put the DAG where Airflow can see it
4. watch Airflow run it once
5. turn the schedule on, and watch it run **by itself**
6. turn it off again

**One pipeline file. One DAG file. Nothing else.**

## What Airflow is, in one sentence

> **Airflow is a program whose only job is to start other programs, in the right
> order, at the right time, and to remember what happened.**

It does not move data. It never touches a row. Every pipeline in this course
would run perfectly well if you typed the commands by hand at the right moments,
forever, without sleeping.

**Airflow is the thing that does the typing.**

## Why not just a for loop?

`cli.py` already runs the eight pipelines in order, and on a laptop that is
genuinely enough. It stops being enough the moment you ask any of these.

![](img/airflow-1-loop.png)

| The question | What a for loop answers |
|---|---|
| The third one failed at 3am. Did the rest still run? | *no, I stopped* |
| I want to retry just that one. How? | *rerun everything* |
| Six of these are independent. Why are they queued? | *because I am a loop* |
| Yesterday's file arrived late. Can I rerun just yesterday? | *no* |
| Who was told, and about which task? | *nobody, and nothing* |

Airflow answers all five. **That is the entire reason it exists.**
""")
n.md("""
---

## Before anything: where the files live

This is the part that confuses people, so deal with it first.

![](img/airflow-4-where.png)

**Two files, both in this repo, doing different jobs.** The pipeline is the
work. The DAG says when. Both folders are mounted into the Airflow container,
which is why there is nothing to copy anywhere.

Airflow is already running in Docker, so one helper lets every cell below be a
single line.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import sql, fetch, run           # the same helpers as every other notebook

import subprocess, json, time, pathlib

PROJECT = pathlib.Path('..').resolve()        # this repo
DAGS    = PROJECT / 'airflow' / 'dags'       # the folder Airflow watches

CONTAINER = 'nightshift-airflow'

def airflow(*args, quiet=False):
    \"\"\"Run an airflow command inside the container. The same CLI you would type
    after ssh-ing onto a scheduler box. Nothing here is special to notebooks.\"\"\"
    r = subprocess.run(['docker', 'exec', CONTAINER, 'airflow', *args],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).rstrip()
    if not quiet:
        print(out)
    return out

print('project  ', PROJECT)
print('dags     ', DAGS)
print('airflow  ', airflow('version', quiet=True))""")
n.md("""
---

# Step 1 · The work

A deliberately tiny pipeline. It writes one row saying *"I ran, at this time,
for this scheduled slot"*. That is enough to prove a schedule is live, and small
enough to read in one screen.
""")
n.code("""HEARTBEAT = '''
from __future__ import annotations
import os, sys
import psycopg
from .lib.config import SCHEMA, dsn

DDL = f\"\"\"
CREATE TABLE IF NOT EXISTS {SCHEMA}.heartbeat (
    ran_at  TIMESTAMPTZ DEFAULT now(),
    slot    TEXT,            -- which scheduled minute this run is FOR
    run_id  TEXT             -- which Airflow run wrote it
);
\"\"\"

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
'''

(PROJECT / 'pipelines' / 'heartbeat.py').write_text(HEARTBEAT.lstrip())
print('wrote', PROJECT / 'pipelines' / 'heartbeat.py')""")
n.md("""
## Run it yourself, before Airflow is involved at all

This is the command a human types. Remember it: the DAG is going to type exactly
this and nothing else.
""")
n.code("""run('-m', 'pipelines.heartbeat')""")
n.code("""from pipelines.lib.config import SCHEMA

sql(f\"\"\"
    SELECT to_char(ran_at, 'HH24:MI:SS') AS ran_at, slot, run_id
    FROM {SCHEMA}.heartbeat ORDER BY ran_at DESC LIMIT 5
\"\"\", 'one row, written by hand')""")
n.md("""
`slot` says **by hand** and `run_id` says **not airflow**, because nothing
scheduled this. Watch both of those change in a minute.

---

# Step 2 · The DAG

A DAG is **a picture of what has to happen before what**. Three words for one
idea:

| | |
|---|---|
| **D**irected | the arrows point one way |
| **A**cyclic | no loops. nothing waits for itself |
| **G**raph | a set of tasks with arrows between them |

Ours has one task, so the picture is a dot. That is fine: **the schedule is the
lesson here, not the shape.**
""")
n.code("""TEACH_DAG = '''
from __future__ import annotations
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

# where the project is mounted INSIDE the container. Not the path on your laptop.
PROJECT = "/opt/kerb/teach"

with DAG(
    dag_id="teach_dag",
    description="the smallest useful DAG, built in notebook 12",
    schedule="*/1 * * * *",                        # every minute
    start_date=pendulum.now("UTC").subtract(minutes=5),
    catchup=False,                                 # do NOT backfill what was missed
    max_active_runs=1,                             # never two runs at once
    default_args={"retries": 1,
                  "retry_delay": pendulum.duration(minutes=1)},
    tags=["course"],
) as dag:

    BashOperator(
        task_id="heartbeat",
        # the exact command you typed above. {{ ts }} is Airflow filling in
        # which scheduled slot this run is for, at run time.
        bash_command=f"cd {PROJECT} && SLOT={{{{ ts }}}} python -m pipelines.heartbeat",
        env={"PYTHONPATH": PROJECT},
        append_env=True,
    )
'''

print(TEACH_DAG)""")
n.md("""
### Read every argument as a question being answered

| | |
|---|---|
| `schedule="*/1 * * * *"` | how often? Every minute. Normally you would write `0 * * * *` for hourly |
| `start_date` | from when does that schedule apply? |
| `catchup=False` | if I enable this today, backfill everything missed since `start_date`? **Almost always no** |
| `max_active_runs=1` | can two runs overlap? Not for a pipeline that rebuilds a window |
| `retries` | how many times before we admit it is broken? |

**`catchup` is the one that bites people.** Leave it `True` with a start date six
months ago and enabling the DAG launches several hundred runs at once, against
production, immediately.

### And notice what the task is NOT

![](img/airflow-3-task.png)

It is **not a copy of the pipeline logic.** It runs the exact command you ran
yourself two cells ago. Two things follow:

**Any Airflow failure reproduces on your laptop** by typing one line. There is
no *"it only breaks in Airflow"*.

**The pipeline has never heard of Airflow.** Swap it for something else tomorrow
and `heartbeat.py` does not change.

---

# Step 3 · Deploy it

Deploying a DAG really is this: **write the file into the folder the scheduler
watches.** No build, no registration, no restart.
""")
n.code("""target = DAGS / 'teach_dag.py'
target.write_text(TEACH_DAG.lstrip())

print(f'wrote {target}')

# the scheduler rescans that folder on a timer. Ask how long that timer is.
print('rescan interval:',
      airflow('config', 'get-value', 'scheduler', 'dag_dir_list_interval', quiet=True),
      'seconds')

airflow('dags', 'reserialize', quiet=True)                # do it now, do not wait 5 minutes
airflow('dags', 'pause', 'teach_dag', quiet=True)         # arrive paused, so we can watch it start
print('deployed')""")
n.md("""
---

# Step 4 · Does Airflow see it?

Three questions, in this order. The first one is the one people skip.
""")
n.code("""airflow('dags', 'list-import-errors')""")
n.md("""
`No data found` is what you want. **A DAG file that raises on import does not
become a broken DAG, it becomes no DAG at all**, and this is the only place that
is reported.
""")
n.code("""out = airflow('dags', 'list', quiet=True)
print(out.splitlines()[0])
print('\\n'.join(l for l in out.splitlines() if 'teach_dag' in l))""")
n.code("""airflow('tasks', 'list', 'teach_dag')""")
n.md("""
---

# Step 5 · Run it once, by hand

`airflow tasks test` runs a single task immediately, ignoring the schedule and
ignoring dependencies. It is what you use while developing.
""")
n.code("""out = airflow('tasks', 'test', 'teach_dag', 'heartbeat', '2026-09-01', quiet=True)
print('\\n'.join(l for l in out.splitlines()
                 if 'heartbeat:' in l or 'Running command' in l or 'Marking task' in l))""")
n.code("""sql(f\"\"\"
    SELECT to_char(ran_at, 'HH24:MI:SS') AS ran_at, slot, run_id
    FROM {SCHEMA}.heartbeat ORDER BY ran_at DESC LIMIT 5
\"\"\", 'the row Airflow just wrote')""")
n.md("""
**That ran inside the Airflow container**, against the same Postgres, using the
same file you wrote in step 1. Not a simulation.

---

# Step 6 · Turn the schedule on

Everything so far, somebody pressed. **A DAG that only runs when you press it is
a shell script with a nicer log viewer.**

First, while it is still paused, ask Airflow when it *would* run. It knows,
because a schedule is **a declared cadence**, not a process sitting in a loop.
""")
n.code("""out = airflow('dags', 'next-execution', 'teach_dag', quiet=True)

# a paused DAG adds a reminder line, so pick the line that is actually a date
when = [l.strip() for l in out.splitlines() if l.strip()[:1].isdigit() and 'T' in l]
print('next slot :', when[-1] if when else out.splitlines()[-1])
print('is_paused :', [l for l in airflow('dags', 'list', quiet=True).splitlines()
                      if 'teach_dag' in l][0].split('|')[-1].strip())""")
n.md("""
It knows exactly when it would run, and it is not going to, because **nobody has
said yes yet**.

## Now say yes, and wait
""")
n.code("""def runs_of(dag_id):
    out = airflow('dags', 'list-runs', '-d', dag_id, '-o', 'json', quiet=True)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []

already = {r['run_id'] for r in runs_of('teach_dag')}
print(f'{len(already)} runs exist already. Watching for a NEW one.\\n')

airflow('dags', 'unpause', 'teach_dag', quiet=True)

t0, fresh = time.time(), []
for _ in range(24):
    fresh = [r for r in runs_of('teach_dag')
             if r['run_id'] not in already and r['run_id'].startswith('scheduled')]
    done = [r for r in fresh if r['state'] == 'success']
    print(f'{int(time.time() - t0):>4}s   new scheduled runs: {len(fresh)}, finished: {len(done)}')
    if done:
        break
    time.sleep(10)

for r in fresh:
    print(f\"\\n  {r['run_id']}   {r['state']}\")""")
n.md("""
### Nobody triggered that

Look at the run id. It starts with **`scheduled__`**, not `manual__`. That run
exists because a cron expression in a file said it should, and the scheduler
agreed.

## And here is the row it wrote

Run this cell, talk for a minute, run it again.
""")
n.code("""sql(f\"\"\"
    SELECT to_char(ran_at, 'HH24:MI:SS') AS ran_at, slot, run_id
    FROM {SCHEMA}.heartbeat ORDER BY ran_at DESC LIMIT 8
\"\"\", 'one row per scheduled minute')""")
n.md("""
### The `slot` column is the bit worth pointing at

`ran_at` is when the machine did the work. `slot` is **which minute the work was
for**. They are not the same thing, and confusing them is one of the most
expensive mistakes in this job.

A run that starts at 03:07 because the scheduler was busy is still rebuilding
the 03:00 window. Every pipeline in this course takes its window from the data
or from the slot, **never from `now()`**, for exactly that reason.

## Go and look at it

Open **http://localhost:8080** (`kerb` / `kerb_local_dev`), find `teach_dag`,
and put the **Grid** view on the screen. A new green square appears every minute
while you talk.

| In the UI | What it shows |
|---|---|
| **Grid** | one column per run, one square per task, green or red |
| **Next Run** | the next slot, the same number you printed above |
| the pause toggle | the same thing `dags pause` does |
| a square, then **Logs** | that pipeline's own output |
| **Clear** on a square | rerun just that task |

---

# Step 7 · Turn it off

An every-minute DAG left running will fill that table forever.
""")
n.code("""airflow('dags', 'pause', 'teach_dag')

n_rows = fetch(f'SELECT count(*) AS n FROM {SCHEMA}.heartbeat').n[0]
print(f'\\n{n_rows} heartbeat rows. That number stops moving now.')""")
n.md("""
---

## The real one, which is the same thing with more tasks

`airflow/dags/teach_pipelines.py` in this project schedules the eight pipelines
you built in notebooks 2 to 8. Same file shape, same BashOperators, same
deployment. Two extra ideas:

![](img/airflow-2-dag.png)
""")
n.code("""airflow('tasks', 'list', 'teach_pipelines')""")
n.md("""
**One:** `bronze >> silver >> gold` is the whole graph. The six bronze tasks
share nothing, so Airflow runs all six at once, for free. And the guarantee that
one line gives you is absolute:

> **Gold can never be built from a silver table that failed to refresh.**

Not "should not". *Cannot.* If silver fails, Airflow does not start gold.

**Two:** the last task runs the signal board, and it **does not fail the DAG**
when a signal breaches. "A number moved and a human should look" is not the same
as "the run is broken". Failing there would page the on-call engineer for a
number that is often completely correct.

To deploy that one, the project has a command:

```bash
python cli.py deploy
```

---

## What Airflow does not do

- it does **not** move your data. Your code does
- it does **not** know whether your data is correct. That is the signal board
- it does **not** make a bad pipeline good. It runs it on time and tells you it failed

## What you learned

- Airflow **starts programs**. It never touches a row
- **Two files**: one does the work, one says when. They live in different folders
- A task runs **the same command you would type**
- **Deploying is writing a file** into a watched folder
- `catchup=False` unless you genuinely want a backfill
- A paused DAG still knows its next slot. **A schedule is a declared cadence**
- `slot` is which window the run is for. `now()` is not
- `bronze >> silver >> gold` makes stale gold **impossible**, not just unlikely
""")
n.save()

# ═══════════════════════════════════════════════════════════════════════════
n = NB("10-kafka-from-scratch.ipynb")
n.md("""
# 10 · Kafka, from nothing

You do not need to have heard of Kafka.

Every cell below is **real Kafka code that you run**. Nothing is hidden in a
helper file. By the end you will have sent a message to a broker running on this
laptop, found it again by its address, and read it back.
""")
n.md("""
---

## Word 1 · an **event**

An event is **a thing that happened**. Past tense. Finished.

```
    a rider requested a ride at 14:02
    a driver accepted it   at 14:04
    the ride completed     at 14:31
```

Three facts about an event:

**It is in the past.** Not a plan. It happened.
**It cannot be changed.** You cannot un-happen it. To correct it you send a
*new* event; you never edit the old one.
**It is small.** One thing, one moment.

Now compare a database row. A row is a statement about **the present**: *"this
ride currently has status completed"*. Update it and the previous value is gone.
Nothing remembers it used to say `in_progress`.

> A table tells you **how things are**.
> A stream of events tells you **how things got that way**.
""")
n.md("""
---

## Word 2 · the **broker**, and Word 3 · a **topic**

The broker is a program that holds events. A topic is a named place inside it.

![](img/kafka-1-shape.png)

There is a broker running in Docker on this laptop. Let us ask it what it has.
""")
n.code("""import sys; sys.path.insert(0, '.')
from nb import run                       # the one helper: runs a pipeline, shows its log
from pipelines.lib.config import KAFKA   # the address, read from .env

from confluent_kafka.admin import AdminClient

BROKER = KAFKA                           # usually localhost:19092
print('broker:', BROKER)

admin = AdminClient({'bootstrap.servers': BROKER})
metadata = admin.list_topics(timeout=10)

for name, topic in sorted(metadata.topics.items()):
    if name.startswith('__'):
        continue                     # Kafka's own internal bookkeeping
    print(f'{name:28} {len(topic.partitions)} partitions')""")
n.md("""
Four topics. They exist for the same reason folders exist: so different kinds
of thing do not get mixed up. Ride events in one, GPS pings in another.

`.dlq` means **dead letter queue**, where a message goes when nothing can read
it.

---

## Word 4 · a **producer**

A producer is anything that sends events. The KERB app is one. You are about to
be one.

Here is the smallest possible producer. Read it before you run it.
""")
n.code("""from confluent_kafka import Producer
from pipelines.lib.config import TOPIC_RIDES
import json, datetime as dt

TOPIC = TOPIC_RIDES                      # 'kerb.trips.lifecycle'

# 1. a producer is a client object. It knows one thing: where the broker is.
producer = Producer({'bootstrap.servers': BROKER})

# 2. the event itself. Just a dictionary. Kafka does not care what is in it.
event = {
    'trip_id':   'TRP-DEMO-001',
    'event':     'requested',
    'ts':        dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    'driver_id': None,
    'pu_zone_id': 42,
}

# 3. Kafka speaks bytes, not python. So we serialise to JSON and encode.
value = json.dumps(event).encode('utf-8')
key   = event['trip_id'].encode('utf-8')     # why a key matters comes later

# 4. produce() does not send immediately. It queues.
producer.produce(TOPIC, key=key, value=value)

# 5. flush() waits until everything queued has actually reached the broker.
#    Forget this line and your program can exit before the message is sent.
producer.flush(10)

print('sent')""")
n.md("""
### Five lines, and the last one catches people out

`produce()` queues. `flush()` is what actually waits for the broker to confirm.
A script that produces and then exits without flushing sends nothing at all, and
raises no error.

## But where did it go?

The broker tells you, if you ask. Add a delivery callback.
""")
n.code("""landed = {}

def on_delivery(err, msg):
    \"\"\"Kafka calls this once it knows what happened to the message.\"\"\"
    if err is not None:
        print('failed:', err)
    else:
        landed['partition'] = msg.partition()
        landed['offset']    = msg.offset()

event['trip_id'] = 'TRP-DEMO-002'
producer.produce(TOPIC,
                 key=event['trip_id'].encode(),
                 value=json.dumps(event).encode(),
                 on_delivery=on_delivery)      # <- the callback
producer.flush(10)

print(f\"it landed at partition {landed['partition']}, offset {landed['offset']}\")""")
n.md("""
---

## Word 5 · a **partition**, and Word 6 · an **offset**

Those two numbers are the message's permanent address.

![](img/kafka-2-partitions.png)

A topic is not one queue. It is split, so several readers can work at once.

Let us count what is actually on each partition.
""")
n.code("""from confluent_kafka import Consumer, TopicPartition

consumer = Consumer({'bootstrap.servers': BROKER,
                     'group.id': 'just-looking'})     # any name, we only read metadata

partitions = sorted(consumer.list_topics(TOPIC, timeout=10).topics[TOPIC].partitions)

total = 0
print(f'{\"partition\":>10} {\"first\":>10} {\"next\":>10} {\"messages\":>12}')
for p in partitions:
    # watermarks: the lowest offset still kept, and the offset the NEXT message gets
    low, high = consumer.get_watermark_offsets(TopicPartition(TOPIC, p), timeout=10)
    total += high - low
    print(f'{p:>10} {low:>10,} {high:>10,} {high - low:>12,}')
print(f'{\"total\":>10} {\"\":>10} {\"\":>10} {total:>12,}')
consumer.close()""")
n.md("""
### The rule that matters

**Kafka only guarantees order *within* one partition.** Across partitions there
is no order at all.

So how do five events of one ride stay in order? Because we passed a **key**
(`trip_id`), and Kafka always puts the same key on the same partition.

> Same key → same partition → same order. Always.

Get that wrong and `completed` can land before `requested`, with no error,
because nothing is broken. You asked for the impossible.

---

## Reading is not destructive

Go back to the exact address of the message you sent and read it again.
""")
n.code("""consumer = Consumer({'bootstrap.servers': BROKER,
                     'group.id': 'just-looking',
                     'enable.auto.commit': False})

# assign() means "put me at this exact position", ignoring any saved bookmark
tp = TopicPartition(TOPIC, landed['partition'], landed['offset'])
consumer.assign([tp])

msg = None
for _ in range(20):                # poll until the message arrives
    m = consumer.poll(1.0)
    if m is not None and not m.error():
        msg = m
        break
consumer.close()

print(f'read from partition {msg.partition()}, offset {msg.offset()}:\\n')
print(json.dumps(json.loads(msg.value()), indent=2))""")
n.md("""
### It is still there

**A queue is destructive**: take a message off and it is gone, and only one
consumer can ever have it.

**Kafka is a log, not a queue.** Reading removes nothing. Five different teams
read the same events independently, and none of them asks the others'
permission.

---

## Word 7 · a **consumer group**

If reading removes nothing, how does a consumer remember where it got to?

It tells the broker, under a name. That name is the consumer group.

![](img/kafka-3-groups.png)
""")
n.code("""groups = admin.list_consumer_groups(request_timeout=10).result().valid

for g in sorted(x.group_id for x in groups):
    c = Consumer({'bootstrap.servers': BROKER, 'group.id': g,
                  'enable.auto.commit': False})
    tps = [TopicPartition(TOPIC, p) for p in partitions]
    position = lag = 0
    for tp, committed in zip(tps, c.committed(tps, timeout=10)):
        low, high = c.get_watermark_offsets(tp, timeout=10)
        # a group that has never committed has offset -1001, so fall back to low
        at = committed.offset if committed.offset and committed.offset >= 0 else low
        position += at
        lag      += high - at
    c.close()
    print(f'{g:24} position {position:>10,}   still to read {lag:>8,}')""")
n.md("""
Two groups read this topic. `teach-bronze-events` is our pipeline.
`bronze-loader` belongs to a different project entirely.

**Separate bookmarks. Neither can affect the other.**

That last number is called **lag**: how far behind a group is.

It also explains something you will hit: `reset` has to delete the group,
because the bookmark lives on the **broker**, not in our database. Drop our
tables without deleting the group and the pipeline wakes up believing it has
already read everything.
""")
n.md("""
---

## Word 8 · a **consumer**

Now write one. This is the shape of every Kafka consumer you will ever write.

We start it **before** sending anything, so you can watch events arrive live.
""")
n.code("""from confluent_kafka import Consumer

watcher = Consumer({
    'bootstrap.servers': BROKER,
    'group.id': 'notebook-watcher',    # our name. the broker keeps our bookmark under it
    'auto.offset.reset': 'latest',     # never read before? start at the END, not the beginning
    'enable.auto.commit': False,       # WE decide when the bookmark moves
})

# subscribe means "give me this topic, wherever my bookmark is"
watcher.subscribe([TOPIC])

# subscribing is a request, not an answer. The broker has to assign us partitions,
# and that only happens while we poll. So poll until we actually have them.
for _ in range(20):
    watcher.poll(1.0)
    if watcher.assignment():
        break

print('watching:', sorted(f'partition {t.partition}' for t in watcher.assignment()))
print('nothing to read yet. it is sitting at the end of the topic, waiting.')""")
n.md("""
### subscribe, versus assign

Two different asks, and the difference matters.

| | |
|---|---|
| `assign()` | *put me at exactly this partition and offset.* We used it earlier to go back to one message. No group, no bookmark. |
| `subscribe()` | *give me this topic, and remember where I got to.* The broker hands out the partitions and keeps our place. |

---

## Now send a whole ride

Five events, one ride. Same key every time, so they all land on the same
partition, in order.
""")
n.code("""import random

trip_id = f'TRP-DEMO-{random.randint(1000, 9999)}'
now     = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
driver  = f'DRV{random.randint(1, 2800):06d}'
fare    = round(random.uniform(60, 420), 2)

LIFECYCLE = ['requested', 'accepted', 'driver_arrived', 'started', 'completed']

producer = Producer({'bootstrap.servers': BROKER})
for i, name in enumerate(LIFECYCLE):
    e = {'trip_id': trip_id,
         'event':   name,
         'ts':      (now + dt.timedelta(minutes=i * 3)).isoformat(),
         'driver_id': None if name == 'requested' else driver,
         'pu_zone_id': 42}
    if name == 'completed':
        e['fare'] = fare
    producer.produce(TOPIC, key=trip_id.encode(), value=json.dumps(e).encode())
    print(f'  queued {name}')
producer.flush(10)
print(f'\\n{trip_id}: 5 events on the topic')""")
n.md("""
## The watcher was listening. Ask it what it saw.
""")
n.code("""seen = []
for _ in range(20):
    batch = watcher.consume(num_messages=500, timeout=1.0)
    for m in batch or []:
        if m.error():
            continue
        d = json.loads(m.value())
        if d.get('trip_id') == trip_id:              # only the ride we just sent
            seen.append((m.partition(), m.offset(), d['event']))
    if len(seen) == 5:
        break

for part, off, ev in seen:
    print(f'  partition {part}  offset {off:>8}  {ev}')""")
n.md("""
**All five, on the same partition, in the order they happened.**

That is the key doing its job. Had we passed no key, Kafka would have spread the
five events across all three partitions, and `completed` could have been read
before `requested`, with no error, because nothing would be broken. We would
have asked for the impossible.

## We read them. We have not saved our place.

`enable.auto.commit` was `False`, so the bookmark has not moved. Prove that,
then move it deliberately.
""")
n.code("""tps = watcher.assignment()

before = watcher.committed(tps, timeout=10)
print('bookmark before commit:', [t.offset for t in before], '  (-1001 means never set)')

watcher.commit(asynchronous=False)          # NOW save our place

after = watcher.committed(tps, timeout=10)
print('bookmark after  commit:', [t.offset for t in after])
watcher.close()""")
n.md("""
### This is the whole safety argument

Read a batch. **Write it.** *Then* commit.

Crash before the commit and the next run reads the same messages again, and
writes them again. That is called **at-least-once**, and it is why every table
we write has a primary key and an `ON CONFLICT DO NOTHING`: writing the same
event twice has to be harmless.

Turn auto-commit on and you get the opposite order. Kafka saves your place while
the rows are still only in memory. Crash there and those messages are gone for
good, and nothing anywhere reports an error.

---

## The events exist. The warehouse has never heard of them.

Two questions, and both get answered with a real number rather than a promise.

### 1 · Where exactly are our five events?

We already know, because the watcher told us. Say it out loud.
"""
)
n.code("""for part, off, ev in seen:
    print(f'  partition {part}  offset {off:>8}  {ev}')

our_partition = seen[0][0]
first_offset  = min(o for _, o, _ in seen)
last_offset   = max(o for _, o, _ in seen)

print(f'\\nall five are on partition {our_partition}, offsets {first_offset:,} to {last_offset:,}')""")
n.md("""
### 2 · How far has the pipeline read on that partition?

The pipeline is a consumer group called `teach-bronze-events`. Its bookmark
lives on the broker. Ask the broker where it is.
""")
n.code("""def bookmark(group, partition):
    \"\"\"Where a group has read up to on one partition, and where the end is.\"\"\"
    c = Consumer({'bootstrap.servers': BROKER, 'group.id': group,
                  'enable.auto.commit': False})
    tp = TopicPartition(TOPIC, partition)
    committed  = c.committed([tp], timeout=10)[0]
    low, high  = c.get_watermark_offsets(tp, timeout=10)
    c.close()
    # a group that has never committed reports -1001, so fall back to the oldest
    at = committed.offset if committed.offset and committed.offset >= 0 else low
    return at, high

at, high = bookmark('teach-bronze-events', our_partition)

print(f'partition {our_partition}')
print(f'  the pipeline has read up to offset  {at:>10,}')
print(f'  our first event sits at offset      {first_offset:>10,}')
print(f'  the newest message on it is at      {high - 1:>10,}')
print()
if at <= first_offset:
    print(f'  the bookmark is BEFORE our events. It has not seen them.')
    print(f'  {high - at:,} messages on this partition are still unread.')
else:
    print('  a scheduled run has already read past them. Send another ride and rerun.')""")
n.md("""
### And the answer that settles it

Offsets are Kafka's opinion. The warehouse is the thing finance queries. Ask it.
""")
n.code("""import psycopg
from pipelines.lib.config import dsn, SCHEMA

with psycopg.connect(dsn()) as c:
    try:
        n_rows = c.execute(f'SELECT count(*) FROM {SCHEMA}.bronze_events WHERE trip_id = %s',
                           (trip_id,)).fetchone()[0]
    except Exception:
        n_rows = 0        # the table does not exist yet, which is also zero rows

print(f'SELECT count(*) FROM {SCHEMA}.bronze_events WHERE trip_id = {trip_id!r}')
print(f'\\n  {n_rows}')
print('\\nfive events exist on the topic. Nothing has moved them.')""")
n.md("""
---

## And now the real pipeline, which does exactly this plus the bookkeeping

Same producer, same consumer, same commit-last ordering. What it adds is the
contract, the quarantine, and a row in the run log.
""")
n.code("""run('-m', 'pipelines.p2_bronze_events')""")
n.code("""at, high = bookmark('teach-bronze-events', our_partition)

print(f'partition {our_partition}')
print(f'  our last event was at offset  {last_offset:>10,}')
print(f'  the bookmark is now at        {at:>10,}   (the offset it will read NEXT)')
print(f'  so it has moved past all five of ours\\n')

with psycopg.connect(dsn()) as c:
    rows = c.execute(f\"\"\"SELECT event, happened_at, fare
                        FROM {SCHEMA}.bronze_events WHERE trip_id = %s
                        ORDER BY happened_at\"\"\", (trip_id,)).fetchall()
print(f'\\n{trip_id} in the warehouse:')
for e, t, f in rows:
    print(f'  {e:16} {t}  {f if f is not None else \"\"}')""")
n.md("""
---

## Last thing: a message nobody can read

The pipeline's contract requires `trip_id`, `event` and `ts`. Send one with an
empty `ts` and watch what happens to it, and to the four around it.
""")
n.code("""broken_id = f'TRP-BROKEN-{random.randint(1000, 9999)}'
producer = Producer({'bootstrap.servers': BROKER})

for i, name in enumerate(LIFECYCLE):
    e = {'trip_id': broken_id, 'event': name,
         'ts': (now + dt.timedelta(minutes=i * 3)).isoformat(),
         'driver_id': driver}
    if name == 'started':
        e['ts'] = ''            # the contract requires this. it is empty.
    producer.produce(TOPIC, key=broken_id.encode(), value=json.dumps(e).encode())
producer.flush(10)
print(f'{broken_id}: 5 events sent, one of them unreadable')""")
n.code("""run('-m', 'pipelines.p2_bronze_events')""")
n.code("""with psycopg.connect(dsn()) as c:
    landed_n = c.execute(f'SELECT count(*) FROM {SCHEMA}.bronze_events WHERE trip_id = %s',
                         (broken_id,)).fetchone()[0]
    held = c.execute(f\"\"\"SELECT reason, payload->>'partition', payload->>'offset'
                        FROM {SCHEMA}.quarantine
                        WHERE payload->>'raw' LIKE %s\"\"\", (f'%{broken_id}%',)).fetchall()

print(f'landed in bronze_events : {landed_n}')
print(f'held in quarantine      : {len(held)}\\n')
for reason, part, off in held:
    print(f'  {reason}')
    print(f'  it is still on the topic at partition {part}, offset {off}')""")
n.md("""
**Four landed. One held. Nothing crashed.**

And look at the last line: quarantine kept the **partition and offset**. Because
an offset is a permanent address, you can go straight back to the topic and read
that exact message again.

That is the difference between *"something went wrong last night"* and *"here it
is, this is the message, this is why"*.

---

## Every word, in one place

| | |
|---|---|
| **event** | a thing that happened. past tense, immutable |
| **broker** | the program that holds events. one is in Docker on this laptop |
| **topic** | a named place to put events |
| **producer** | anything that sends. `produce()` queues, `flush()` sends |
| **consumer** | anything that reads. reading removes nothing |
| **partition** | a topic is split, so several readers work at once |
| **offset** | a permanent address inside a partition |
| **key** | same key → same partition → order is kept |
| **consumer group** | a name, and a bookmark the broker stores against it |
| **lag** | how far behind a group's bookmark is |

## Three reasons Kafka exists

1. **A table says how things are. A stream says how they got that way.**
2. **Many independent consumers.** Reading does not remove.
3. **Partitions let readers work in parallel**, and a key keeps order where it matters.
""")
n.save()
