"""Generate the notebooks for the two services.

Same rule as the course notebooks: the code lives in runnable cells, not in a
description of code that lives somewhere else. Run a cell, see the output,
explain it.
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
        print(f"  {self.filename:44} {len(self.cells):>3} cells ({c} code)")


HEAD = """import sys; sys.path.insert(0, '..')
from nb import show, sql, fetch, run          # the same helpers as notebooks 1 to 12"""


# ═══════════════════════════════════════════════════════════════════════════
n = NB("13-kpis-and-signals.ipynb")
n.md("""
# 13 · KPIs, signals, and the difference

You have a warehouse. Eight pipelines fill it and they all say `ok`.

**That is not the same as the numbers being right**, and notebook 9 proved it:
a field moved upstream, nothing failed, no row count changed, and a number
quietly stopped being true.

So somebody has to watch the numbers. This notebook is about what to watch, and
the distinction that makes the difference between alerting that works and
alerting everybody ignores.

![](img/oncall-2-kpi-vs-signal.png)
""")
n.code(HEAD)
n.md("""
---

## The distinction, in one cell

People use these words interchangeably and then cannot work out why their
alerting is useless.
""")
n.code("""import psycopg
from pipelines.lib.config import dsn, SCHEMA

# A KPI: a number with a definition. That is all it is.
with psycopg.connect(dsn()) as c:
    revenue = float(c.execute(
        f'SELECT revenue FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1'
    ).fetchone()[0])          # NUMERIC comes back as Decimal, which will not
                             # subtract from a float. Cast at the boundary.

print(f'revenue yesterday: {revenue:,.2f}')
print()
print('Is that good or bad?')""")
n.md("""
**You cannot answer that**, and neither can any alerting system, because a
number on its own has no opinion about itself.

Now give it a baseline.
""")
n.code("""import statistics

with psycopg.connect(dsn()) as c:
    history = [float(r[0]) for r in c.execute(
        f'SELECT revenue FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1')]

baseline = statistics.mean(history)
spread   = statistics.pstdev(history)

print(f'yesterday      {revenue:>14,.2f}')
print(f'normally       {baseline:>14,.2f}   over {len(history)} days')
print(f'usual spread   {spread:>14,.2f}')
print()
print(f'z score        {(revenue - baseline) / max(spread, 0.01):>14.2f}')""")
n.md("""
> **A KPI is a number with a definition and an owner. It can never be wrong and
> it can never fire.**
>
> **A signal is a KPI plus a baseline plus a tolerance. That is the thing that
> can breach.**

The baseline is the part nobody wants to write, and it is the only part that
turns a number into something you can act on.

---

## Two kinds of baseline, and both are correct

Some numbers **have a history**. Some have **a rule**.
""")
n.code("""with psycopg.connect(dsn()) as c:
    held = c.execute(f'SELECT count(*) FROM {SCHEMA}.quarantine').fetchone()[0]

print(f'records held: {held:,}')
print()
print('What is the "normal" number of held records?')
print('It is not an average of the last seven days. It is zero.')
print('Zero held records is not a statistic, it is a rule somebody decided.')""")
n.md("""
| | computed from history | decided by a person |
|---|---|---|
| example | `rides_per_day`, `revenue_per_day` | `records_held`, `pipelines_failing` |
| baseline | the mean of previous readings | a number in the code |
| breach when | it is N spreads from normal | it is anything other than the rule |
| catches | a feed that stopped | a contract refusing things |
| gets wrong | a genuinely quiet Sunday | nothing, but it needs a person to set it |

A system that only has the first kind cannot express "this should be zero". A
system that only has the second cannot express "quieter than a normal Tuesday".

---

## Writing one down properly

Four fields, and the fourth is the one people skip.
""")
n.code("""from signal_service.kpis import KPI, CATALOGUE, get

k = get('surge_coverage_pct')

print(f'name       {k.name}')
print(f'title      {k.title}')
print(f'owner      {k.owner}          <- a team that exists')
print(f'watches    {k.watches}')
print(f'unit       {k.unit!r}')
print(f'judged by  {k.judgement}, baseline {k.baseline}, tolerance {k.tolerance}')
print(f'\\nmeans:\\n  {k.means}')""")
n.md("""
### The owner is the field that decides whether any of this was worth building

A breach with no name attached is a number on a screen that everybody assumes
somebody else is looking at.

`means` is written for that owner, who will read it at 3am having never seen
this code. Not for you, and not for the model.

### And read the tolerance

`surge_coverage_pct` has a baseline of 100 and a tolerance of **1**, not 5.

That is deliberate. In normal operation this KPI is exactly 100.0, because the
pipeline **holds** a record it cannot read a surge value from rather than
writing a null. So any drop at all is a real change, and a generous tolerance
would let a release move a field and stay under the bar until it had affected
weeks of rides.

---

## The catalogue

Thirteen KPIs, in four groups, because between them they answer the four
questions that actually go wrong.
""")
n.code("""groups = {
    'did the work happen':  ('pipelines_failing', 'warehouse_lag_hours', 'records_held'),
    'is the volume right':  ('rides_per_day', 'revenue_per_day', 'events_per_ride'),
    'is the shape right':   ('completion_rate', 'cancellation_rate', 'avg_fare'),
    'is anything missing':  ('surge_coverage_pct', 'fare_coverage_pct',
                             'zone_coverage_pct', 'settlement_coverage_pct'),
}
for question, names in groups.items():
    print(f'\\n{question.upper()}')
    for name in names:
        k = get(name)
        how = 'a rule' if k.judgement == 'fixed' else 'history'
        print(f'   {k.name:26} {k.owner:14} {how:8} {k.severity}')""")
n.md("""
### The one that is not about data at all

`pipelines_failing` reads `teach.runs`. It does not look at a single row of
business data. It asks **whether the work happened.**

**A pipeline that never ran leaves perfectly valid rows behind.** Every value is
correct. Every value is old. No check that looks only at values will ever
notice, which is why this one exists.

---

## Measuring, and judging, are different steps

They fail for different reasons, so keeping them apart lets you tell the
difference between "the KPI could not be measured" and "the KPI was measured and
it is wrong". Only the second is worth waking somebody for.
""")
n.code("""from signal_service import evaluate as ev

reading, verdict = ev.evaluate(get('surge_coverage_pct'))

print('READING   (running the query)')
print(f'   value    {reading.value}')
print(f'   measured {reading.measured}')
print(f'   error    {reading.error}')
print()
print('VERDICT   (comparing it to normal)')
print(f'   baseline {verdict.baseline}')
print(f'   breached {verdict.breached}')
print(f'   detail   {verdict.detail}')""")
n.md("""
## Now the whole board
""")
n.code("""rows = ev.evaluate_all()

print(f'{"":8} {"kpi":26} {"value":>13} {"normally":>13}   detail')
print('-' * 100)
for kpi, reading, v in rows:
    if not reading.measured:
        print(f'{"----":8} {kpi.name:26} {"not measurable":>13}   {reading.error[:40]}')
        continue
    flag = 'BREACH' if v.breached else '  ok  '
    print(f'{flag:8} {kpi.name:26} {v.value:>13,.2f} {v.baseline:>13,.2f}   {v.detail[:44]}')""")
