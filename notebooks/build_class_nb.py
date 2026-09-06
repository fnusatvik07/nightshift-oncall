"""The class itself: one notebook, ninety minutes, run live in front of a room.

Not a guide for the instructor. This is what the room sees.

Every section is CONCEPT, then SEE IT, then THE CODE. Nobody is shown a line of
code before they know what problem it solves, and nobody is told a concept
without being shown it happening.
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


n = NB("00-the-class.ipynb")

n.md("""
# How a number goes wrong, and who finds out

### Ninety minutes. Everything on this screen is running for real.

---

You are going to see a data platform break in the way that costs companies the
most money: **quietly**. Then you are going to see the two pieces of software
that catch it.

By the end you will know what a KPI is, why it cannot raise an alarm on its own,
what an AI agent actually is underneath, and why this one is not allowed to fix
anything.

No prior knowledge assumed. If you have never written a pipeline or used an
agent framework, you are in the right room.

| | |
|---|---|
| **00 to 15** | the problem. A number goes wrong and nothing fails |
| **15 to 30** | a KPI is not a signal |
| **30 to 45** | turning a check into a service |
| **45 to 65** | what an agent actually is |
| **65 to 80** | why five agents, and what they cannot do |
| **80 to 90** | the whole thing, running unattended |
""")
n.code("""import sys; sys.path.insert(0, '..')
import inspect, psycopg
from pipelines.lib.config import dsn, SCHEMA
from nb import show, sql, fetch, run

print('connected to the warehouse.')""")

# ═══════════════════════════════════════════════════════════════════════════
n.md("""
---

# Part 1 · The problem
### 00 to 15 minutes

## The setup, in one paragraph

KERB is a ride hailing company. Riders book cars. That data lives in six
different systems: a database, an event stream, a document store, a payment
partner's API, a file drop, and a reference table.

None of them agree with each other, because they were built by different teams
at different times. So we copy all six into one place, a **warehouse**, and
answer questions from the copy.

That copy is already built. Here is what is in it.
""")
n.code("""sql(f\"\"\"
    SELECT trip_date, rides, completed, cancelled, revenue, avg_surge
    FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 7
\"\"\", 'the answer finance reads: one row per day')""")
n.md("""
That table is the end of a chain: six sources, six copy jobs, one join, one
aggregate. Somebody looks at it every morning.

## Now watch it break

A mobile release goes out. It moves one field to a new place in the payload.
Nobody tells the data team, because why would they.
""")
n.code("""run('break_it.py')""")
n.md("""
### Nothing has failed yet. Let us re-run the whole pipeline.
""")
n.code("""run('cli.py', 'run', 'all')""")
n.md("""
## Read that output carefully

**Every single pipeline says `ok`.**

Nothing crashed. Nothing errored. No alert fired anywhere, because there is
nothing to fire on: a pipeline that reads a row it cannot fully understand still
reads the row.

Look at the row counts. They are the same as before.
""")
n.code("""sql(f\"\"\"
    SELECT app_version,
           count(*)                    AS rows,
           count(surge)                AS with_a_surge_value,
           count(*) - count(surge)     AS missing
    FROM {SCHEMA}.bronze_driver_app
    GROUP BY 1 ORDER BY 1
\"\"\", 'the rows all arrived. one column did not')""")
n.md("""
## This is the entire problem

| What you would check | What it says |
|---|---|
| did the pipeline run? | yes |
| did it fail? | no |
| how many rows landed? | exactly as many as usual |
| is the data correct? | **no** |

> **A pipeline that fails wakes somebody up.**
> **A pipeline that succeeds while quietly carrying less data than it should
> wakes nobody.**

Every row count check you can write stays green through this. So does every
error log, every retry, every dashboard that shows pipeline status.

**Somebody has to watch the numbers themselves.**
""")

