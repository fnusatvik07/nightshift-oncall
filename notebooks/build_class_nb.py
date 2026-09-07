"""The class: two notebooks, run live in front of a room.

Not a guide for the instructor. This is what the room sees.

    00-class-1-building-the-signal-service.ipynb
    00-class-2-building-the-agent-system.ipynb

The rule these two follow, and the reason they exist separately from notebooks
1 to 19: **build the thing in front of people, do not import the finished thing
and print it.** Running a working system and narrating the output teaches
nobody how it was made. Every idea here is written from nothing in a cell, run,
and only then matched against the real file it became.
"""
import nbformat as nbf

KERNEL = {"display_name": "NIGHTSHIFT oncall", "language": "python",
          "name": "nightshift-oncall"}


class NB:
    def __init__(self, filename):
        self.filename, self.cells = filename, []

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
        print(f"  {self.filename:48} {len(self.cells):>3} cells ({c} code)")


RESET = """run('break_it.py', '--fix')     # undo the break, if it is still in place
run('cli.py', 'reset')          # empty warehouse, no incidents, no artifacts
run('cli.py', 'run', 'all')     # rebuild all eight pipelines, about 40 seconds"""


# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
#
#  NOTEBOOK 1 · BUILDING THE SIGNAL SERVICE
#
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════

n = NB("00-class-1-building-the-signal-service.ipynb")

n.md("""
# Building the signal service

### Everything on this screen is running for real. Nothing here is a slide.

---

You are going to watch a data platform break in the way that costs companies the
most money: **quietly**. No crash, no error, no alert, every dashboard green, and
a number that a real team makes decisions with is wrong.

Then you are going to **build the service that catches it**, from nothing, one
idea at a time. Not read it. Build it, run it, and only at the end compare what
you built with what is in the repository.

**No prior knowledge assumed.** If you have never written a data pipeline, you
are in the right room.
""")
n.code("""import sys; sys.path.insert(0, '..')
import inspect, json, statistics, psycopg
from pipelines.lib.config import dsn, SCHEMA, MONGO_URI
from nb import show, sql, fetch, run

print('connected to the warehouse.')""")
n.md("""
### Start from a clean slate

Run this if anything here has been run before, or if a previous session left the
estate half broken. It puts the source data back, empties the warehouse, forgets
every incident, and rebuilds all eight pipelines from nothing.

**Safe to run at any point.** If you get lost later, come back to this cell.
""")
n.code(RESET)