n.md("""
---

## One bug worth showing, because it will happen to you

The first version of `evaluate_all` shared one database connection across all
thirteen KPIs, which is right: thirteen connections every minute forever is
waste.

But a failing query **aborts the whole transaction in Postgres**, and every KPI
after it died with `current transaction is aborted`. One bad query silenced
twelve good numbers.
""")
n.code("""import inspect
src = inspect.getsource(ev.read)
start = src.index('except Exception as e:')
print(src[start:start + 900])""")
n.md("""
`conn.rollback()` is the whole fix. **One poison KPI must not block the rest**,
which is the same rule as one poison message on a topic.

## What you learned

- **A KPI cannot fire. A signal can.** The difference is a baseline somebody wrote
- Two kinds of baseline: **computed from history**, and **decided by a person**
- The **owner** is the field that makes a breach somebody's rather than nobody's
- A tolerance should reflect **what the number does when nothing is wrong**
- **Measuring and judging are separate steps**, because they fail differently
- One failing query can take out the other twelve. Roll back and carry on
""")
n.save()


# ═══════════════════════════════════════════════════════════════════════════
n = NB("14-the-signal-service.ipynb")
n.md("""
# 14 · Turning a board into a service

Notebook 13 built a catalogue and evaluated it by typing a command. That is
fine for a laptop and useless at 3am.

A service is three things the command is not: **it answers questions over HTTP,
it runs on a clock, and it keeps what it saw.** This notebook builds all three
and runs them.

![](img/oncall-1-two-services.png)
""")
n.code(HEAD)
n.md("""
---

## Part 1 · Keeping what it saw

A baseline computed from `gold_daily` only works for KPIs that have history in
the warehouse. `records_held` does not: there is no table of what quarantine
used to be.

So the service keeps its own readings, in its own schema.
""")
n.code("""from signal_service import store

store.setup()

import psycopg
from pipelines.lib.config import dsn

with psycopg.connect(dsn()) as c:
    rows = c.execute(\"\"\"
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'oncall' ORDER BY table_name
    \"\"\").fetchall()
print('the oncall schema:')
for (t,) in rows:
    print('   ', t)""")
n.md("""
### Read the schema name

The service **reads** `teach` and **writes** `oncall`. It never writes a row
into the warehouse.

That is not tidiness. It is the property that lets you drop the entire
observability layer and rebuild it without touching a single number anybody
reports on. If the signal board could write to `teach`, then every incident
review would have to start with "did the monitoring do this?"

---

## Part 2 · The API

An HTTP surface over the catalogue, so anything can ask without importing
python or knowing which database the numbers live in.
""")
n.code("""from signal_service.api import app

for route in app.routes:
    if hasattr(route, 'methods') and route.path != '/openapi.json':
        methods = ','.join(sorted(route.methods - {'HEAD', 'OPTIONS'}))
        print(f'   {methods:5} {route.path}')""")
n.md("""
### One design decision worth arguing about in class

Look at which of those is a `POST`.

**`GET /signals` measures and tells you. It records nothing and wakes nobody.**
**`POST /evaluate` is the one that can start an investigation.**

A dashboard refreshing every ten seconds must not be able to page somebody. If
measuring had side effects, the act of looking at the board would generate
incidents, and you would have built a machine that alerts on being observed.

## Start it and ask it something

The service is already running in Docker. If it is not, this cell tells you.
""")
n.code("""import httpx, os

SIGNAL = os.environ.get('SIGNAL_SERVICE_URL', 'http://localhost:8091')

try:
    health = httpx.get(f'{SIGNAL}/health', timeout=10).json()
    print('health:', health)
except Exception as e:
    print(f'not running: {type(e).__name__}')
    print('start it with:  docker compose -f platform/docker-compose.yml up -d signal-api')
    print('or locally:     uvicorn signal_service.api:app --port 8091')""")
n.code("""kpis = httpx.get(f'{SIGNAL}/kpis', timeout=30).json()
print(f'{len(kpis)} kpis\\n')
print(f'  {"name":26} {"owner":15} {"judged by":10} severity')
for k in kpis:
    print(f'  {k["name"]:26} {k["owner"]:15} {k["judgement"]:10} {k["severity"]}')""")
n.md("""
## The query is not a secret
""")
n.code("""d = httpx.get(f'{SIGNAL}/kpis/surge_coverage_pct', timeout=30).json()
print(d['means'], '\\n')
print('SQL:', d['sql'])""")
n.md("""
Anybody arguing with a number deserves to see exactly how it was produced.
Hiding the query is how a metric becomes folklore.

## Evaluate everything, over HTTP
""")
n.code("""data = httpx.get(f'{SIGNAL}/signals', timeout=120).json()
print(f'{data["total"]} evaluated, {data["breached"]} breached, '
      f'{data["unmeasured"]} not measurable\\n')
for s in data['signals']:
    flag = 'BREACH' if s['breached'] else '  ok  '
    value = '--' if s['value'] is None else f'{s["value"]:,.2f}'
    print(f'  {flag}  {s["kpi"]:26} {value:>13}{s["unit"]:<7} {s["owner"]}')""")