# ═══════════════════════════════════════════════════════════════════════════
n.md("""
---

# Part 2 · A KPI is not a signal
### 15 to 30 minutes

## Start with the word everybody uses loosely

Here is a number. It is a real number, correctly calculated, from the table
finance reads.
""")
n.code("""with psycopg.connect(dsn()) as c:
    revenue = float(c.execute(
        f'SELECT revenue FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC LIMIT 1'
    ).fetchone()[0])

print(f'revenue yesterday: {revenue:,.2f}')
print()
print('Question for the room: is that good or bad?')""")
n.md("""
## Nobody can answer that

Not you, not me, and not any alerting system ever built. **A number on its own
has no opinion about itself.**

To have an opinion you need a second thing: what it normally is.
""")
n.code("""import statistics

with psycopg.connect(dsn()) as c:
    history = [float(r[0]) for r in c.execute(
        f'SELECT revenue FROM {SCHEMA}.gold_daily ORDER BY trip_date DESC OFFSET 1')]

baseline = statistics.mean(history)
spread   = statistics.pstdev(history)

print(f'  yesterday        {revenue:>14,.2f}')
print(f'  normally         {baseline:>14,.2f}   over {len(history)} days')
print(f'  usual wobble     {spread:>14,.2f}')
print()
print(f'  how unusual is it?  {(revenue - baseline) / max(spread, 0.01):>5.2f} wobbles from normal')""")
n.md("""
## So here is the definition. Write it down.

> ### A **KPI** is a number with a definition and an owner.
> It is never wrong. **It can never raise an alarm.**
>
> ### A **signal** is a KPI plus a baseline plus a tolerance.
> **That** is the thing that can go off.

The baseline is the part nobody wants to write, because it means committing to a
sentence like *"revenue is normally about 1.9 million a day"*, and being wrong
about it in public.

**It is also the only part that turns a number into something you can act on.**

## Two kinds of normal, and both are correct

Some numbers have a **history**. Some have a **rule**.
""")
n.code("""with psycopg.connect(dsn()) as c:
    held = c.execute(f'SELECT count(*) FROM {SCHEMA}.quarantine').fetchone()[0]

print(f'records the system refused to publish: {held:,}')
print()
print('What is the "normal" number here?')
print()
print('It is NOT the average of the last seven days.')
print('It is zero. Somebody decided that. It is a rule, not a statistic.')""")
n.md("""
| | computed from history | decided by a person |
|---|---|---|
| example | revenue, rides per day | held records, failed pipelines |
| normal is | the average of before | a number somebody chose |
| goes off when | it is far from usual | it is anything other than the rule |
| gets it wrong on | a genuinely quiet Sunday | nothing, but somebody has to decide it |

A system with only the first kind cannot say *"this should be zero"*.
A system with only the second cannot say *"quieter than a normal Tuesday"*.

## Now the code

Everything you just saw is one file. Thirteen entries, each one six fields.
""")
n.code("""from signal_service.kpis import get, CATALOGUE

k = get('surge_coverage_pct')
for field in ('name', 'owner', 'watches', 'unit', 'judgement',
              'baseline', 'tolerance', 'watch_direction'):
    print(f'  {field:16} {getattr(k, field)}')
print(f'\\n  means:\\n    {k.means}')""")
n.md("""
### Three things to notice, and they are all about people rather than code

**`owner` is a team, by name.** Not "the data team". A breach with no name
attached is a number on a screen that everybody assumes somebody else is
looking at.

**`means` is written for that owner**, who reads it at 3am having never seen
this code. Not for the engineer, and not for the model.

**`watch_direction` is `below`.** Coverage going *up* is good news. A check that
fires on good news trains people to ignore it.

## The thirteen, and the four questions they answer
""")
n.code("""groups = {
    'did the work happen': ('pipelines_failing', 'warehouse_lag_hours', 'records_held'),
    'is the volume right': ('rides_per_day', 'revenue_per_day', 'events_per_ride'),
    'is the shape right':  ('completion_rate', 'cancellation_rate', 'avg_fare'),
    'is anything missing': ('surge_coverage_pct', 'fare_coverage_pct',
                            'zone_coverage_pct', 'settlement_coverage_pct'),
}
for question, names in groups.items():
    print(f'\\n{question.upper()}')
    for name in names:
        kpi = get(name)
        how = 'a rule' if kpi.judgement == 'fixed' else 'history'
        print(f'   {kpi.name:26} {kpi.owner:15} {how}')""")
