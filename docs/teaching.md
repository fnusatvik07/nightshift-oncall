# Running this as a class

Written for whoever is standing at the front.

---

## Part zero: reading it yourself, first

You cannot teach this from the README. Here is the order that works, and it is
about six hours spread over a few sittings.

### 1 · Understand the shape, before running anything  ·  40 minutes

| Read | For |
|:--|:--|
| [the README](../README.md) | the three diagrams. Look at them, do not skim them |
| [architecture.md](architecture.md) | what is running, and why nothing reads upward |
| [medallion.md](medallion.md) | what each layer is allowed to do |

Stop when you can answer this without looking: **why does bronze have no
opinions?** If you cannot, the rest will not stick, because every other decision
in the project follows from that one.

### 2 · Run it, and break it  ·  1 hour

Follow [setup.md](setup.md) exactly. Then, in a terminal, in this order:

```bash
python cli.py status          # what exists
python cli.py run all         # build the warehouse
python cli.py signals         # thirteen numbers, one breach
python cli.py invariants      # seventeen things that must never be false

python break_it.py            # move a field upstream
python cli.py run all         # everything still succeeds
python cli.py signals         # and one number has moved
python cli.py investigate surge_coverage_pct
python break_it.py --fix
```

That sequence is the entire project in ten commands. Everything else is
explanation.

### 3 · The warehouse, through the notebooks  ·  3 hours

Notebooks **1 to 12**, in order, running every cell. Do not read them, run them.

If you are short on time, **1, 2, 7 and 9** are the spine: what a pipeline is,
how one is built, why a join is dangerous, and what a silent failure looks like.

### 4 · The two services  ·  2 hours

Notebooks **13 to 18**, in order. These are the new material and the reason the
project exists in this form.

Read the source alongside them, in this order, because each file only needs the
one before it:

```
events/contract.py            the smallest file, and both services depend on it
signal_service/kpis.py        thirteen definitions. Read three, skip the rest
signal_service/evaluate.py    reading, then verdict, and why they are separate
signal_service/correlate.py   the grouping rules, and the arithmetic behind them
signal_service/scheduler.py   thirty lines, and three decisions

agent_service/tools/warehouse.py   the read only guard. Read the docstring twice
agent_service/agents.py            the five prompts. These ARE the lesson
agent_service/supervisor.py        subagents as tools
agent_service/tools/repo.py        the worktree, and the bug that made it necessary
tests/test_guards.py               what the project claims, as assertions
```

**Every file opens with a docstring explaining the decision rather than the
syntax.** Those docstrings are the teaching material; the code underneath is
just the proof that it works.

### 5 · The parts you will be asked about  ·  40 minutes

| Read | When somebody asks |
|:--|:--|
| [contracts.md](contracts.md) | "why hold a record instead of fixing it?" |
| [signals.md](signals.md) | "how do I know my baseline is right?" |
| [agents.md](agents.md) | "what stops it doing something stupid?" |
| [data.md](data.md) | "where did this incident come from?" |

---


## Before anybody arrives

```bash
docker compose -f platform/docker-compose.yml up -d
python cli.py reset
python cli.py run all
python cli.py board
```

Then **reset again**, so the first thing the room sees is an empty warehouse
filling up:

```bash
python cli.py reset
```

Have these open in tabs, in this order:

| Tab | Why |
|---|---|
| Jupyter, on notebook 1 | the lesson |
| [pgweb :8081](http://localhost:8081) | show a table appear, live |
| [Redpanda Console :8083](http://localhost:8083) | show a message land on a topic |
| [Mongo Express :8082](http://localhost:8082) | show a document's nested shape |
| [Airflow :8080](http://localhost:8080) | session 4 only |

A second screen with `watch -n 2 'python cli.py status'` on it is worth more
than any slide.

---

## Seven sessions

Each is about two hours. Notebooks are self contained, so you can stop anywhere.

| Sessions | Notebooks | About |
|:--|:--|:--|
| 1 to 4 | 1 to 12 | building the warehouse, and the tools it uses |
| 5 to 7 | 13 to 19 | the two services that watch it, and the code itself |

### Session 1 · What this job is, and bronze

**Notebooks 1, 2, 3**

Start with the problem, not the architecture. *"Finance asks what we earned last
month. Why can we not just query the app database?"* Let the room answer. They
will get "it would be slow" and usually miss the other two.

Then notebook 2, and **type it live**. Every cell is runnable code, so run the
window query and get the surprise:

```
counting back from today   : 0 rides
```

That zero is the best five minutes of the session. Everybody has lost twenty
minutes to it.

Finish with notebook 3 and the stream. If the room has never seen Kafka, do
**notebook 10 instead** and come back to 3 next time. Ten builds every word from
nothing and it is worth the whole session on its own.

**What they should leave saying:** bronze copies, it has no opinions, and a
pipeline rebuilds a window rather than a table.

### Session 2 · The awkward sources

**Notebooks 4, 5, 6**

This is where it stops being about SQL.

Notebook 4 is the strongest hour in the course. The class runs the loop, gets
**10,454 held records**, opens one document, and finds `payload.pricing.surgeFactor`
with their own eyes. Then one line fixes it.

Do not rush the sentence that follows:

> The pipeline did not fail. The rows still landed. The count was unchanged.
> Surge was just empty, on some rows, starting Tuesday.

Notebook 5 is the money one. **Three outcomes, not two.** Ask the room what to
do with a settlement whose status is an empty string, and let them argue. Both
defaults are wrong and somebody will defend each.

Notebook 6 is lighter and closes with facts versus dimensions.

**What they should leave saying:** a value you cannot read is held, never
dropped, and never defaulted to zero.

### Session 3 · Silver, gold, and finding a break

**Notebooks 7, 8, 9**

Notebook 7 has the single most useful cell in the course:

```
LEFT  JOIN :   84,689 rides
INNER JOIN :        0 rides
```

Put it on the screen and leave it there while you explain where they went. Every
person in the room has changed a `LEFT` to an `INNER` to make a query faster.

Notebook 8 is the three checkpoints. Draw them: **the contract can block, the
tests can roll back, the board blocks nothing ever.**

Notebook 9 is the finale. Take the reading, break it, watch every pipeline say
`ok`, then let the board find it. Do not explain the punchline in advance.

**What they should leave saying:** a wrong answer that runs successfully is
worse than a crash, because a crash tells you.

### Session 4 · Kafka and Airflow properly

**Notebooks 10, 11, 12**

Notebook 10 from nothing: an event, a broker, a topic, a producer, a partition,
an offset, a consumer, a group. They send a message and find it again by its
address.

Notebook 11 is short and they should drive it. Somebody in the room invents a
new field path, sends a document, and watches it get held.

Notebook 12 is the schedule. Write the DAG in cells, deploy it, then unpause it
and **wait**. The moment a run id starting `scheduled__` appears with nobody
having pressed anything is the point of the session.

**What they should leave saying:** Airflow starts programs and never touches a
row.

### Session 5 · Somebody has to watch the numbers

**Notebooks 13, 14**

Open by reminding them of notebook 9: a field moved, nothing failed, a number
stopped being true. Then ask the room, **"so who finds out?"** Let the silence
sit.

Notebook 13 is one distinction, and it is worth the whole hour:

> A KPI is a number with a definition and an owner. **It can never fire.**
> A signal is a KPI plus a baseline plus a tolerance. **That one can breach.**

Run the cell that prints yesterday's revenue and ask whether it is good or bad.
Nobody can answer, and that is the point: a number has no opinion about itself.

Notebook 14 turns the command into a service. The moment to slow down is the
`GET` versus `POST` argument: **a dashboard refreshing every ten seconds must
not be able to page somebody.** Somebody in the room will have lived that.

Finish with the fingerprint cell. A board on a one minute clock would open 1,440
investigations a day for one broken pipeline without it.

**What they should leave saying:** you cannot alert on a number, only on a
number plus somebody's opinion of what normal is.

### Session 6 · Five agents, and what they are not allowed to do

**Notebooks 15, 16, 17**

Notebook 15 builds one agent from nothing: a tool, an agent, a typed answer, and
a guard. If the room has never used an agent framework, this hour is enough on
its own.

The cell to linger on is the one that hands `DELETE FROM teach.silver_rides` to
the SQL tool. It is refused twice: once by a regex, once by the connection being
opened read only. Say the sentence:

> **Whether an agent meant well is a judgement. Whether it CAN write is a fact.**

Notebook 16 is why five and not one. Put the tool lists side by side and let
them see that the data detective cannot open a file. **An agent with every tool
will use every tool.**

Then run the whole investigation live. It takes a minute or two, which is a good
moment to ask what they think it will find. It usually finds the release.

Notebook 17 is the boundaries, and the demos are the argument: it tries to edit
a file outside the allow list and is refused, then proposes code that would not
compile and is refused again. End on `request_db_change`, which records a
statement and runs nothing.

**What they should leave saying:** the prompt is a request; the read only
connection is a constraint. Build on constraints.

### Session 7 · Running it, and reading it

**Notebooks 18, 19**

Notebook 18 is the deployment. Three containers, and the demo is: break
something, then touch nothing. Put `docker logs -f nightshift-signal-scheduler`
on the screen and talk for sixty seconds while it catches up.

Notebook 19 is the one to use when somebody says *"but how is it actually
built?"*. It walks the source in dependency order, printing real code out of
real files. Use it as the closing session, or hand it to the person on your team
who has to maintain this after the course.

**What they should leave saying:** every file opens with a docstring explaining
the decision rather than the syntax, and those docstrings are the material.

---

## Two stories worth telling

Both are bugs this project committed against itself, and both land better than
any invented example, because the room can see the fix in the repository.

**The shared working tree.** The code change tool ran `git checkout` in the
project's own directory. One investigation worked. Two, reproduced in a
throwaway repo, gave: thread one reporting *committed* with the original file on
its branch, thread two reporting *commit failed* with its change on its branch.
A success report containing no change.

**The tests that opened seven pull requests.** The concurrency tests call the
real code, the target repository is configurable, and it pointed at a live one.
The tests passed. Nothing failed. The side effect was somewhere else entirely.

> A test that can open a pull request is not a test, it is a deployment.

Ask the room what these two have in common with the surge field moving. The
answer is the whole course: **nothing failed, and the wrong answer looked
exactly like the right one.**

---

## Questions you will get

**"Why not just use dbt?"**
Because you cannot see what "delete the window then insert it back in one
transaction" means when a tool does it for you. Learn the mechanic, then let a
tool do it.

**"Is this how it works in a real company?"**
The shapes are exactly right. Real estates have more sources, more layers, and a
cloud warehouse instead of local Postgres. Nothing here would embarrass you in a
design review.

**"What if the source has no timestamp?"**
Then you cannot build a window on it and you are looking at a full snapshot
comparison, which is a different technique with different costs. Say so out loud
rather than pretending.

**"Why hold a record instead of fixing it?"**
Because fixing it means guessing, and a guess in bronze is indistinguishable
from a fact by the time it reaches gold.

**"How do I know my baseline is right?"**
You do not, at first. You watch the board for two weeks and move the numbers
that cry wolf. A signal nobody reads is worse than no signal.

---

## Things that go wrong live

| | |
|---|---|
| a notebook cell fails on a stale variable | notebooks assume top to bottom. Restart the kernel and run all |
| the stream reads nothing | somebody already ran it. `python cli.py reset`, then run again |
| a container died | `docker ps -a \| grep 137`. Docker needs 6 GB |
| the numbers differ from your notes | check `KERB_DAYS` and `KERB_TRIPS_PER_DAY` in `.env` |
| you break something beyond repair | `python cli.py reset && python cli.py run all`. Ninety seconds |

**Rehearse the reset in front of them once**, early. A room that knows nothing
is fragile asks better questions.

---

## If you only have one hour

Notebooks **1, 2 and 9**. Why a warehouse exists, how a pipeline is really
built, and what a silent failure looks like.

## If you only have one day

Notebooks **1, 2, 9, 13, 16 and 18**. That is the entire argument end to end: a
warehouse, a silent failure, the thing that notices, the thing that
investigates, and the whole lot running unattended.

## If somebody has to maintain it afterwards

Notebook **19**, and then the source in the order it names. Six hours, and they
will be able to add a KPI, an invariant or a tool without asking anybody.