n.md("""
---

## Part 3 · The clock

This is the whole difference between a board you run and a board that runs.
""")
n.code("""import inspect
from signal_service import scheduler

print(inspect.getsource(scheduler.cycle))""")
n.md("""
### Three decisions in thirty lines

**Why a loop and not cron.** Cron is fine, and for many teams it is the right
answer. A loop is used here because it holds one thing cron cannot: the memory
of what it has already raised. Suppression, backoff and "this is the fourth
time tonight" all need state that survives between cycles, and a process that
exits every minute has none.

**Why it never dies.** Every cycle is wrapped. If the warehouse is down it says
so, waits, and tries again. A scheduler that stops on the first error is a
scheduler that was running yesterday.

**Why it is not the API.** The API answers questions; the clock asks them.
Keeping them apart means a dashboard hammering `/signals` cannot slow the clock,
and a slow clock cannot make the dashboard time out.

## Run one cycle
""")
n.code("""run('-m', 'signal_service.scheduler', '--once', '--no-notify')""")
n.md("""
---

## Part 4 · Not raising the same thing 288 times

The board runs every minute. A broken pipeline stays broken for hours.

Without something, one incident becomes several hundred investigations, and the
thing you built to help becomes the outage.
""")
n.code("""from signal_service.kpis import get
from signal_service import evaluate as ev

kpi = get('records_held')
reading, verdict = ev.evaluate(kpi)
breach = ev.to_breach(kpi, reading, verdict)

print('breach id   ', breach.breach_id, '  <- unique every time')
print('fingerprint ', breach.fingerprint(), '  <- the same for the same problem')
print()
again = ev.to_breach(kpi, *ev.evaluate(kpi))
print('a second evaluation of the same problem:')
print('   different id:          ', again.breach_id != breach.breach_id)
print('   identical fingerprint: ', again.fingerprint() == breach.fingerprint())""")
n.md("""
The fingerprint is the KPI, the direction and the value. **The same KPI breaching
the same way is the same incident**, and the store refuses to open a second one
within a window.

---

## Part 5 · The record, and the doorbell

Two things happen when a signal breaches, and they are not the same.
""")
n.code("""print(inspect.getsource(__import__('signal_service.emit', fromlist=['emit']).emit))""")
n.md("""
### Read the order

**RECORD** the breach to `oncall.breaches`. Durable. This is the truth.
**NOTIFY** the agent service over HTTP. A doorbell. This is a courtesy.

Do them in that order and a failed notification costs **latency**, not an
incident: the record is on disk and the agent picks it up on its next sweep. Do
it the other way round and a restart at the wrong second means a breach nobody
ever hears about, with no error anywhere.

That is the same argument as writing rows before committing a Kafka offset, and
it turns up every time two systems have to agree on something.

---

## What you learned

- A service is **an API, a clock, and a memory**. The command was none of those
- The board **reads the warehouse and writes its own schema**, never the reverse
- **`GET` must not have side effects.** A dashboard cannot be allowed to page people
- The clock exists so nobody has to type, and it **never dies on an error**
- **Deduplicate by fingerprint**, or one broken pipeline becomes 288 incidents
- **Write the record, then ring the doorbell.** Never the other way round
""")
n.save()


# ═══════════════════════════════════════════════════════════════════════════
n = NB("15-one-agent.ipynb")
n.md("""
# 15 · One agent, built from nothing

The board can now tell you that a number moved. Somebody still has to find out
why, and that somebody is asleep.

This notebook builds **one** agent, in cells, and gets it to do a real piece of
work against the real warehouse. Notebook 16 turns it into five.

No experience with agents needed. We build up one word at a time.
""")
n.code("""import sys; sys.path.insert(0, '..')
import os
from pipelines.lib.config import dsn, SCHEMA      # loads .env, so the key is set

print('model :', os.environ.get('ONCALL_MODEL', 'openai:gpt-5.4-mini'))
print('key   :', 'present' if os.environ.get('OPENAI_API_KEY') else 'MISSING')""")
n.md("""
---

## Word 1 · a **tool**

A tool is a python function the model is allowed to call.

That is the whole idea. The model cannot query your database; it can ask you to,
by name, with arguments, and read what you hand back.
""")
n.code("""from langchain.tools import tool

@tool
def count_rows(table: str) -> str:
    \"\"\"Count the rows in one warehouse table.\"\"\"
    import psycopg
    with psycopg.connect(dsn()) as c:
        c.read_only = True
        n = c.execute(f'SELECT count(*) FROM {SCHEMA}.{table}').fetchone()[0]
    return f'{table} has {n:,} rows'

print('name        :', count_rows.name)
print('description :', count_rows.description)
print('arguments   :', count_rows.args)
print()
print(count_rows.invoke({'table': 'bronze_driver_app'}))""")
n.md("""
### The docstring is not documentation, it is the interface

The model chooses tools by reading that description. A vague docstring produces
an agent that picks the wrong tool and then explains confidently why it was
right.

Notice `c.read_only = True`. Hold that thought.

---

## Word 2 · an **agent**

A model, some tools, and a loop: call the model, run any tool it asked for, give
it the result, repeat until it stops asking.

`create_agent` is that loop.
""")
n.code("""from langchain.agents import create_agent

agent = create_agent(
    model='openai:gpt-5.4-mini',
    tools=[count_rows],
    system_prompt='You answer questions about a data warehouse using the tools you have.',
)

result = agent.invoke({'messages': [
    {'role': 'user', 'content': 'How many rows are in bronze_driver_app and silver_rides?'}
]})

for m in result['messages']:
    kind = type(m).__name__.replace('Message', '')
    if getattr(m, 'tool_calls', None):
        for call in m.tool_calls:
            print(f'  {kind:10} calls {call["name"]}({call["args"]})')
    elif m.content:
        print(f'  {kind:10} {str(m.content)[:150]}')""")
n.md("""
**Read the trace.** The model decided to call the tool twice, we ran it twice,
and it wrote the answer from what came back. Nobody wrote an if statement.

---

## Word 3 · **structured output**

Prose is readable and unusable. If another program has to act on the answer, it
needs fields, not a paragraph.
""")
n.code("""from pydantic import BaseModel, Field

class TableVerdict(BaseModel):
    table: str
    rows: int
    looks_empty: bool = Field(description="true if the table has no rows")
    comment: str

typed = create_agent(
    model='openai:gpt-5.4-mini',
    tools=[count_rows],
    system_prompt='You answer questions about a data warehouse.',
    response_format=TableVerdict,
)

out = typed.invoke({'messages': [
    {'role': 'user', 'content': 'Check bronze_driver_app'}]})

v = out['structured_response']
print(type(v).__name__, '\\n')
print('  table      ', v.table)
print('  rows       ', v.rows)
print('  looks_empty', v.looks_empty, '  <- a bool you can branch on')
print('  comment    ', v.comment)""")
n.md("""
`v.looks_empty` is a real python boolean. **That is what lets a supervisor stop
early**, and it is why every agent in this project returns a schema.

---

## Word 4 · the **guard**

The agent above could have been asked to run any SQL. It was not, because the
tool only counts rows. But the moment you give it a general query tool, the
question becomes: what stops it writing?
""")
n.code("""from agent_service.tools.warehouse import run_sql

print(run_sql.invoke({'query': 'SELECT count(*) FROM teach.silver_rides'}))
print()
print(run_sql.invoke({'query': 'DELETE FROM teach.silver_rides'}))
print()
print(run_sql.invoke({'query': 'SELECT 1; DROP TABLE teach.gold_daily'}))""")
n.md("""
### Two guards, and only one of them is about trust

**The syntactic guard** rejects anything that is not a single SELECT. Easy to
read, easy to explain, and easy to fool: it is a string check.

**The read only transaction** is the one that matters:

```python
conn.read_only = True
```

Postgres itself refuses the write, no matter what the model asked for or how the
query was spelled. Say the distinction out loud, because it generalises:

> **Whether an agent meant well is a judgement. Whether it CAN write is a fact.**

Build on facts. Every rule you enforce only in a system prompt is a rule you are
hoping about.

---

## Now a real one: the data detective

Same three ideas, pointed at a real breach.
""")
n.code("""from agent_service.tools.warehouse import READ_TOOLS

for t in READ_TOOLS:
    print(f'  {t.name:20} {t.description.splitlines()[0][:70]}')""")