n.md("""
### One of those is not like the others

`pipelines_failing` does not look at a single row of business data. It asks
**whether the work happened at all**.

That matters because **a pipeline that never ran leaves perfectly correct rows
behind.** Every value is right. Every value is yesterday's. No check that looks
only at values will ever notice.

## And now, does it catch our break?
""")
n.code("""run('cli.py', 'signals')""")

# ═══════════════════════════════════════════════════════════════════════════
n.md("""
---

# Part 3 · Turning a check into a service
### 30 to 45 minutes

## What you just ran was a command

Somebody typed it. At 3am nobody is typing.

A **service** is that same check with three things added, and each one exists
for a reason you can say in a sentence.

| | so that |
|---|---|
| **a clock** | nobody has to type |
| **an API** | anything can ask, without knowing where the data lives |
| **a memory** | "when did this start" has an answer |

## The clock

Thirty lines. The lines are not the interesting part.
""")
n.code("""run('-m', 'signal_service.scheduler', '--once', '--no-notify')""")
n.md("""
### Three decisions inside those thirty lines

**Why a loop and not cron.** Cron is fine, and often right. A loop can hold one
thing cron cannot: **the memory of what it already raised.** A process that
exits every minute has none.

**Why it never dies.** Every cycle is wrapped. If the database is down it says
so, waits, and tries again. A checker that stops on the first error is a checker
that was running yesterday.

**Why it is separate from the API.** A dashboard refreshing every ten seconds
must not be able to slow the clock down.

## The one design decision worth arguing about
""")
n.code("""from signal_service.api import app

for route in app.routes:
    if hasattr(route, 'methods') and not route.path.startswith(
            ('/openapi', '/docs', '/redoc')):
        methods = ','.join(sorted(route.methods - {'HEAD', 'OPTIONS'}))
        print(f'   {methods:5} {route.path}')""")
n.md("""
Look at which one is a `POST`.

**`GET /signals` measures and tells you. It records nothing and wakes nobody.**
**`POST /evaluate` is the only one that can start an investigation.**

> A dashboard on a ten second refresh must not be able to page somebody.

If measuring had side effects, the act of *looking* at the board would generate
incidents. You would have built a machine that alarms on being observed.

## The problem nobody thinks about until it happens

The clock runs every minute. A broken pipeline stays broken for hours.

Thirteen signals watch one warehouse, so when a pipeline dies, six of them go off
**in the same minute, for one reason**.
""")
n.code("""from signal_service import correlate
from events.contract import SignalBreach
import datetime as dt

def fake(kpi, owner, watches):
    return SignalBreach(breach_id=f'B-{kpi}', detected_at=dt.datetime.now(dt.timezone.utc),
                        kpi=kpi, title=kpi, value=1, baseline=0, deviation=1,
                        severity='high', owner=owner, watches=watches, means=kpi)

breaches = [
    fake('pipelines_failing', 'data-platform', 'teach.runs'),
    fake('rides_per_day',     'operations',    'teach.gold_daily'),
    fake('revenue_per_day',   'finance',       'teach.gold_daily'),
    fake('fare_coverage_pct', 'finance',       'teach.silver_rides'),
]
print(f'{len(breaches)} signals went off in the same cycle\\n')

for incident in correlate.group(breaches, board_size=13):
    print(f'  -> {incident.signal_count} of them became ONE incident')
    print(f'     led by:  {incident.primary.kpi}')
    print(f'     because: {incident.correlation}')""")