# ── the problem ────────────────────────────────────────────────────────────
n.md("""
---

# Part 1 · A number goes wrong and nothing fails

## The company

KERB is a ride hailing company. Riders book cars, drivers accept them, money
moves. The data lives in **six different systems**, because it was built by six
different teams over six different years:

| where | what is in it | what it looks like |
|---|---|---|
| PostgreSQL | the rides themselves | rows in a table |
| Kafka | every event in a ride's life | messages on a stream |
| **MongoDB** | **what the driver's phone reported** | **documents, no fixed shape** |
| a partner's API | whether the money settled | JSON over HTTP |
| MinIO | the regulator's nightly file | gzipped CSV |
| PostgreSQL | the list of zones | a small reference table |

Nobody can answer *"how much did we earn on Tuesday"* from six systems at once.
So we copy all six into one place, shaped for questions instead of for apps.
That place is the **warehouse**, and this is what finance reads every morning.
""")
n.code("""sql(f\"\"\"
    SELECT trip_date, rides, completed, cancelled, revenue, avg_surge
    FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 7
\"\"\", 'gold_daily · the answer somebody reads every morning')""")
n.md("""
Seven days, one row each. Note **`avg_surge`** on the right. Surge is the
multiplier applied when demand is high, and the pricing team use it to decide
whether the pricing model is behaving.

**Remember that column.** It is the one that is about to go wrong.

## Where that number comes from

It is not typed in by anybody. It is carried, one hop at a time, from a phone in
a car to that table.

```
    the driver's phone
          |
          v
    MongoDB   kerb_app.driver_app_events        <- a document per event
          |
          |   p3_bronze_driver_app      copy it, keep it faithful
          v
    teach.bronze_driver_app                     <- our copy
          |
          |   p7_silver_rides           one clean row per ride
          v
    teach.silver_rides
          |
          |   p8_gold_daily             one row per day
          v
    teach.gold_daily                            <- what finance reads
```

Four hops. **The break happens at the very first one**, and every hop after it
carries on working perfectly.

## What one of those documents actually looks like

Not a diagram of a document. A real one, read out of MongoDB right now, printed
exactly as it is stored.
""")
n.code("""from pymongo import MongoClient

events = MongoClient(MONGO_URI).kerb_app.driver_app_events

def one_document(version):
    \"\"\"One real trip_offer document from a given app version.\"\"\"
    return events.find_one({'app.version': version, 'event_type': 'trip_offer'},
                           {'_id': 0, 'location': 0, 'device': 0})

print(json.dumps(one_document('4.2.0'), indent=2, default=str))""")
n.md("""
Read the bottom of that document. The surge multiplier is in there, nested:

```
    "payload": { "pricing": { "surgeFactor": 1.07 } }
```

**Nothing enforces that shape.** MongoDB accepts a document of any shape at all.
The phone decides where to put the value, and the phone is written by a different
team, on a different release cycle, who have never met you.

## So the pipeline has to know where to look

Here is the real code that reads surge out of a document. Not a description of
it, the code, out of the file that ran to build the table above.
""")
n.code("""from pipelines import p3_bronze_driver_app as p3

print('the four places this pipeline knows to look:')
print()
for path in p3.SURGE_PATHS:
    print(f'    doc[{\"][\".join(repr(k) for k in path)}]')
print()
print('and the function that tries them, in order:')
print()
print(inspect.getsource(p3.surge_of))""")
n.md("""
Four known places, tried in order. The first that has a value wins.

Those four paths are not a design. They are **scar tissue**: each was added the
day a release moved the field and somebody spent an afternoon finding out.

And look at what happens when none of them match. It does **not** write a zero
and it does **not** write a null. It **holds** the document, with the reason
attached. That decision matters in about two minutes.

---

## Now break it

A new mobile release goes out. It moves the surge value one level deeper, from
`payload.pricing.surgeFactor` to `payload.pricing.surge.factor`.

A perfectly reasonable refactor. They are tidying their own payload. Nobody tells
the data team, because from where they sit nothing about the app changed.
""")
n.code("""run('break_it.py')""")
n.md("""
## The same document, again

Same query, same collection, same app version. This is what the phone sends now.
""")
n.code("""print(json.dumps(one_document('4.2.0'), indent=2, default=str))""")
n.md("""
Put the two side by side, because this one change is the whole lesson.

| | where surge lives |
|---|---|
| **before** | `payload` &rarr; `pricing` &rarr; **`surgeFactor`** |
| **after** | `payload` &rarr; `pricing` &rarr; **`surge`** &rarr; **`factor`** |

The value is still there. It is still correct. It is still 1.07. It is one level
deeper and spelled differently, and **none of our four known paths matches it**.

Nothing about this is malicious or even careless. This is Tuesday.

## Re-run the pipelines and watch nothing fail
""")
n.code("""run('cli.py', 'run', 'all')""")
n.md("""
## Read that output slowly, because this is the part people miss

**Every pipeline says `ok`.** Nothing crashed. Nothing raised. No retry, no
alert, no red anything.

But look at the driver app line:

```
    p3_bronze_driver_app: ok   read 40,000   wrote 30,131
```

It read forty thousand documents and wrote thirty thousand. **Nine thousand
eight hundred and sixty nine documents did not become rows**, and it still
reported success, because from its point of view nothing went wrong: it was
asked to copy what it could read, and it did exactly that.
""")
n.code("""sql(f\"\"\"
    SELECT pipeline, status, rows_in, rows_out,
           rows_in - rows_out AS did_not_land,
           to_char(started_at, 'HH24:MI:SS') AS at
    FROM {SCHEMA}.runs
    WHERE pipeline = 'p3_bronze_driver_app'
    ORDER BY started_at DESC LIMIT 3
\"\"\", 'the run log · success, and ten thousand rows short')""")
n.md("""
## Where did the missing ten thousand go?

They were **held**. Not dropped, not defaulted, not silently zeroed: written to
a quarantine table with the reason attached and the original document intact.
""")
n.code("""sql(f\"\"\"
    SELECT reason, count(*) AS records
    FROM {SCHEMA}.quarantine
    WHERE pipeline = 'p3_bronze_driver_app'
    GROUP BY 1
\"\"\", 'why they were held')

with psycopg.connect(dsn()) as c:
    held = c.execute(f\"\"\"SELECT payload FROM {SCHEMA}.quarantine
                         WHERE pipeline = 'p3_bronze_driver_app'
                         ORDER BY seen_at DESC LIMIT 1\"\"\").fetchone()[0]

print('one held document, exactly as it arrived:')
print()
print(json.dumps(held, indent=2)[:700])""")
n.md("""
There it is. `payload.pricing.surge.factor`, sitting in quarantine, value intact.

**The evidence of what broke is in the warehouse**, written by the pipeline at
the moment it happened, which is the only time anybody knew enough to write it
down.

> Holding a record costs you an incomplete table for a day.
> Defaulting it to zero costs you a wrong number forever, with nothing to point at.

## What the warehouse says now

The whole 4.2.0 release has **vanished** from our copy. Not corrupted. Gone.
""")
n.code("""sql(f\"\"\"
    SELECT app_version, count(*) AS rows_that_landed
    FROM {SCHEMA}.bronze_driver_app
    GROUP BY 1 ORDER BY 1
\"\"\", 'bronze_driver_app · one app version is missing entirely')""")
n.md("""
## This is the entire problem

| What a normal platform checks | What it says today |
|---|---|
| did the pipeline run? | yes |
| did it fail? | no |
| did it throw an error? | no |
| did every row land? | **no, and nothing asked** |
| is the number correct? | **no** |

> **A pipeline that fails wakes somebody up.**
>
> **A pipeline that succeeds while quietly carrying less data than it should
> wakes nobody.**

Every check in the left column stays green. So does every error log, every retry
policy, and every dashboard that shows pipeline status, because all of them watch
**the machinery** and none of them watch **the number**.

**So we are going to build the thing that watches the number.** From nothing.
""")