n.code("""from agent_service.agents import data_agent, DATA_PROMPT

print(DATA_PROMPT)""")
n.md("""
### Read that prompt again

It contains a **method**, not answers. Look at the warehouse, in this order,
and quote real numbers. Nowhere does it say "if surge is missing, look at app
versions".

That matters more than anything else in this notebook. An agent given a list of
known problems handles known problems. An agent given a method handles the one
nobody has seen.

## Run it against something that is actually broken
""")
n.code("""from signal_service import evaluate as ev
from signal_service.kpis import get

kpi = get('surge_coverage_pct')
reading, verdict = ev.evaluate(kpi)
breach = ev.to_breach(kpi, reading, verdict)
print(breach.one_line())
print()
print('breached:', verdict.breached)
if not verdict.breached:
    print('\\nNothing is broken. Break it first, in a terminal:')
    print('   python break_it.py && python cli.py run all')""")
n.code("""agent = data_agent()

out = agent.invoke({'messages': [{'role': 'user', 'content':
    f'{breach.one_line()}\\n\\nThe KPI means: {breach.means}\\n\\n'
    f'What is wrong with the data?'}]})

calls = [c['name'] for m in out['messages'] for c in (getattr(m, 'tool_calls', None) or [])]
print('tools it chose to use:', calls, '\\n')

v = out['structured_response']
print('FINDING  ', v.finding)
print('\\nEVIDENCE\\n', v.evidence)
print('\\nSCALE    ', v.scale)
print('CONFIDENCE', v.confidence)""")
n.md("""
**Nobody told it to split by app version.** The prompt said "split it, by
whatever column exists", and it worked out which column mattered by looking.

---

## What you learned

- A **tool** is a function the model may call. Its docstring is the interface
- An **agent** is a model, tools, and a loop. `create_agent` is that loop
- **Structured output** turns an answer into fields another program can branch on
- **The prompt is a request. The read only connection is a constraint.** Build on
  constraints
- Give an agent **a method, not a list of known problems**
""")
n.save()


# ═══════════════════════════════════════════════════════════════════════════
n = NB("16-five-agents-and-a-supervisor.ipynb")
n.md("""
# 16 · Five agents, and the one that holds the plan

One agent found what was wrong with the rows. It could not tell you **where the
wrong value came from**, because it cannot read code, and that was on purpose.

This notebook is about why, and about the shape that turns five narrow
specialists into one investigation.

![](img/oncall-3-five-agents.png)
""")
n.code("""import sys; sys.path.insert(0, '..')
from nb import run                            # prints a command exactly as a terminal would
from pipelines.lib.config import dsn, SCHEMA""")
n.md("""
---

## Why five and not one

The obvious design is one agent with every tool. It is also the one that stops
working the moment the problem is unfamiliar.

> **An agent with every tool will use every tool.**

Give one agent SQL and file reading and it will read a file, form a theory, and
then go looking for numbers that agree with it. Split them and that becomes
impossible:
""")
n.code("""from agent_service.agents import (triage_agent, data_agent, lineage_agent,
                                  remediation_agent, verifier_agent)
from agent_service.tools.warehouse import READ_TOOLS
from agent_service.tools.lineage import LINEAGE_TOOLS
from agent_service.tools.signals import SIGNAL_TOOLS
from agent_service.tools.publish import PUBLISH_TOOLS

print()
print('  triage             ', [t.name for t in SIGNAL_TOOLS])
print()
print('  data detective     ', [t.name for t in READ_TOOLS])
print()
print('  lineage detective  ', [t.name for t in LINEAGE_TOOLS])
print()
print('  remediation        ', [t.name for t in PUBLISH_TOOLS])""")
n.md("""
### Read the two middle rows

**The data detective cannot open a file.** So everything it reports came from a
query. It cannot guess from the code and present the guess as evidence.

**The lineage detective cannot query the warehouse.** So it cannot quietly redo
the previous agent's work with worse tools.

Narrow the toolbox and the method emerges from the constraint, rather than from
a longer prompt that everybody hopes the model reads.

---

## The other reason: cost

Triage is the cheapest agent and it runs first, on purpose.
""")
n.code("""from agent_service.agents import TRIAGE_PROMPT
print(TRIAGE_PROMPT)""")
n.md("""
> **Be willing to say no. A triage agent that says yes to everything has cost
> you the money it was there to save.**

If triage says the number moved for a boring reason, nothing else runs. Four
expensive agents are never woken, and nobody is paged for a public holiday.

## Watch it say no

Give it something that has not actually breached.
""")
n.code("""from signal_service import evaluate as ev
from signal_service.kpis import get

kpi = get('events_per_ride')            # healthy: 4.77 against a baseline of 4.7
reading, verdict = ev.evaluate(kpi)
print(f'{kpi.name}: {verdict.value} vs {verdict.baseline}, breached={verdict.breached}\\n')

out = triage_agent().invoke({'messages': [{'role': 'user', 'content':
    f'The signal {kpi.name} is at {verdict.value}{kpi.unit}, normally '
    f'{verdict.baseline}{kpi.unit}. It means: {kpi.means}\\n\\nIs this real?'}]})

v = out['structured_response']
print('is_real  ', v.is_real)
print('severity ', v.severity)
print('reason   ', v.reason)""")
n.md("""
---

## The pattern: subagents as tools

Five specialists is not a system. Something has to decide who is asked next and
carry each answer forward.

The documented LangChain multi agent shape for this is **subagents as tools**:
each specialist is an agent, wrapped with `@tool`, and one main agent holds all
five.

The older `create_supervisor` helper is no longer maintained; this is what
replaced it.
""")
n.code("""import inspect
from agent_service import agents

src = inspect.getsource(agents.build_subagent_tools)
print(src[src.index('    @tool("triage"'):src.index('    @tool("investigate_lineage"')])""")
n.md("""
Each wrapper does three things: run the specialist, take its typed verdict, and
hand back JSON the supervisor can read. The specialists are **stateless** and
start in a clean context every time, which is what stops the fifth agent
inheriting four agents' worth of noise.

## The supervisor holds the plan and nothing else
""")
n.code("""from agent_service.supervisor import SUPERVISOR_PROMPT
print(SUPERVISOR_PROMPT)""")
n.md("""
### What the supervisor does not do

It does not investigate. It decides who is asked next, carries each answer
forward, and stops when the evidence is enough.

**It stops early too.** That is the `if triage says the breach is not real,
STOP` rule, and it is the difference between a system that costs a few cents a
night and one that costs a few hundred.

---

## Run the whole thing

Five agents, one breach, no human. This takes a minute or two.
""")
n.md("""
First, break something, so there is a real thing to investigate. This is the
same release shaped break as notebook 9: the driver app moves a field, nothing
errors, and a value the pricing team depends on quietly stops arriving.
""")
n.code("""run('break_it.py')
run('cli.py', 'run', 'p7_silver_rides')
run('cli.py', 'run', 'p8_gold_daily')""")
n.md("""
Now measure it. `to_breach` turns a reading into the record the agents receive,
and `correlate.group` turns one or more breaches into the **incident** that is
actually investigated. That distinction matters: a pipeline dying breaches six
signals, and nobody wants six investigations of one cause.
""")
n.code("""from agent_service.supervisor import investigate
from signal_service import correlate, store
from signal_service.kpis import BY_NAME

kpi = get('surge_coverage_pct')
reading, verdict = ev.evaluate(kpi)
breach = ev.to_breach(kpi, reading, verdict)

incident = correlate.group([breach], board_size=len(BY_NAME))[0]

print(breach.one_line())
print('breached  ', verdict.breached)
print('incident  ', incident.incident_id, '|', incident.severity,
      '|', incident.signal_count, 'signal(s)')
print('grouped   ', incident.correlation)""")
n.md("""
Five agents, one incident, no human. This takes a minute or two, and prints
nothing until it is finished.

**To watch it work, run it from a terminal instead**, where every tool call and
every verdict is printed as it happens:

```
python cli.py investigate surge_coverage_pct
```
""")
n.code("""out = investigate(incident)

print('  ' + ' -> '.join(s['tool'] for s in out['steps']))
print('  waiting for human:', out['waiting_for_human'])
print()
print(out['handover'])""")
n.md("""
Put the estate back before moving on.
""")
n.code("""run('break_it.py', '--fix')
run('cli.py', 'run', 'p7_silver_rides')
run('cli.py', 'run', 'p8_gold_daily')""")
n.md("""
---

## What you should have seen

Five tool calls, in order, and a handover naming the pipeline, the release and
the path.

**None of that is written into any prompt.** There is no list of incidents
anywhere in this project. The agents were given a method and a toolbox, which is
why a problem nobody has seen before is worked the same way as this one.

## What you learned

- **Five narrow agents beat one wide one**, because the constraint enforces the method
- The data detective **cannot read code**; the lineage detective **cannot query**
- **Triage is cheap and runs first**, so the expensive agents are never woken for noise
- **Subagents as tools** is the current LangChain pattern. `create_supervisor` is gone
- Every specialist returns **a typed verdict**, because a supervisor cannot branch
  on a paragraph
- The supervisor **holds the plan and investigates nothing**
""")
n.save()