n.md("""
### Without that, one broken pipeline becomes four investigations

Four pages, four tickets, four people woken, four times the cost, for **one
cause**. And the person on call has to work out they are the same thing before
they can start.

> **Group before you page.**

The rules are deliberately cautious, and the reason is worth saying: **grouping
two genuinely separate problems is worse than missing a grouping.** The second
costs money. The first costs you a missed incident.

## And then it hands over exactly one record
""")
n.code("""from signal_service import emit
print(inspect.getdoc(emit))""")
n.md("""
### Read the order, because it is the whole lesson

**Write the record to the database. Then ring the doorbell.**

Do it that way and a failed notification costs you *latency*: the record is on
disk and gets picked up later. Do it the other way round and a restart at the
wrong second means an incident nobody ever hears about, with no error anywhere.

That same argument comes up every single time two systems have to agree on
something.
""")

# ═══════════════════════════════════════════════════════════════════════════
n.md("""
---

# Part 4 · What an agent actually is
### 45 to 65 minutes

Forget everything you have read about AI agents. Underneath, there are three
ideas and you can hold all of them at once.

## Idea 1 · a tool is a python function

That is it. A normal function, with a normal docstring.
""")
n.code("""from langchain.tools import tool

@tool
def count_rows(table: str) -> str:
    \"\"\"Count the rows in one warehouse table.\"\"\"
    with psycopg.connect(dsn()) as c:
        c.read_only = True
        return f'{table} has {c.execute(f"SELECT count(*) FROM {SCHEMA}.{table}").fetchone()[0]:,} rows'

print('the model sees exactly this, and nothing else:\\n')
print('  name       ', count_rows.name)
print('  description', count_rows.description)
print('  arguments  ', count_rows.args)
print()
print('and when it asks for it, WE run it:')
print(' ', count_rows.invoke({'table': 'silver_rides'}))""")
n.md("""
**The model cannot touch your database.** It can ask you to, by name, with
arguments, and read whatever you hand back.

The docstring is not documentation. **It is the interface.** A vague one produces
an agent that picks the wrong tool and then explains confidently why it was
right.

## Idea 2 · an agent is a loop

Call the model. If it asked for a tool, run the tool. Give it the result. Repeat
until it stops asking.

That is all `create_agent` is.
""")
n.code("""from langchain.agents import create_agent

agent = create_agent(
    model='openai:gpt-5.4-mini',
    tools=[count_rows],
    system_prompt='You answer questions about a data warehouse using your tools.',
)

result = agent.invoke({'messages': [{'role': 'user', 'content':
    'How many rows are in silver_rides and gold_daily?'}]})

for m in result['messages']:
    kind = type(m).__name__.replace('Message', '')
    if getattr(m, 'tool_calls', None):
        for call in m.tool_calls:
            print(f'  {kind:9} asked for {call["name"]}({call["args"]})')
    elif m.content:
        print(f'  {kind:9} {str(m.content)[:130]}')""")
n.md("""
**Read the trace.** It decided to call the tool twice. We ran it twice. It wrote
the answer from what came back.

**Nobody wrote an `if` statement.** That is the whole difference from ordinary
software, and it is the reason this is useful for problems nobody has seen.

## Idea 3 · make it answer in fields, not paragraphs

Prose is readable and useless. If another program has to act on the answer, it
needs something it can branch on.
""")
n.code("""from pydantic import BaseModel, Field

class Verdict(BaseModel):
    is_real: bool = Field(description="is this worth investigating, or a boring reason")
    severity: str
    reason: str

triage = create_agent(
    model='openai:gpt-5.4-mini',
    tools=[],
    system_prompt='You decide whether a number that moved is worth waking somebody for.',
    response_format=Verdict,
)

out = triage.invoke({'messages': [{'role': 'user', 'content':
    'The share of driver app records carrying a surge value fell from 100% to 97.3%. '
    'Pricing models use that value. Is this real?'}]})

v = out['structured_response']
print('  is_real  ', v.is_real, '   <- a real python boolean')
print('  severity ', v.severity)
print('  reason   ', v.reason)""")
n.md("""
`v.is_real` is a `bool`. **That is what lets the rest of the system stop early**,
and it is why every agent in this project answers in a schema.

## That is the whole of it

| | |
|---|---|
| **a tool** | a function the model may ask you to run |
| **an agent** | a model, some tools, and a loop |
| **structured output** | an answer with fields instead of prose |

Everything else you have heard about agents is built out of those three.
""")