# ── building it ────────────────────────────────────────────────────────────
n.md("""
---

# Part 2 · Building the signal service, step by step

Twelve steps. Each one is a decision, and each one exists because the previous
step was not enough. Nothing here is imported until we have written it.

## Step 1 · A number, on its own, is useless

Here is a real number, correctly calculated, from the table finance reads.
""")
n.code("""with psycopg.connect(dsn()) as c:
    revenue = float(c.execute(
        f'SELECT revenue FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1'
    ).fetchone()[0])

print(f'revenue yesterday: {revenue:,.2f}')
print()
print('Question for the room: is that good or bad?')""")
n.md("""
Nobody can answer that. Not you, not me, not any alerting product ever sold.

> **A number has no opinion about itself.**

To have an opinion you need a second thing: **what it normally is**.
""")
n.code("""with psycopg.connect(dsn()) as c:
    history = [float(r[0]) for r in c.execute(
        f'SELECT revenue FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1')]

baseline = statistics.mean(history)
spread   = statistics.pstdev(history)

print(f'  yesterday      {revenue:>14,.2f}')
print(f'  normally       {baseline:>14,.2f}    over {len(history)} days')
print(f'  usual wobble   {spread:>14,.2f}')
print()
print(f'  {(revenue - baseline) / max(spread, 0.01):>5.2f} wobbles from normal')""")
n.md("""
That last number has a name. It is a **z-score**: how many standard deviations
from the mean. It is the whole of the statistics in this project.

> ### A **KPI** is a number with a definition and an owner. It can never raise an alarm.
> ### A **signal** is a KPI plus a baseline plus a tolerance. That is the thing that goes off.

Most "we need better monitoring" conversations are actually about the missing
second half, and nobody wants to write it, because writing it means committing in
public to a sentence like *"revenue is normally about 1.4 million a day"*.

## Step 2 · Give the number a definition and an owner

We could keep this in a dictionary. We are not going to, because six months from
now somebody will ask *"who owns this and what does it mean"* and a dictionary
has no answer.
""")
n.code("""from dataclasses import dataclass, field

@dataclass(frozen=True)
class MyKPI:
    name: str          # what people call it in Slack
    title: str         # the same thing, in words
    owner: str         # a team that exists, not 'data'
    watches: str       # the table it reads
    means: str         # written FOR the owner, who has never read this code
    sql: str           # returns exactly one row, one column
    unit: str = ''

surge = MyKPI(
    name='surge_coverage_pct',
    title='Share of driver app records carrying a surge value',
    owner='pricing',
    watches=f'{SCHEMA}.bronze_driver_app',
    means='What share of driver app records arrived with a surge value we could '
          'read. This moves when the mobile team renames a field.',
    unit='%',
    sql=f\"\"\"SELECT coalesce((SELECT round(100.0 * rows_out / nullif(rows_in, 0), 2)
                             FROM {SCHEMA}.runs
                             WHERE pipeline = 'p3_bronze_driver_app'
                               AND status = 'success'
                             ORDER BY started_at DESC LIMIT 1), 100)::float\"\"\")

print(surge.name, '·', surge.owner)
print(surge.means)""")
n.md("""
### Three things to notice, and all three are about people

**`owner` is a team, not "data".** A signal nobody owns is a signal nobody acts
on. If you cannot name the team, you have not finished defining the KPI.

**`means` is written for the owner**, who was asleep and has never read this
code. This ends up in the ticket, the page, and the terminal.

**`sql` measures what the pipeline was OFFERED, not what it wrote.** Look at that
query again: it reads `rows_in` and `rows_out` from the run log.

The obvious version, `count(surge) / count(*)` over the landed table, is **100%
by construction** and can never move, because p3 never writes a null surge: a
document it cannot read is held. A KPI that cannot detect the failure it is named
after is worse than none, because it is reassuring.

## Step 3 · Read it, and never let it raise

Reading a number sounds like one line. It is one line and one decision.
""")
n.code("""def read(kpi):
    \"\"\"Run the query. Return the number, or the reason there isn't one.\"\"\"
    try:
        with psycopg.connect(dsn()) as c:
            row = c.execute(kpi.sql).fetchone()
        return {'value': float(row[0]) if row and row[0] is not None else None,
                'error': None}
    except Exception as e:
        # A KPI that cannot be measured is NOT a KPI that is fine.
        return {'value': None, 'error': f'{type(e).__name__}: {e}'}

print(read(surge))""")
n.md("""
> **"could not be measured" and "was measured and it is wrong" are different
> outcomes, and only one of them means somebody typed a bad query.**

Collapse them into `0` and a dropped table looks exactly like a healthy day.

There is a second reason for the `try`, and it cost real time to find. Postgres
aborts **the whole transaction** on any error. Thirteen KPIs sharing one
connection, one of them with a typo, and the other twelve silently return nothing.
One poison KPI must not be able to silence the board.

## Step 4 · Judge it, separately

Reading and judging are different jobs, so they are different functions.
""")
n.code("""def judge(kpi, reading, baseline, spread=None, tolerance=0.0, z_threshold=4.0):
    \"\"\"Compare the number to what it should be. Returns a verdict, never raises.\"\"\"
    if reading['value'] is None:
        return {'breached': False, 'detail': reading['error'] or 'not measured'}

    value = reading['value']

    if spread is None:                       # baseline is A RULE somebody decided
        off = abs(value - baseline)
        return {'breached': off > tolerance, 'z': None,
                'detail': f'{off:.2f} away from the rule of {baseline:g}, '
                          f'{tolerance:g} allowed'}

    z = (value - baseline) / max(spread, 1e-9)     # baseline is FROM HISTORY
    return {'breached': abs(z) > z_threshold, 'z': round(z, 2),
            'detail': f'{z:+.2f} standard deviations from {baseline:,.2f}'}

print('rule    ', judge(surge, read(surge), baseline=100.0, tolerance=1.0))
print('history ', judge(surge, read(surge), baseline=99.0, spread=0.4))""")
n.md("""
### Why they are two functions and not one

Because you will want to read a number without judging it (a chart), and judge a
number you already have (a backfill, a test). Fused together you can do neither,
and every test needs a database.

### The two kinds of normal, and both are correct

| | where the baseline comes from | breached when | example |
|---|---|---|---|
| **from history** | the last N readings of this same number | z-score past a threshold | revenue per day |
| **a rule** | a person decided it | past a tolerance | coverage should be 100% |

You cannot compute a baseline for *"coverage should be 100%"*. There is no
history to average, because it has always been 100% and always should be. That
is a decision, not a statistic, and pretending otherwise is how a slow drift
becomes the new normal.

**And this matters when the agent reads the breach later.** "75% when it is
normally 100%" is ambiguous: is 75 unusual? "75% when a person decided it must be
100%, and anything past 1 is a breach" is not ambiguous. The record has to carry
which kind it is.

## Step 5 · Some numbers are only bad in one direction

`records_held` going **up** is a problem. Going down is a fix. Alerting on a fix
is how people learn to ignore alerts.
""")
n.code("""def apply_direction(direction, value, baseline, breached):
    if not breached:
        return False
    if direction == 'above' and value < baseline:  return False
    if direction == 'below' and value > baseline:  return False
    return True

for d, v in [('below', 75.3), ('below', 100.0), ('above', 75.3)]:
    print(f'  watch {d:5}  value {v:6}  vs 100  ->  '
          f'breach={apply_direction(d, v, 100.0, True)}')""")