# ═══════════════════════════════════════════════════════════════════════════
n = NB("17-what-it-is-allowed-to-do.ipynb")
n.md("""
# 17 · What it is allowed to do, and what it is not

The agents can now diagnose. The dangerous idea is to let them fix.

This notebook is about the boundary: what the system produces, what it refuses
to do, and where a person is put in the way on purpose.

![](img/oncall-4-artifacts.png)

> **It proposes. A person decides. Nothing it does changes a number.**
""")
n.code("""import sys; sys.path.insert(0, '..')
from pipelines.lib.config import dsn, SCHEMA""")
n.md("""
---

## Four artifacts, and one of them is not optional

| Tool | Produces | When |
|---|---|---|
| `publish_incident_page` | a Confluence page with a diagram | **always** |
| `raise_ticket` | a tracked item with an owner | **always** |
| `propose_code_change` | a branch and a pull request | when the fix is code |
| `request_db_change` | an approval request. Runs nothing | when the fix touches data |

### Why a page is always produced

Because the most common outcome of an investigation is not a fix. It is a
diagnosis, some evidence, and a decision that belongs to somebody who was
asleep.

**A system that only produces output when it is confident produces nothing on
the nights you needed it most.**

---

## The page

Composed in code, not by the model. The agent supplies eight strings; the shape,
the ordering, the macros and the column widths are fixed here.
""")
n.code("""from agent_service.tools import confluence as cf

print('the pieces a page is built from:\\n')
for name in ('details', 'status', 'toc', 'panel', 'code', 'expand', 'table', 'image'):
    fn = getattr(cf, name)
    print(f'  {name:10} {(fn.__doc__ or "").strip().splitlines()[0][:66]}')""")
n.md("""
### Why the model does not write the XHTML

Ask a model for Confluence storage format and you get a different page every
time, some of them broken. Ask it for eight strings and assemble them yourself
and **every page in the space looks the same**, which is what makes a space
navigable rather than a pile.

The structure, in order: a summary table, a provenance panel, a table of
contents, what happened, a diagram, evidence in code blocks, what it means,
numbered steps, an ownership table, and a collapsed appendix.

**A reader should be able to stop after the summary table and still know what to
do.** Everything below the fold is for the person who wants to check the work.
""")
n.code("""summary = cf.details([
    ('Status',   cf.status('open')),
    ('Severity', cf.status('high')),
    ('Owner',    '<p>pricing</p>'),
])
print(summary[:400], '...')""")
n.md("""
That is the page properties macro. Confluence can roll those up into a report,
so a parent page becomes an index of every incident **without anybody
maintaining one**.

## Is Confluence configured here?
""")
n.code("""print('configured:', cf.configured())
if not cf.configured():
    print('\\nNo Atlassian credentials, so pages are written to artifacts/ as markdown.')
    print('The whole project still runs. Set ATLASSIAN_SITE, ATLASSIAN_EMAIL,')
    print('ATLASSIAN_TOKEN and CONFLUENCE_SPACE in .env to publish for real.')
else:
    print('site  :', cf.SITE)
    print('space :', cf.SPACE_KEY)
    print('parent:', cf.PARENT_TITLE)""")
n.md("""
### The seam

`Publisher` is an interface with two implementations: markdown on disk, or the
Confluence REST API. It turns itself on when the credentials are present.

**Swapping one for the other changes no agent code.** That is the entire reason
the interface exists, and it is why this project works for a student with no
Atlassian account and for you with one.

---

## The diagram

An incident page should answer the question everybody asks first and nobody
writes down: **where in the flow did this break?**
""")
n.code("""from agent_service.tools import diagram

png = diagram.render(
    breach_id='DEMO',
    kpi='surge_coverage_pct',
    title='Surge stopped arriving for one release',
    broken_at='the contract in pipelines/p3_bronze_driver_app.py',
    what_broke='The loader knows four paths for surge. The release sends a fifth.')
print('drawn:', png)""")
n.code("""from IPython.display import Image, display
if png:
    display(Image(str(png), width=980))""")
n.md("""
Green is proved fine. Red is where the value stops being readable. **Amber is
every layer after it, which keeps working perfectly and reports a number built
on less data than it should be.**

Nothing fails. No row count changes. That is the whole problem, drawn.

---

## Code changes: a branch and a pull request, never a merge
""")
n.code("""from agent_service.tools.publish import WRITABLE, propose_code_change
print('directories a proposed change may touch:', WRITABLE)
print()
print(propose_code_change.invoke({
    'breach_id': 'DEMO', 'summary': 'x', 'rationale': 'x',
    'path': 'platform/docker-compose.yml',
    'old_string': 'a', 'new_string': 'b'}))""")
