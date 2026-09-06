# CLAUDE.md

Instructions for Claude Code working in this repository.

This file has two halves. The first is a **setup procedure**, written to be
executed rather than read: if someone says *"set this project up locally for
me"*, follow it top to bottom, verifying as you go. The second half is how to
work in this codebase without breaking its conventions.

---

# Part one: setting the project up

## What you are setting up

NIGHTSHIFT is a data engineering course that runs entirely on the user's
machine. Nine Docker containers make up a small but real estate: Postgres,
MongoDB, Redpanda, MinIO, a partner REST API, Airflow, and three browser GUIs.
A generator fills all of them with one consistent month of trading. Eight Python
pipelines then copy that into a warehouse.

Nothing is mocked and nothing is a simulation. That is why setup is worth doing
carefully.

## Step 0. Check the prerequisites before doing anything

Run these and read the answers:

```bash
docker --version
docker compose version
docker info --format '{{.MemTotal}}'
python3 --version
```

Three things have to be true, and if any is not, stop and tell the user rather
than pressing on:

| Requirement | Why |
|---|---|
| Docker is installed **and running** | `docker info` fails if the daemon is down. On macOS and Windows that means Docker Desktop is not open |
| Docker has **at least 6 GB** of memory | `MemTotal` is in bytes, so you want roughly `6000000000` or more. Nine containers, and Airflow alone takes 1.5 GB. This is the single most common cause of a failed first run |
| Python is **3.11 or newer** | the code uses `X | None` type syntax and modern `psycopg` |

If Docker has less than 6 GB, tell the user to raise it in Docker Desktop under
Settings, Resources, Memory, and to restart Docker. Do not try to work around
it: the symptom is Redpanda being killed by the kernel partway through, which
looks like a mysterious `Connection refused` on port 19092 much later on.

## Step 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Verify it took:

```bash
python -c "import psycopg, confluent_kafka, pymongo, minio; print('imports ok')"
```

## Step 2. Settings

```bash
cp .env.example .env
```

Do not edit it unless a port is taken. The defaults match the compose file.

Check the ports are free before starting anything, because a port clash gives a
confusing error much later:

```bash
for p in 5434 27019 19092 9000 9001 8080 8081 8082 8083 8088; do
  lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && echo "port $p is in use"
done
echo "port check done"
```

If a port is taken, change that one variable in `.env` and nothing else. Every
address in the project is read from `.env` by `pipelines/lib/config.py`, so
changing it there is genuinely enough.

## Step 3. Start the estate

```bash
docker compose -f platform/docker-compose.yml up -d
```

The first run pulls roughly 2 GB of images and builds two of them, so give it
several minutes. Do not use a short timeout and do not interrupt it.

Then **wait for health properly**, rather than sleeping a fixed number of
seconds:

```bash
python - <<'PY'
import subprocess, time
need = {"nightshift-postgres", "nightshift-mongo", "nightshift-redpanda",
        "nightshift-minio", "nightshift-partner-api"}
for _ in range(60):
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
                         capture_output=True, text=True).stdout
    healthy = {l.split("\t")[0] for l in out.splitlines()
               if "healthy" in l and l.split("\t")[0] in need}
    print(f"  healthy: {len(healthy)}/{len(need)}")
    if healthy == need:
        print("estate is up")
        break
    time.sleep(5)
else:
    print("TIMED OUT. Run: docker compose -f platform/docker-compose.yml logs --tail 40")
PY
```

Airflow takes longer than the rest, usually 60 to 120 seconds, because it
migrates its own database on first boot. It is not needed until notebook 12, so
do not block on it here.

## Step 4. Generate the data

```bash
python -m seed
```

Expect about 40 seconds and output like this:

```
  seeding 30 days, 12,000 rides a day
  2026-08-16 to 2026-09-14   (the dataset ends 14 days before today, on purpose)
  zones, drivers and riders     61 zones, 2,800 drivers, 40,000 riders
  rides and payments            365,060 rides, 324,877 payments
  settlements                   298,920 settlements
  driver app documents          686,285 documents
  ride lifecycle events         1,741,282 events
  the regulator's files         30 gzipped CSV files
```