n.md("""
## Step 6 · One KPI is a script. Thirteen is a service.

Now we stop writing our own and look at the real catalogue, because the shape is
identical to what we just built, and the interesting part is **which thirteen**.
""")
n.code("""from signal_service.kpis import CATALOGUE, BY_NAME, get

groups = {
    'did the work happen': ('pipelines_failing', 'warehouse_lag_hours', 'records_held'),
    'is the volume right': ('rides_per_day', 'revenue_per_day', 'events_per_ride'),
    'is the shape right':  ('completion_rate', 'cancellation_rate', 'avg_fare'),
    'is anything missing': ('surge_coverage_pct', 'fare_coverage_pct',
                            'zone_coverage_pct', 'settlement_coverage_pct'),
}
for question, names in groups.items():
    print(question.upper())
    for name in names:
        k = BY_NAME[name]
        how = 'a rule' if k.judgement == 'fixed' else 'from history'
        print(f'    {k.name:24} {k.owner:14} {how}')
    print()""")
n.md("""
Four questions, and between them they are what actually goes wrong:

> **did the work happen · is the volume right · is the shape right · is anything missing**

The last group is the interesting one. Those four are the only signals in the
catalogue that can catch today's break, because they are the only ones that ask
*"did everything that should have arrived, arrive"* rather than *"is the number
about right"*.

## Does it catch our break?
""")
n.code("""run('cli.py', 'signals')""")
n.md("""
`surge_coverage_pct` is red. Nothing else moved, because nothing else was
watching for this.

## Step 7 · A breach is a record, not a message

When a signal goes off, something else has to act on it. What we send is the most
consequential design decision in the whole project.

The temptation is a string: *"surge_coverage_pct is 75.33%, was 100%"*. That is
fine for a human and useless to a program: nothing can be branched on, nothing
can be grouped, nothing can be tested.

So the two services share **one typed record**, and it lives in a package that
neither of them owns.
""")
n.code("""from events.contract import SignalBreach

print(inspect.getsource(SignalBreach)[:1600])""")
n.md("""
### Why `events/` is its own package

If the record lived in `signal_service/`, the agent would import from the signal
service, and they would be one program with two folders. The moment the agent
imports the board's code, it can reach past the API into the board's tables, and
nobody notices until a refactor breaks something in a service that "does not
depend on it".

Two services, one contract, neither owns it.

### And it carries how unusual this is
""")
n.code("""from signal_service import evaluate as ev

kpi = get('surge_coverage_pct')
reading, verdict = ev.evaluate(kpi)
breach = ev.to_breach(kpi, reading, verdict)

print(breach.one_line())
print()
print('  baseline kind :', breach.baseline_kind)
print('  tolerance     :', breach.tolerance)
print()
print('  ' + breach.how_unusual())""")
n.md("""
That last sentence is written into the record on purpose. Without it, triage was
dismissing real breaches as ordinary wobble, because "75 when it is normally 100"
does sound like a wobble. **A record that omits how unusual something is invites
the reader to guess.**

## Step 8 · Write it down before you tell anybody

The order of these two lines is the whole reliability story.
""")
n.code("""print(inspect.getsource(__import__('signal_service.emit', fromlist=['x'])._dispatch))""")
n.md("""
```
    record it durably   ->   then ring the doorbell
```

Not the other way round. If the notification fails, or the agent service is
restarting, or the network blinks, the breach is **already in the database** and
`POST /sweep` picks it up later. Cost: some latency. The other order costs you
the incident.

This is the same shape as writing rows before committing a Kafka offset, and it
comes up every time two systems have to agree on something.

## Step 9 · Do not say the same thing every minute

The clock runs every sixty seconds. The break lasts for hours. Without this, one
problem becomes four hundred pages.
""")
n.code("""from signal_service import store
print(inspect.getsource(store.already_open))""")
n.md("""
A **fingerprint** is a stable identity for "this same problem": the KPI plus the
severity. Same fingerprint, still open, seen in the last two hours: record the
reading, say nothing.

## Step 10 · Group before you page

This is the one people skip, and it is why on-call rotations burn out.

A pipeline dies at 3am. `pipelines_failing` goes red. So does
`warehouse_lag_hours`, because nothing ran. So does `rides_per_day`, because gold
is stale. So does `revenue_per_day`, for the same reason.

**Four alerts. One cause.** Send four and the person on call spends their first
ten minutes working out that it is one problem, at 3am, which is exactly when
people are worst at that.
""")
n.code("""from signal_service import correlate

print(inspect.getsource(correlate.group))""")
n.md("""
Four rules, in order:

| | rule | why |
|---|---|---|
| 1 | more than half the board is red | that is the estate, not one number |
| 2 | an upstream signal is red | everything else is downstream of work that did not happen |
| 3 | several signals share an owner | one team, one page |
| 4 | otherwise | one incident each |

Rule 2 is the one worth arguing about. `pipelines_failing`,
`warehouse_lag_hours` and `records_held` describe **whether the work happened**.
Every other KPI describes the result of that work. If the work did not happen,
the results are not independent evidence, they are consequences.
""")
n.code("""from signal_service.kpis import BY_NAME

fake = []
for name in ['pipelines_failing', 'rides_per_day', 'revenue_per_day', 'events_per_ride']:
    k = BY_NAME[name]
    r, v = ev.read(k), None
    v = ev.judge(k, r)
    fake.append(ev.to_breach(k, r, v.model_copy(update={'breached': True})))

incidents = correlate.group(fake, board_size=len(BY_NAME))
print(f'{len(fake)} breaches  ->  {len(incidents)} incident')
print()
print(correlate.explain(incidents))""")
n.md("""
Four in, one out, and the incident names the lead signal and the reason it was
grouped. **The person on call is woken once, and told which of the four to look
at first.**

## Step 11 · The clock

Everything so far is a function. A service is those functions plus something that
calls them on a schedule and never dies.
""")
n.code("""run('-m', 'signal_service.scheduler', '--once', '--no-notify')""")
n.md("""
Three decisions live in that loop, and all three are about what happens on a bad
night:

**It runs OUTSIDE the pipelines.** It cannot block a write and cannot slow a
load. This is the third of three checkpoints, and it is the only one that blocks
nothing:

| checkpoint | where | can it stop you? |
|---|---|---|
| the contract | inside the pipeline, per record | **yes**, it holds the record |
| the invariants | after a write, before committing | **yes**, it rolls back |
| the signal board | outside, on a clock | **no**, and that is the point |

**One cycle never raises.** A cycle that dies takes the clock with it, and a
monitoring system that is down looks exactly like a system with nothing wrong.

**Every reading is saved, breach or not.** Today's readings are tomorrow's
baseline. Throw away the healthy ones and you have no history to be normal
against.

## Step 12 · The API, and why it is over HTTP

The agents could import `signal_service` directly. They talk to it over HTTP
instead.
""")
n.code("""from signal_service.api import app

for route in app.routes:
    if hasattr(route, 'methods') and route.path != '/openapi.json':
        print(f'  {\",\".join(sorted(route.methods)):8} {route.path}')""")