# ═══════════════════════════════════════════════════════════════════════════
n.md("""
---

# Part 5 · Why five agents, and what they cannot do
### 65 to 80 minutes

## The obvious design is one agent with every tool

It is also the one that stops working the moment the problem is unfamiliar.

> ### An agent with every tool will use every tool.

Give one agent both SQL and file reading, and it will read a file, form a
theory, and then go looking for numbers that agree with it. That is confirmation
bias, implemented.

## So each one gets a question and a toolbox, and nothing else
""")
n.code("""from agent_service.tools.warehouse import READ_TOOLS
from agent_service.tools.lineage import LINEAGE_TOOLS
from agent_service.tools.publish import PUBLISH_TOOLS
from agent_service.tools.verify import VERIFY_TOOLS
from agent_service.tools.signals import SIGNAL_TOOLS

for who, question, tools in [
        ('1 triage',            'is this real?',      SIGNAL_TOOLS),
        ('2 data detective',    'what is wrong?',     READ_TOOLS),
        ('3 lineage detective', 'where did it start?', LINEAGE_TOOLS),
        ('4 remediation',       'what is the fix?',   PUBLISH_TOOLS),
        ('5 verifier',          'did it work?',       VERIFY_TOOLS)]:
    print(f'{who:22} {question:22} {len(tools)} tools')
    print(f'{"":22} {", ".join(t.name for t in tools)}\\n')""")
n.md("""
### Read rows two and three again

**The data detective cannot open a file.** So everything it reports came from a
query. It literally cannot guess from the code and present the guess as
evidence.

**The lineage detective cannot query the database.** So it cannot quietly redo
the previous agent's work with worse tools.

Narrow the toolbox and **the method comes from the constraint**, rather than
from a longer prompt that everybody hopes the model reads carefully.

## And triage is cheap on purpose, and runs first

If it says the number moved for a boring reason, **nothing else runs**. Four
expensive agents are never woken and nobody is paged for a public holiday.

## Now: what stops it doing something stupid?

This is the question every room asks, and the answer is not "we told it not to".
""")
n.code("""from agent_service.tools.warehouse import run_sql

print(run_sql.invoke({'query': 'SELECT count(*) FROM teach.silver_rides'}))
print()
print(run_sql.invoke({'query': 'DELETE FROM teach.silver_rides'}))
print()
print(run_sql.invoke({'query': 'SELECT 1; DROP TABLE teach.gold_daily'}))""")
n.md("""
### There are two guards there, and only one of them counts

**The first** is a text check: does this look like a `SELECT`. It is easy to
read, easy to explain, and easy to fool. It is a string comparison.

**The second** is one line:

```python
conn.read_only = True
```

Postgres itself refuses the write, no matter what the model asked for or how the
query was spelled. It is not a rule the agent is following. It is a thing the
agent cannot do.

> ### Whether an agent meant well is a judgement.
> ### Whether it CAN write is a fact.
>
> Build on facts. Every rule you enforce only in a prompt is a rule you are
> hoping about.

## The same idea, three more times
""")
n.code("""from agent_service.tools.repo import WRITABLE
from agent_service.tools.publish import propose_code_change, request_db_change

print('1. it can only edit these directories:', WRITABLE, '\\n')
print(propose_code_change.invoke({
    'breach_id': 'DEMO', 'summary': 'x', 'rationale': 'x',
    'path': 'tests/test_guards.py', 'old_string': 'a', 'new_string': 'b'}))""")