n.md("""
**An agent that can edit the tests which judge it is not being judged.**

And before a human is even asked, the edit is applied in memory and the result
is parsed:
""")
n.code("""print(propose_code_change.invoke({
    'breach_id': 'DEMO',
    'summary': 'deliberately break the syntax',
    'rationale': 'to show the gate',
    'path': 'signals/board.py',
    'old_string': 'Z_THRESHOLD = 4.0',
    'new_string': 'Z_THRESHOLD = = 4.0'}))""")
n.md("""
> **Whether a change is right is a judgement. Whether it compiles is a fact.**
> Facts get checked before a person is asked for an opinion.

---

## Data changes: the graph stops

This is the one the user is put in the way of, deliberately.
""")
n.code("""from agent_service.tools.publish import request_db_change
print(request_db_change.invoke({
    'breach_id': 'DEMO',
    'summary': 'Backfill surge for release 4.2.0',
    'rationale': 'The value exists in the source at a path the contract now reads.',
    'statement': "UPDATE teach.bronze_driver_app SET surge = surge_backup "
                 "WHERE surge IS NULL AND app_version = '4.2.0';",
    'rows_affected_estimate': '395 rows, counted with a SELECT before proposing this',
    'reversible': 'Yes: surge_backup is untouched, so setting surge back to NULL restores it.',
}))""")
n.md("""
### Read what it did not do

It did not run the statement. **No part of this system will run it.** A person
does that, by hand, having read it.

And it insisted on three things before it would even record the request: the
exact statement, an estimate of the blast radius, and **how to undo it**. Never
propose a data change without saying how to reverse it.

## And the graph itself pauses
""")
n.code("""from agent_service.tools.publish import GATED
from agent_service.supervisor import build_supervisor
import inspect

print('tools that stop for a human:', GATED)
print()
print(inspect.getsource(build_supervisor))""")
n.md("""
`HumanInTheLoopMiddleware` pauses the graph **before** a gated tool runs. The
investigation comes back with `waiting_for_human: True` and nothing has
happened yet.

Resuming takes a decision and a reason:

```python
resume(thread_id, breach, approve=False, note="we are rolling the app back instead")
```

**Rejecting is a real outcome and the reason goes back to the agent.** That is
the difference between a human gate and a rubber stamp.

### Why code changes do not pause here

A pull request is already a human gate, by construction. Pausing twice for the
same decision teaches people to click through, and a gate everybody clicks
through is worse than no gate, because it looks like control.

---

## What you learned

- **A page and a ticket are always produced**, even when the diagnosis is uncertain
- The page is **composed in code**, so every page in the space looks the same
- The publisher is **an interface**, so no credentials still works
- Code changes go to **a branch and a pull request**, never a merge, and only in
  two directories
- The edit is **parsed before a human is asked**, because compiling is a fact
- Data changes **stop the graph**. Nothing is executed, ever
- A proposed data change must say **how to reverse it**
""")
n.save()


# ═══════════════════════════════════════════════════════════════════════════
n = NB("18-running-it-for-real.ipynb")
n.md("""
# 18 · Running it for real

Everything so far you started by running a cell. In production nobody is awake
to run a cell.

This notebook is the deployment: three containers, one clock, and a break that
nobody triggers by hand.
""")
n.code("""import sys; sys.path.insert(0, '..')
import subprocess, httpx, os, time
from pipelines.lib.config import dsn, SCHEMA

def compose(*args):
    r = subprocess.run(['docker', 'compose', '-f', '../platform/docker-compose.yml', *args],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()

print(compose('ps', '--format', '{{.Name}}\\t{{.Status}}'))""")
n.md("""
---

## Three containers, not two

The signal board is genuinely two things, and they are separated on purpose.

| Container | Runs | Why separate |
|---|---|---|
| `signal-api` | `uvicorn signal_service.api:app` | answers questions |
| `signal-scheduler` | `python -m signal_service.scheduler` | asks them on a clock |
| `agent` | `uvicorn agent_service.worker:app` | asleep until a record arrives |

A dashboard hammering `/signals` must not be able to slow the clock down, and a
slow clock must not make the dashboard time out. They share a package and share
nothing else.

## Start them
""")
n.code("""print(compose('up', '-d', 'signal-api', 'signal-scheduler', 'agent'))""")
n.code("""SIGNAL = os.environ.get('SIGNAL_SERVICE_URL', 'http://localhost:8091')
AGENT  = os.environ.get('AGENT_SERVICE_URL',  'http://localhost:8092')

for name, url in [('signal', SIGNAL), ('agent', AGENT)]:
    for _ in range(30):
        try:
            print(f'{name:7}', httpx.get(f'{url}/health', timeout=5).json()); break
        except Exception:
            time.sleep(2)
    else:
        print(f'{name:7} not reachable at {url}')""")
n.md("""
### Where the secrets are

Look at the compose file: `env_file: [../.env]`. The model key and the Atlassian
token come from `.env`, which is git ignored. **No secret is written into a file
that gets committed**, and the same file works for a laptop and a container.

And note the environment block: `POSTGRES_HOST: postgres`, not `localhost`.
`config.py` loads `.env` with `override=False`, so the container's value wins
and not one line of service code changes between the two.

---

## Watch the clock work
""")
n.code("""print(compose('logs', '--tail', '12', 'signal-scheduler'))""")
n.md("""
---

## Now break something, and touch nothing else

This is the whole point of the class. From here on, nobody types anything.
""")
n.code("""before = httpx.get(f'{SIGNAL}/signals', timeout=120).json()
print(f'before: {before["breached"]} breached')
for s in before['signals']:
    if s['breached']:
        print(f'   {s["kpi"]:26} {s["value"]:,.2f}{s["unit"]}')""")
n.code("""# cwd is the repo root, so the path is 'break_it.py' and not '../break_it.py'.
# Both of those together point one level above the project.
r = subprocess.run([sys.executable, 'break_it.py'], capture_output=True, text=True,
                   cwd='..')
print(r.stdout + r.stderr)

# Silver and gold only. Re-running the bronze driver app pipeline would read
# mongodb again and put the surge values straight back, which is a confusing
# way to discover that the break lives in OUR copy and not in the source.
for mod in ('pipelines.p7_silver_rides', 'pipelines.p8_gold_daily'):
    subprocess.run([sys.executable, '-m', mod], capture_output=True, cwd='..')
print('pipelines re-run. Every one of them succeeded.')""")
n.md("""
**Nothing failed.** No pipeline errored, no row count changed, and the warehouse
looks healthy from every angle except one.

Now wait for the clock. It runs every sixty seconds by default.
""")
n.md("""
What we are waiting for is an **incident**, not a breach. The board raises a
breach per KPI and then groups them, because one cause can move several numbers
and nobody wants four investigations of one thing. The incident id is what the
agent service works with, so it is what we watch for.
""")
n.code("""import psycopg

incident_id = None
for i in range(20):
    with psycopg.connect(dsn()) as c:
        row = c.execute(\"\"\"SELECT incident_id, primary_kpi, signal_count, status
                             FROM oncall.incidents
                             WHERE primary_kpi = 'surge_coverage_pct'
                             ORDER BY detected_at DESC LIMIT 1\"\"\").fetchone()
    if row:
        incident_id = row[0]
        print(f'  {i*6:>4}s  the board raised {row[0]}  '
              f'({row[2]} signal(s), {row[3]})')
        break
    print(f'  {i*6:>4}s  nothing yet')
    time.sleep(6)

if incident_id is None:
    print('\\n  Nothing was raised. The usual reason is that the scheduler '
          'container is not running:\\n  docker compose -f ../platform/docker-compose.yml '
          'up -d signal-scheduler')""")