n.md("""
The boundary is the point. Over HTTP the agent can only ask the questions the API
exposes; with an import it can reach into the board's tables and nobody notices
until a refactor breaks a service that "does not depend on it".

## Step 13 · The other checkpoint: invariants

A signal watches a number that is **usually** in a range. An invariant is a
statement that must **never** be false. There is no tolerance, no baseline and no
history: one violation is one bug.
""")
n.code("""run('cli.py', 'invariants')""")
n.md("""
Every invariant is a query that returns **the rows that violate it**. Zero rows
is a pass. That shape is deliberate: when it fails you already have the evidence
in your hand rather than a boolean and a hunt.

> **A signal that fires is a question for a human.**
> **An invariant that fires is a defect.**

---

# What you built, and where it actually lives

Everything in Part 2 is in `signal_service/`, in the same order you built it.

| file | what it is | the step |
|---|---|---|
| `kpis.py` | the thirteen definitions | 2, 6 |
| `evaluate.py` | `read` and `judge`, kept apart | 3, 4, 5 |
| `invariants.py` | the seventeen things that must never be false | 13 |
| `store.py` | readings, breaches, incidents, suppression | 8, 9 |
| `correlate.py` | four breaches into one incident | 10 |
| `emit.py` | record durably, then ring the doorbell | 8 |
| `scheduler.py` | the clock, which never dies | 11 |
| `api.py` | the questions other services may ask | 12 |
| `dashboard.py` | all of it in a browser | |
| `events/contract.py` | the record both services share | 7 |

Every file opens with a docstring explaining the **decision**, not the syntax.

## See all of it at once
""")
n.code("""run('cli.py', 'signals')
run('cli.py', 'incidents')""")
n.md("""
And in a browser, on a second screen, refreshing itself. In a terminal:

```
python cli.py dashboard          # then open http://localhost:8099
```

Click any tile to see the exact query behind it.

> **The dashboard is not the system.** The system is thirteen queries, a baseline
> for each, and a clock. The dashboard is a nice way to read the answer.

---

# What to take away

> ### A number cannot raise an alarm. Only a number plus somebody's written opinion of what normal looks like.
> ### Writing that opinion down, with an owner's name on it, is the work.
> ### Group before you page. One cause producing four alerts is not four problems.
> ### Record it durably, then notify. Never the other way round.

**Next:** the board has found the problem and told nobody what caused it. That is
notebook 2.

## Put it back

Clears the break, the incidents and the artifacts, so this notebook is ready to
run again from the top.
""")
n.code(RESET)
n.save()


# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
#
#  NOTEBOOK 2 · BUILDING THE AGENT SYSTEM
#
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════

n = NB("00-class-2-building-the-agent-system.ipynb")

n.md("""
# Building the agent system

### Everything on this screen is running for real. Nothing here is a slide.

---

In notebook 1 you built the thing that **notices**. It can tell you that
`surge_coverage_pct` is 75.33% when a person decided it must be 100%.

It cannot tell you **why**, and that is where the hours actually go. Somebody has
to open the run log, read the quarantine, read the pipeline source, find the
release, write it up, raise the ticket, and propose the fix.

That work is a **method**. This notebook builds the thing that follows it.

You will build an agent from nothing: a tool, a loop, a typed answer. Then five
of them, then the thing that decides who is asked next, and then the guards that
mean none of it can change a number.
""")
n.code("""import sys; sys.path.insert(0, '..')
import inspect, json, psycopg
from pipelines.lib.config import dsn, SCHEMA
from nb import show, sql, fetch, run

print('connected.')""")
n.md("""
### Start from a clean slate, then break it

We need a real problem for the agents to work on. This resets everything, then
applies the same break as notebook 1: the mobile team moves the surge field.

**Safe to run at any point.** If you get lost later, come back here.
""")
n.code("""run('break_it.py', '--fix')
run('cli.py', 'reset')
run('cli.py', 'run', 'all')""")
n.code("""run('break_it.py')                       # move the surge field
run('cli.py', 'run', 'p3_bronze_driver_app')
run('cli.py', 'run', 'p7_silver_rides')
run('cli.py', 'run', 'p8_gold_daily')
run('cli.py', 'signals')""")
n.md("""
`surge_coverage_pct` is red. Now we build the thing that works out why.
""")