Use `--quick` if the user wants a faster first run: 7 days instead of 30.

If it says the database already holds rides, that is the guard working. Use
`--force` only if the user actually wants to regenerate.

## Step 5. Run the pipelines and verify

```bash
python cli.py status
python cli.py run all
python cli.py board
```

**What a correct result looks like.** All eight pipelines print `ok`, and the
board prints six signals of which exactly one, `records_held`, is breached.

That breach is **correct and expected**. The payment processor genuinely sends
some settlements with an empty status, and the contract genuinely refuses them.
Tell the user it is meant to be there. Do not try to fix it.

```
  signal board   6 signals, 1 breached
    ok    pipelines_failing        0.000
  BREACH  records_held         1,605.000
    ok    rides_per_day       13,483.000
    ok    events_per_ride          4.770
    ok    rides_missing_fare       0.000
    ok    surge_missing_pct        0.000
```

## Step 6. The two services

The warehouse is only half the project. Two services watch it.

```bash
docker compose -f platform/docker-compose.yml up -d signal-api signal-scheduler agent
```

Verify both:

```bash
curl -s localhost:8091/health     # {"ok":true,"kpis":13,...}
curl -s localhost:8092/health     # {"ok":true,"model":"openai:...",...}
```

The agent service needs a model key. `OPENAI_API_KEY` in `.env` is enough; the
compose file passes `.env` through with `env_file`. Without it, the signal board
still works and the agent service starts but every investigation fails.

Confluence is **optional**. With no Atlassian credentials the agents write
markdown into `artifacts/` instead, and everything else is identical.

## Step 7. Hand over

Tell the user, in this order:

1. `jupyter lab notebooks/` and start at `01-what-is-a-pipeline.ipynb`. The
   kernel is **NIGHTSHIFT oncall**; if it is missing, run
   `python -m ipykernel install --user --name nightshift-oncall --display-name "NIGHTSHIFT oncall"`
   from the activated venv
2. The browser GUIs worth having open: Airflow at 8080, pgweb at 8081, Mongo
   Express at 8082, Redpanda Console at 8083, MinIO at 9001
3. `python cli.py reset` puts the warehouse back to empty and never touches a
   source system, so nothing they do is dangerous

## When setup fails

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop is not running | start it, wait for the whale icon to settle |
| A container is `Exited (137)` | the kernel killed it for memory | raise Docker's memory to 6 GB or more, then `up -d` again |
| `Connection refused` on 19092 | Redpanda died, usually memory, see above | `docker compose -f platform/docker-compose.yml up -d redpanda` |
| `port is already allocated` | something else uses that port | change the one port in `.env`, then `up -d` again |
| `psycopg.OperationalError` on connect | Postgres is not healthy yet | wait for the healthcheck, do not just retry faster |
| `KeyError: 'POSTGRES_HOST'` | `.env` is missing | `cp .env.example .env` |
| Pipelines run but write 0 rows | the estate was never seeded | `python -m seed` |
| `relation "teach.bronze_trips" does not exist` | pipelines run out of order | `python cli.py run all`, which uses the right order |
| Airflow shows no DAGs | the scheduler has not rescanned | `python cli.py deploy` |
| Notebook kernel cannot import `pipelines` | Jupyter started outside the venv | run `jupyter lab` from the activated venv |

Full detail is in [docs/troubleshooting.md](docs/troubleshooting.md).

---

# Part two: working in this codebase

## What this repository is for

It is teaching material that happens to be working software. Both halves of that
matter. Code that runs but cannot be read in front of a room has failed here,
and so has a beautiful explanation of something that does not run.

## The conventions, and why they exist

**Every pipeline obeys four rules.** They are written once in
`pipelines/lib/run.py` and never re-implemented:

1. **Idempotent.** Running it twice is the same as running it once. That is
   `write_window`, which deletes the window and inserts it back inside one
   transaction, or a primary key plus `ON CONFLICT DO NOTHING`.