n.md("""
**An agent that can edit the tests which judge it is not being judged.**
""")
n.code("""print('2. a change that would not compile never reaches a human:\\n')
print(propose_code_change.invoke({
    'breach_id': 'DEMO', 'summary': 'x', 'rationale': 'x',
    'path': 'signals/board.py',
    'old_string': 'Z_THRESHOLD = 4.0', 'new_string': 'Z_THRESHOLD = = 4.0'}))""")
n.md("""
> **Whether a change is right is a judgement. Whether it compiles is a fact.**
> Facts get checked before you ask a person for an opinion.
""")
n.code("""print('3. anything that would touch data stops and waits:\\n')
print(request_db_change.invoke({
    'breach_id': 'DEMO',
    'summary': 'Backfill the missing surge values',
    'rationale': 'The value exists in the source at a path the loader now reads.',
    'statement': "UPDATE teach.bronze_driver_app SET surge = surge_backup "
                 "WHERE surge IS NULL AND app_version = '4.2.0';",
    'rows_affected_estimate': '395 rows, counted with a SELECT first',
    'reversible': 'Yes. surge_backup is untouched, so setting surge back to NULL undoes it.'}))""")
n.md("""
### It did not run that statement. **Nothing in this system will.**

A person does that, by hand, having read it. And notice what it insisted on
before it would even write the request down: the exact statement, how many rows,
and **how to undo it**.

## So the four boundaries, and how each is enforced

| It cannot | Because |
|---|---|
| write to the warehouse | the connection is opened read only |
| edit its own tests | an allow list of four directories |
| ship a change | a branch and a pull request, never a merge |
| touch data | the graph stops and waits for a person |

**None of those is a sentence in a prompt.** Every one is a property of the
system, and 192 tests check that they hold.
""")
n.code("""run('-m', 'pytest', 'tests/test_guards.py', '-q', '--no-header', '--color=no')""")

# ═══════════════════════════════════════════════════════════════════════════
n.md("""
---

# Part 6 · All of it, running unattended
### 80 to 90 minutes

You have seen every piece. Here they are together, on the break we made at the
start of the class.
""")
n.code("""run('cli.py', 'investigate', 'surge_coverage_pct')""")
n.md("""
## What just happened, in order

1. The board measured thirteen numbers and one was out of range
2. It grouped anything that moved for the same reason into **one** incident
3. **Triage** decided it was real, and whose it was
4. The **data detective** queried the warehouse and found which rows and which release
5. The **lineage detective** read the pipeline and found the contract that could not see the new field
6. **Remediation** wrote a page, raised a ticket, and proposed the change
7. The **verifier** checked whether the number had actually come back

**Nobody typed anything after step 1.**

And the thing worth sitting with: **there is no list of known problems anywhere
in this codebase.** No prompt says "if surge is missing, check app versions". The
agents were given a method and a toolbox, which is why a problem nobody has seen
before is worked exactly like this one.

## Put it back
""")
n.code("""run('break_it.py', '--fix')
run('cli.py', 'run', 'all')""")
n.md("""
---

# What to take away

Four sentences. If you remember nothing else:

> ### A pipeline that fails wakes somebody.
> ### A pipeline that succeeds while quietly carrying less data than it should wakes nobody.
> ### Every row count check you can write stays green through that.
> ### So something has to watch the numbers, and something has to work out why.

And three smaller ones you will use next week, whatever you are building:

**A number cannot raise an alarm.** Only a number plus somebody's written
opinion of what normal looks like. Writing that opinion down is the work.

**Group before you page.** One cause producing six alerts is not six problems,
and the person on call should not have to work that out first.

**Build on facts, not on prompts.** If the boundary matters, make it something
the system cannot do, rather than something you asked it not to.

---

### Where to go next

| | |
|---|---|
| notebooks **1 to 12** | build the warehouse yourself, one source at a time |
| notebooks **13 to 18** | build these two services yourself |
| notebook **19** | a guided tour of the source, in dependency order |
| `docs/` | twelve documents, one per idea |

Every file in the project opens with a docstring explaining the **decision**
rather than the syntax. Those docstrings are the real material.
""")
n.save()