# ── what an agent is ───────────────────────────────────────────────────────
n.md("""
---

# Part 1 · What an agent actually is

Three ideas. That is genuinely all of it, and none of them are hard.

## Idea 1 · A tool is a python function

Not a plugin. Not a connector. A function, with a docstring, and the docstring is
the API: it is the only thing the model reads to decide whether to call it.
""")
n.code("""from langchain.tools import tool

@tool
def rows_in_table(table: str) -> str:
    \"\"\"How many rows are in one table of the warehouse.

    Use this to check whether a table is empty or unexpectedly small.
    \"\"\"
    with psycopg.connect(dsn()) as c:
        n = c.execute(f'SELECT count(*) FROM {SCHEMA}.{table}').fetchone()[0]
    return f'{table} has {n:,} rows'

print('name       ', rows_in_table.name)
print('description', rows_in_table.description.splitlines()[0])
print()
print(rows_in_table.invoke({'table': 'bronze_driver_app'}))""")
n.md("""
> **Write the docstring for the model, not for a colleague.** It is the only
> documentation the model gets. A vague one produces a tool that is never called,
> or worse, called for the wrong thing.

## Idea 2 · An agent is a loop

Give a model some tools and a question. It picks a tool, sees the result, decides
what to do next, and stops when it has an answer.

That loop is the entire idea. Everything else is engineering around it.
""")
n.code("""from langchain.agents import create_agent

little = create_agent(
    model='openai:gpt-5.4-mini',
    tools=[rows_in_table],
    system_prompt='You answer questions about the warehouse using the tools you '
                  'have. Quote the real numbers you were given.',
)

out = little.invoke({'messages': [{'role': 'user', 'content':
    'How many rows are in bronze_driver_app and in silver_rides?'}]})

print(out['messages'][-1].content)""")
n.md("""
### Now look at the loop itself

The answer is not the interesting part. **This** is.
""")
n.code("""for m in out['messages']:
    kind = type(m).__name__.replace('Message', '')
    if getattr(m, 'tool_calls', None):
        for call in m.tool_calls:
            print(f'  {kind:9}  CALL   {call[\"name\"]}({call[\"args\"]})')
    elif kind == 'Tool':
        print(f'  {kind:9}  RESULT {m.content}')
    elif m.content:
        print(f'  {kind:9}  {str(m.content)[:90]}')""")
n.md("""
Read that trace top to bottom. Nobody wrote *"call rows_in_table twice"*. The
model was given a question and a toolbox and worked out the order.

**That is the whole of what an agent is.** A loop, a toolbox, and a stopping
condition.

## Idea 3 · Make it answer in fields, not paragraphs

An agent that replies *"it looks like the driver app data might be incomplete"*
is useless to a program. You cannot branch on it, count it, or put it in a
column.
""")
n.code("""from pydantic import BaseModel, Field

class TableCheck(BaseModel):
    table:     str  = Field(description='the table you looked at')
    row_count: int  = Field(description='how many rows it has')
    is_empty:  bool = Field(description='true if it has no rows at all')
    comment:   str  = Field(description='one sentence a person can read')

typed = create_agent(model='openai:gpt-5.4-mini', tools=[rows_in_table],
                     system_prompt='Check the table you are asked about.',
                     response_format=TableCheck)

v = typed.invoke({'messages': [{'role': 'user', 'content':
    'Check bronze_driver_app.'}]})['structured_response']

print(type(v).__name__)
for k, val in v.model_dump().items():
    print(f'  {k:10} {val}')""")
n.md("""
`v.is_empty` is a real boolean. The supervisor you are about to build branches on
exactly this kind of field.

> **A supervisor cannot make a decision from a paragraph.**

### That is the whole of it

```
    a tool          a python function with a docstring
    an agent        a model, some tools, and a loop
    a verdict       a pydantic model, so a program can use the answer
```

Everything from here is about **what each agent is not allowed to do**.
""")

# ── five agents ────────────────────────────────────────────────────────────
n.md("""
---

# Part 2 · Why five agents, and not one

The obvious design is one agent with every tool. It is also the one that stops
working the first time the problem is unfamiliar.

> **An agent with every tool will use every tool.**

Give one agent SQL *and* file reading and it will read a file, form a theory, and
then go looking for numbers that agree with it. That is not an investigation,
that is confirmation, and it is convincing precisely when it is wrong.

## So each one gets a question and a toolbox, and nothing else

| | agent | the question it answers | what it can touch |
|---|---|---|---|
| 1 | **triage** | is this real, or is it Sunday? | the board only |
| 2 | **data detective** | what is wrong with the rows? | read-only SQL |
| 3 | **lineage detective** | where did it enter? | source and git |
| 4 | **remediation** | what is the smallest fix? | writes artifacts |
| 5 | **verifier** | did it actually work? | runs pipelines and checks |
""")
n.code("""from agent_service.tools.warehouse import READ_TOOLS
from agent_service.tools.lineage import LINEAGE_TOOLS
from agent_service.tools.signals import SIGNAL_TOOLS
from agent_service.tools.publish import PUBLISH_TOOLS
from agent_service.tools.verify import VERIFY_TOOLS

for label, tools in [('1 triage', SIGNAL_TOOLS), ('2 data detective', READ_TOOLS),
                     ('3 lineage detective', LINEAGE_TOOLS),
                     ('4 remediation', PUBLISH_TOOLS), ('5 verifier', VERIFY_TOOLS)]:
    print(f'{label}')
    for t in tools:
        print(f'      {t.name}')
    print()""")