2. **Atomic.** All of it lands or none of it does. Never leave a reader looking
   at a half written table.
3. **Honest.** A value you cannot read is **held**, with the reason and the
   original payload, never dropped and never defaulted.
4. **Observable.** Every run writes a row to `teach.runs` saying what happened.

**No address is ever hardcoded.** Everything goes through
`pipelines/lib/config.py`, which loads `.env` with `override=False` so a real
environment variable wins. That single flag is what lets identical code run on a
laptop, where Postgres is at `localhost:5434`, and inside the Airflow container,
where it is at `postgres:5432`.

**Pipelines are divided by step markers**, like this:

```python
# ══ STEP 3 · Check every record against the contract ══
```

`notebooks/nb.py` parses those markers, so a marker is load bearing. If you add
or renumber one, check the notebooks still line up.

**Comments explain the decision, not the syntax.** The pipelines carry a high
comment density on purpose, because they are read aloud. Write about why a
`LEFT JOIN` is a `LEFT JOIN`, not about what a join is.

**The agents propose, never apply.** Every tool that could change something is
either read only at the connection level, limited to two directories, or gated
behind a human interrupt. If you add a tool, decide which of those three it is
before writing it, and never rely on the system prompt to hold a boundary.

**No em dashes anywhere.** Not in code comments, not in markdown, not in
notebook prose. Use a comma, a colon, or a full stop.

**No generated images.** Diagrams are built from source in `diagrams/` and
exported to PNG, or written as mermaid in markdown. Photography and brand logos
only, never generated art.

## Editing the notebooks

**Do not edit the `.ipynb` files by hand.** They are generated:

```bash
cd notebooks
python build_nb.py            # regenerates all twelve from build_nb.py
```

Edit `notebooks/build_nb.py`, regenerate, then execute the affected notebook to
prove it still runs:

```bash
jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=900 \
  --output /tmp/check.ipynb 07-silver-joining-it-together.ipynb
```

Commit notebooks **with their outputs cleared**, so the class watches them run:

```bash
jupyter nbconvert --clear-output --inplace notebooks/*.ipynb
```

## Editing the diagrams

Each `diagrams/*_diagrams.py` builds one drawio file and exports PNGs into
`notebooks/img/`. They need the `drawio` CLI installed. If you do not have it,
do not delete the PNGs: leave the existing ones alone.

## Changing the data

`seed/` generates everything. Two constraints:

**It must stay deterministic.** The same `--seed` gives the same rides, fares
and incidents on any machine. A lesson quoting a number that differs on a
student's screen is worse than a lesson quoting no numbers.

**The incidents are load bearing.** Notebook 4 depends on release 4.2.0 moving
the surge field to `payload.pricing.surgeFactor`, on that release sitting at the
end of the month, and on exactly four documents landing at
`pricing.surge_multiplier`. Notebook 5 depends on a share of settlements
arriving with an empty status. Notebook 7 depends on cancelled rides having no
`completed` event. Change any of those and the lesson stops working.

If you regenerate, always use `--force`, which clears the Kafka topics too. A
stream is not a table: truncating Postgres does nothing to the broker, and
leaving the previous generation's events behind gives you a topic that disagrees
with the database it describes.

## Before you say something works

Run it. This project has caught real bugs only because everything was executed
end to end rather than reasoned about:

```bash
python -m pyflakes pipelines seed signals signal_service agent_service events \
                   cli.py reset.py break_it.py
python cli.py reset && python cli.py run all && python cli.py board

# and for the services, the end to end test that actually means something:
python break_it.py && python cli.py run all
python cli.py signals            # surge_coverage_pct should breach
python cli.py investigate surge_coverage_pct
python break_it.py --fix
```

And for a change touching the notebooks, execute all twelve in order against a
freshly reset warehouse. That is the only test that means anything here.

## Git

Commits are authored by the repository owner, never by Claude. Do not add
`Co-Authored-By` trailers or any other Claude attribution to commits in this
repository.