n.md("""
## And the agent picked it up without being asked

Nobody called the agent service. The board rang its doorbell the moment it
recorded the incident, and it started work on a background thread.
""")
n.code("""d = None
for i in range(40):
    r = httpx.get(f'{AGENT}/investigations/{incident_id}', timeout=30)
    if r.status_code == 200:
        d = r.json()
        print(f'  {i*6:>4}s  {d["status"]:20} {d.get("steps") or ""}')
        if d['status'] in ('done', 'waiting_for_human', 'failed'):
            break
    else:
        print(f'  {i*6:>4}s  not started yet')
    time.sleep(6)""")
n.code("""print(d.get('handover') or d.get('error') or 'no handover yet')
print('\\nARTIFACTS')
for p in d['pages']:            print('   page   ', p['url'] or p['page_id'])
for t in d['tickets']:          print('   ticket ', t['ticket_id'], t['kind'], t['severity'])
for c in d['change_requests']:  print('   change ', c['request_id'], c['kind'], c['status'])
if not (d['pages'] or d['tickets'] or d['change_requests']):
    print('   none. Triage decided the breach was not real, and stopped.')""")
n.md("""
---

## What just happened

1. A field moved upstream. Nothing failed
2. The clock evaluated thirteen KPIs, as it does every minute
3. One breached, and the board **wrote a record, then rang a doorbell**
4. The agent service accepted it and returned immediately, so the clock kept ticking
5. Five agents investigated, in order, stopping when they had enough
6. A page and a ticket appeared, with an owner and a diagram

**Nobody typed anything after step 1.**

## Put it back
""")
n.code("""print(subprocess.run([sys.executable, 'break_it.py', '--fix'],
                    capture_output=True, text=True, cwd='..').stdout)
for mod in ('pipelines.p7_silver_rides', 'pipelines.p8_gold_daily'):
    subprocess.run([sys.executable, '-m', mod], capture_output=True, cwd='..')
print(httpx.post(f'{SIGNAL}/evaluate', timeout=180).json()['breached'], 'still breached')""")
n.md("""
---

## What you learned

- **Three containers**, because answering questions and asking them are different jobs
- Secrets come from `.env` through `env_file`, never from a committed file
- `override=False` is why `localhost` and `postgres` are the same code
- The doorbell **returns immediately**, so a two minute investigation cannot stall
  a sixty second clock
- The record is durable **before** the doorbell rings, and a sweep is the backstop
- From a field moving to a page with an owner on it: **nobody typed anything**
""")
n.save()


# ═══════════════════════════════════════════════════════════════════════════
n = NB("19-the-code-walked-through.ipynb")
n.md("""
# 19 · The code, walked through

Eighteen notebooks built things. This one is different: **nothing new is built
here.** It is a guided tour of the code you have been running, in the order the
files actually depend on each other.

Use it when you have finished the course and want to change something, or when
you are about to explain the project to somebody else.

Every cell prints real source out of real files. Nothing is pasted, so nothing
can drift.
""")
n.code("""import sys; sys.path.insert(0, '..')
import inspect, pathlib, subprocess

ROOT = pathlib.Path('..').resolve()

def show(obj, lines=None):
    \"\"\"Print the real source of a real function or class.\"\"\"
    src = inspect.getsource(obj)
    print(src if lines is None else '\\n'.join(src.splitlines()[:lines]))

def head(path, n=30):
    \"\"\"Print the top of a file, which is where its docstring lives.\"\"\"
    text = (ROOT / path).read_text().splitlines()[:n]
    print(f'--- {path} ---')
    print('\\n'.join(text))

print('project root:', ROOT)""")
n.md("""
---

## The shape, in one cell

Six things, and only two of them are the subject of this course.
""")
n.code("""LAYOUT = [
    ('pipelines/',      'THE WAREHOUSE. Eight pipelines, one per source.'),
    ('seed/',           'Generates the world all six systems describe.'),
    ('events/',         'ONE FILE. The record both services agree on.'),
    ('signal_service/', 'SERVICE ONE. Thirteen KPIs, a clock, an API.'),
    ('agent_service/',  'SERVICE TWO. Five agents and their toolbox.'),
    ('tests/',          'What the project CLAIMS, written as assertions.'),
]
for folder, what in LAYOUT:
    files = sorted(p.name for p in (ROOT / folder).glob('*.py')
                   if '__pycache__' not in str(p))
    print(f'{folder:18} {what}')
    print(f'{"":18} {", ".join(files)}\\n')""")