n.md("""
### Read rows two and three again

**The data detective cannot open a file.** So everything it reports came from a
query. It cannot guess from the code and present the guess as evidence.

**The lineage detective cannot query the warehouse.** So it cannot quietly redo
the previous agent's work with worse tools.

> **The method emerges from the constraint, not from a longer prompt that
> everybody hopes the model reads.**

## And triage is cheap, and runs first, on purpose
""")
n.code("""from agent_service.agents import TRIAGE_PROMPT
print(TRIAGE_PROMPT)""")
n.md("""
If triage says the number moved for a boring reason, **nothing else runs**. Four
expensive agents are never woken and nobody is paged for a public holiday.

> **Be willing to say no. A triage agent that says yes to everything has cost you
> the money it was there to save.**

## Watch it say no

Give it a signal that has not actually breached.
""")
n.code("""from agent_service.agents import triage_agent
from signal_service import evaluate as ev
from signal_service.kpis import get

kpi = get('events_per_ride')            # healthy
reading, verdict = ev.evaluate(kpi)
print(f'{kpi.name}: {verdict.value} vs {verdict.baseline}, breached={verdict.breached}')
print()

v = triage_agent().invoke({'messages': [{'role': 'user', 'content':
    f'The signal {kpi.name} is at {verdict.value}{kpi.unit}, normally '
    f'{verdict.baseline}{kpi.unit}. It means: {kpi.means}. Is this real?'
}]})['structured_response']

print('is_real ', v.is_real)
print('reason  ', v.reason)""")
n.md("""
## Every prompt is a method, not a list of answers

This is the difference between a system that works on a problem nobody has seen
and one that recognises the three incidents somebody wrote down.
""")
n.code("""from agent_service.agents import DATA_PROMPT
print(DATA_PROMPT)""")
n.md("""
Read it again. It contains **an order to look in** and **a standard of evidence**.
Nowhere does it say *"if surge is missing, look at app_version"*. There is no
list of incidents anywhere in this project.

Note the paragraph about held records. It is there because the model kept
reporting the wrong app version: the rows that explain this incident **never
landed in any table**, so no query over the warehouse can see them. They are in
quarantine, and the held payload is the only place the truth is written down.

> **The prompt teaches where to look. The tools decide what is reachable. Neither
> one contains the answer.**
""")

# ── the supervisor ─────────────────────────────────────────────────────────
n.md("""
---

# Part 3 · The thing that holds the plan

Five specialists is not a system. Something has to decide who is asked next and
carry each answer forward.

The documented LangChain pattern for this is **subagents as tools**: each
specialist is an agent, wrapped with `@tool`, and one main agent holds all five.
The older `create_supervisor` helper is no longer maintained; this replaced it.
""")
n.code("""from agent_service import agents

src = inspect.getsource(agents.build_subagent_tools)
print(src[src.index('    @tool(\"triage\"'):src.index('    @tool(\"investigate_lineage\"')])""")
n.md("""
Each wrapper does three things: run the specialist, take its typed verdict, hand
back JSON the supervisor can read.

The specialists are **stateless**. Each starts in a clean context every time,
which is what stops the fifth agent inheriting four agents' worth of noise.

## And the supervisor holds the plan and nothing else
""")
n.code("""from agent_service.supervisor import SUPERVISOR_PROMPT
print(SUPERVISOR_PROMPT)""")
n.md("""
### What it does not do

It does not investigate. It decides who is asked next, carries each answer
forward, and stops when the evidence is enough.

**It stops early too.** That is the `if triage says the breach is not real, STOP`
rule, and it is the difference between a system that costs a few cents a night
and one that costs a few hundred.
""")

