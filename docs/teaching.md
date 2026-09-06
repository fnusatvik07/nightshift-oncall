# Running this as a class

Written for whoever is standing at the front. The notebooks carry the material;
this is about pacing, what to put on the screen, and what people actually ask.

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

## Four sessions

Each is about two hours. Notebooks are self contained, so you can stop anywhere.

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

Notebooks 1, 2 and 9.

The first says why a warehouse exists. The second builds a real pipeline with
every rule in it. The ninth breaks it and finds the break.

That is the whole argument, and it fits in an hour.