n.md("""
---

# Part one · the file both services depend on

Start here, always. It is the smallest file in the project and it defines the
only thing that crosses between the two services.
""")
n.code("""head('events/contract.py', 14)""")
n.md("""
### Why it lives in a package neither service owns

The moment one side owns the shape of the record, the other side is a client
rather than a peer, and changing it becomes a negotiation.

Two records are defined in here. Read the second one's docstring out loud in
class: it contains the arithmetic that justifies the whole grouping feature.
""")
n.code("""from events.contract import Incident
print(inspect.getdoc(Incident))""")
n.md("""
---

# Part two · the signal board, file by file

Five files, and each one only needs the one before it.

```
kpis.py        the catalogue. What is watched, and by whom
evaluate.py    a KPI becomes a reading; a reading becomes a verdict
correlate.py   many breaches become one incident
emit.py        record it, THEN ring the doorbell
scheduler.py   the clock
```

## kpis.py · what a KPI is, and what it is not
""")
n.code("""head('signal_service/kpis.py', 20)""")
n.md("""
**That distinction is the spine of the service.** Everything else follows from
it: a KPI cannot fire, a signal can, and the difference is a baseline somebody
had to sit down and write.

Now look at one entry. Six fields, and the one people skip is `owner`.
""")
n.code("""from signal_service.kpis import get, CATALOGUE
k = get('surge_coverage_pct')
for field in ('name', 'title', 'owner', 'watches', 'unit',
              'judgement', 'baseline', 'tolerance', 'watch_direction'):
    print(f'  {field:16} {getattr(k, field)}')
print(f'\\n  means:\\n    {k.means}')""")
n.md("""
### The two things to point at when you teach this

**`owner` is a team that exists.** A breach with no name attached is a number on
a screen everybody assumes somebody else is looking at.

**`tolerance` is 1, not 5.** In normal operation this number is exactly 100.0,
because the pipeline holds a record it cannot read rather than writing a null.
So any drop is real, and a generous tolerance would let a release move a field
and stay under the bar for weeks.

## evaluate.py · why measuring and judging are separate steps
""")
n.code("""from signal_service import evaluate as ev
print(inspect.getdoc(ev))""")
n.md("""
And the line that took twelve KPIs down until it was found:
""")
n.code("""src = inspect.getsource(ev.read)
print(src[src.index('    except Exception as e:'):])""")
n.md("""
> **One poison KPI must not block the rest**, which is the same rule as one
> poison message on a topic.

## correlate.py · the rules that stop six pages for one cause
""")
n.code("""from signal_service import correlate
print(inspect.getdoc(correlate))""")
n.code("""show(correlate.group)""")
n.md("""
### Read the order of the rules

Rule 2 is the one that earns its keep. If the pipeline did not run, then rides,
revenue and coverage are all wrong **because of that**, and investigating them
separately is five wasted investigations that end at the same sentence.

And notice the whole thing is conservative on purpose: **a rule that groups two
genuinely separate problems is worse than one that misses a grouping.**

## emit.py · the two steps that are not the same step
""")
n.code("""from signal_service import emit
print(inspect.getdoc(emit))""")
n.md("""
## scheduler.py · thirty lines, three decisions
""")
n.code("""from signal_service import scheduler
print(inspect.getdoc(scheduler))""")
n.md("""
---

# Part three · the agents, file by file

```
tools/warehouse.py   read only SQL. The guard that is a fact
tools/lineage.py     code and git. Cannot touch the database
tools/verify.py      re-run a pipeline, re-check the invariants
tools/publish.py     the artifacts a person acts on
tools/repo.py        the isolated worktree
agents.py            the five specialists
supervisor.py        subagents as tools
worker.py            the HTTP surface and the worker pool
```

## The toolbox is split so no agent can do everything
""")
n.code("""from agent_service.tools.warehouse import READ_TOOLS
from agent_service.tools.lineage import LINEAGE_TOOLS
from agent_service.tools.verify import VERIFY_TOOLS
from agent_service.tools.publish import PUBLISH_TOOLS
from agent_service.tools.signals import SIGNAL_TOOLS

for label, tools in [('warehouse (agent 2)', READ_TOOLS),
                     ('lineage   (agent 3)', LINEAGE_TOOLS),
                     ('publish   (agent 4)', PUBLISH_TOOLS),
                     ('verify    (agent 5)', VERIFY_TOOLS),
                     ('signals   (agent 1)', SIGNAL_TOOLS)]:
    print(f'{label}  {len(tools)}')
    for t in tools:
        print(f'    {t.name}')
    print()""")
n.md("""
> **An agent with every tool will use every tool.**

The data detective cannot open a file, so everything it reports came from a
query. The lineage detective cannot query, so it cannot redo the previous
agent's work with worse tools.

## The guard that is a fact, not a promise
""")
n.code("""from agent_service.tools import warehouse
print(inspect.getdoc(warehouse))""")
n.code("""src = inspect.getsource(warehouse._query)
print(src[:1500])""")
n.md("""
### This is the sentence to write on the whiteboard

> **Whether an agent meant well is a judgement. Whether it CAN write is a fact.**

`conn.read_only = True` is the fact. The regex above it is a courtesy that makes
the error message readable. Every rule you enforce only in a system prompt is a
rule you are hoping about.

## agents.py · the prompts ARE the lesson

There is no list of known incidents anywhere in this project. Each agent is
given a method and a toolbox. Read one out loud.
""")
n.code("""from agent_service.agents import DATA_PROMPT
print(DATA_PROMPT)""")
n.md("""
Nowhere does it say "if surge is missing, look at app versions". It says *split
it, by whatever column exists*, and the agent works out which column mattered by
looking.

**That is the difference between a system that handles six known problems and
one that handles the problem nobody has seen.**

## supervisor.py · subagents as tools
""")
n.code("""from agent_service import agents
src = inspect.getsource(agents.build_subagent_tools)
print(src[src.index('    @tool("triage"'):src.index('    @tool("investigate_lineage"')])""")
n.md("""
Each specialist is an agent, wrapped as a tool, returning a typed verdict as
JSON. The supervisor decides who is asked next and carries the answer forward.

**The specialists are stateless.** Each starts in a clean context, which is what
stops the fifth agent inheriting four agents' worth of noise.

## repo.py · the bug that shaped a file
""")
n.code("""from agent_service.tools import repo
print(inspect.getdoc(repo))""")
n.md("""
Worth telling as a story in class, because it is the project failing at exactly
the thing it teaches. It reported success and committed nothing.

---

# Part four · the tests are the specification

If you want to know what this project actually promises, do not read the README.
Read the assertions.
""")
n.code("""out = subprocess.run(['python', '-m', 'pytest', '--collect-only', '-q'],
                     cwd=ROOT, capture_output=True, text=True)
lines = [l for l in out.stdout.splitlines() if '::' in l]
print(f'{len(lines)} tests\\n')
for f in ('test_guards', 'test_correlate', 'test_isolation', 'test_catalogue'):
    n_in = sum(1 for l in lines if f in l)
    print(f'  {f:20} {n_in:>4}')""")
n.code("""names = sorted({l.split('::')[-1].split('[')[0] for l in lines if 'test_guards' in l})
print('what the guards promise:\\n')
for name in names:
    print('  ', name.replace('test_', '').replace('_', ' '))""")
n.md("""
Read that list as a sentence each. **That is the safety story of this project,
and every line of it is executable.**

---

# Part five · changing it

Three things you will want to do, and where each one lives.

## Add a KPI

One entry in `signal_service/kpis.py`. Nothing else changes: the API, the clock,
the store and the agents all pick it up.
""")
n.code("""print(inspect.getsource(type(get('records_held'))).split('# ═══')[0])""")
n.md("""
Three rules for a new one: **the query returns exactly one number**, `means` is
written for the owner rather than for you, and the owner is somebody who exists.

## Add an invariant

One entry in `signal_service/invariants.py`. Remember the difference: if you
want to write "usually" into it, it is a signal and it belongs in `kpis.py`.

## Add a tool

A function with `@tool` in `agent_service/tools/`, added to exactly one agent's
list. Before you write it, decide which of these three it is:

| | |
|---|---|
| **read only** | enforced at the connection, not in the prompt |
| **limited** | an allow list of names or directories |
| **gated** | it stops the graph and waits for a person |

**Never rely on the system prompt to hold a boundary.**

---

## What to say at the end of the course

The whole project is one argument, and it fits in four lines:

> A pipeline that fails wakes somebody.
> A pipeline that succeeds while quietly carrying less data than it should
> wakes nobody.
> Every row count check you can write stays green through that.
> So something has to watch the numbers, and something has to work out why.

Everything else, the medallion layers, the contracts, the quarantine, the
thirteen KPIs, the seventeen invariants, the five agents and the four
boundaries, is machinery in service of those four lines.
""")
n.save()