# ── guards ─────────────────────────────────────────────────────────────────
n.md("""
---

# Part 4 · What stops it doing something stupid

This is the part that makes the difference between a demo and something you would
actually run against a warehouse.

## The rule

> **Whether an agent meant well is a judgement.**
> **Whether it CAN write is a fact.**

Every boundary in this system is a fact.

## 1 · The read-only tool cannot write, and not because we asked
""")
n.code("""from agent_service.tools.warehouse import run_sql

# @tool wraps the function in a StructuredTool, so the original is .func
print(inspect.getsource(run_sql.func))""")
n.md("""
There are two guards there and only one of them counts.

The regex is a **courtesy**: it returns a clear message instead of a database
error, and it stops an honest mistake early. If it were the only guard, this
system would be one clever string away from a deleted table.

`conn.read_only = True` is the one that counts. **Postgres** refuses the write.
Not our code, not our regex, not the model's good intentions.
""")
n.code("""print(run_sql.invoke({'query': 'DELETE FROM teach.silver_rides'}))
print()
print(run_sql.invoke({'query': 'UPDATE teach.gold_daily SET revenue = 0'}))""")
n.md("""
## 2 · A code change happens in an isolated checkout, and never on your branch
""")
n.code("""from agent_service.tools.repo import WRITABLE, pushing_allowed
print('the agent may only propose changes to:')
for pattern in WRITABLE:
    print(f'    {pattern}')
print()
print('pushing allowed right now:', pushing_allowed())""")
n.md("""
Two more facts underneath that list:

**It works in a `git worktree`**, a separate checkout of the same repository. Two
investigations running at once cannot see each other's files. Without it, the
second one commits the first one's changes, reports success, and the branch does
not contain the fix.

**It never merges.** It opens a branch and a pull request. A human decides.

## 3 · A change that would not compile never reaches a human
""")
n.code("""from agent_service.tools import repo

src = inspect.getsource(repo.propose)
i = src.index('    # Whether a change is right is a judgement')
print(src[i:src.index('    out.diff =')])""")
n.md("""
## 4 · Anything that would touch data stops and waits for a person
""")
n.code("""from agent_service.tools.publish import request_db_change, GATED
print('tools that pause for a human:', GATED)
print()
print(request_db_change.invoke({
    'breach_id': 'BRCDEMO',
    'summary': 'backfill the missing surge values',
    'rationale': 'the pricing report is wrong until these rows have a value',
    'statement': 'UPDATE teach.silver_rides SET surge = 1.0 WHERE surge IS NULL',
    'rows_affected_estimate': 'about 9,900 rows, counted with a SELECT first',
    'reversible': 'yes: rebuild silver from bronze, which is untouched',
}))""")
n.md("""
**It did not run that statement, and nothing in this system will.** The tool
records what was proposed, what it would touch and how to reverse it, and stops.

That is `HumanInTheLoopMiddleware`, and the investigation genuinely pauses:
`waiting_for_human` comes back true, and a person answers it with
`POST /investigations/{id}/resume`. **Rejecting is a real outcome**, and the note
goes back to the agent. That is the difference between a human gate and a rubber
stamp.

## The four boundaries, and how each is enforced

| boundary | enforced by | not by |
|---|---|---|
| cannot write to the warehouse | Postgres, `read_only = True` | a prompt |
| cannot edit files outside a whitelist | a path check, in an isolated checkout | a prompt |
| cannot merge anything | opening a pull request instead | a prompt |
| cannot touch data | an interrupt that pauses the run | a prompt |

And every one of them has a test that tries to break it.
""")
n.code("""run('-m', 'pytest', 'tests/test_guards.py', '-q', '--no-header', '--color=no')""")

# ── run it ─────────────────────────────────────────────────────────────────
n.md("""
---

# Part 5 · Running it, and watching every step

Now the whole thing, on the break we made at the top. Five agents, one incident,
no human.

**Run this in a terminal, not in this cell.** The notebook captures the output
and prints it when it is finished; the terminal streams it, so the room watches
the method rather than reading a conclusion.

```
python cli.py investigate surge_coverage_pct
```

You will see, live:

```
  1 TRIAGE              is this real?
      get_signal_board()
      get_kpi_definition(name=surge_coverage_pct)
      -> triage answered      is_real True   severity high

  2 DATA DETECTIVE      what is wrong with the rows?
      recent_runs(limit=10)
      quarantine_sample(pipeline=p3_bronze_driver_app, limit=5)
      -> data_detective answered

  3 LINEAGE DETECTIVE   where did it enter?
      read_source(path=pipelines/p3_bronze_driver_app.py)
      -> lineage_detective answered

  4 REMEDIATION         what is the smallest fix?
      propose_code_change(...)     -> a real pull request
      raise_ticket(...)
      publish_incident_page(...)

  5 VERIFIER            did it actually work?
      check_file_on_disk(...)
      -> resolved False, change_applied False
```

If you would rather run it here, this cell does the same thing and prints the
whole trace at the end.
""")
n.code("""run('cli.py', 'investigate', 'surge_coverage_pct')""")
n.md("""
## What just happened, in order

1. **Triage** read the board and said it was real, and said why
2. **The data detective** queried, found the held records, and quoted the numbers
3. **The lineage detective** read `p3_bronze_driver_app.py` and found the contract
4. **Remediation** opened a branch and a pull request, raised a ticket, and wrote
   the Confluence page
5. **The verifier** checked the file on disk and said plainly: **not applied, still
   on a branch, nothing is fixed**

**Nobody typed anything after the break.** And there is no list of incidents
anywhere in this project: the agents were given a method and a toolbox, which is
why a problem nobody has seen before is worked exactly like this one.

## What it produced, and what it did not

Everything the investigation leaves behind is **for a person to decide on**.
""")
n.code("""sql(\"\"\"
    SELECT ticket_id, kind, severity, left(title, 60) AS title
    FROM oncall.tickets ORDER BY raised_at DESC LIMIT 5
\"\"\", 'tickets raised')

sql(\"\"\"
    SELECT request_id, kind, status, coalesce(pr_url, '(no remote)') AS pull_request
    FROM oncall.change_requests ORDER BY created_at DESC LIMIT 5
\"\"\", 'code changes proposed · none of them merged')""")
n.md("""
The verifier said `resolved: False`, and it is right. **A proposal waiting for a
human has fixed nothing**, and an agent that reports otherwise is worse than no
agent, because the incident looks handled and is not.

---

# What to take away

> ### An agent is a loop, a toolbox, and a stopping condition. Nothing more.
> ### Five narrow agents beat one wide one, because the constraint enforces the method.
> ### Make it answer in fields, because a supervisor cannot branch on a paragraph.
> ### If a boundary matters, make it something the system CANNOT do, not something you asked it not to.

## Put it back

Clears the break, the incidents, the tickets and the agent's branches, so both
notebooks are ready to run again from the top.
""")
n.code(RESET)
n.md("""
---

### Where to go next

| | |
|---|---|
| notebooks **1 to 12** | build the warehouse yourself, one source at a time |
| notebooks **13 to 18** | the same two services, in more depth |
| notebook **19** | a guided tour of the source, in dependency order |
| `docs/` | twelve documents, one per idea |

Every file in the project opens with a docstring explaining the **decision**
rather than the syntax. Those docstrings are the real material.
""")
n.save()
