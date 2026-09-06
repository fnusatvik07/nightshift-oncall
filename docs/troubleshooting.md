# When it does not work

Ordered by how often it actually happens.

---

## Start here

Three commands answer most questions:

```bash
docker compose -f platform/docker-compose.yml ps          # is it all up and healthy
docker ps -a --filter "status=exited" --format '{{.Names}}\t{{.Status}}'
python cli.py status                                      # what exists, what ran last
```

---

## A container says `Exited (137)`

**The kernel killed it for using too much memory.** Almost always Redpanda,
because it is the hungriest.

```bash
docker ps -a --format '{{.Names}}\t{{.Status}}' | grep 137
```

**Fix:** give Docker more memory. Docker Desktop, Settings, Resources, Memory,
6 GB or more, then Apply and restart. Then:

```bash
docker compose -f platform/docker-compose.yml up -d
```

This is the single most common failure, and its symptom usually shows up much
later as `Connection refused` on port 19092, long after the actual death.

---

## `Connection refused` on port 19092

Redpanda is not running. See above, then:

```bash
docker compose -f platform/docker-compose.yml up -d redpanda
docker logs nightshift-redpanda --tail 30
```

The pipeline will now tell you rather than pretending: `p2_bronze_events` fetches
topic metadata before reading, so a dead broker fails the run instead of quietly
reporting `ok  read 0`.

---

## `port is already allocated`

Something else on your machine is using that port.

```bash
lsof -nP -iTCP:5434 -sTCP:LISTEN        # or whichever port it named
```

**Fix:** change that one variable in `.env`, then `up -d` again. Every address
in the project is read from `.env`, so one line is genuinely enough.

If you change `MONGO_PORT`, remember `MONGO_URI` carries the port too. It is the
one value that appears twice.

---

## `KeyError: 'POSTGRES_HOST'`

There is no `.env`.

```bash
cp .env.example .env
```

---

## `psycopg.OperationalError: connection failed`

Postgres is not ready yet, or is not running.

```bash
docker compose -f platform/docker-compose.yml ps postgres
docker logs nightshift-postgres --tail 20
```

Wait for `healthy`. Retrying faster does not make a database start sooner.

---

## Pipelines run but write zero rows

The estate was never seeded.

```bash
python cli.py status        # does kerb.trips have anything in it
python -m seed
```

---

## `relation "teach.bronze_trips" does not exist`

A pipeline ran before the ones it depends on. `p7_silver_rides` needs all six
bronze tables.

```bash
python cli.py run all       # uses the right order
```

---

## The stream pipeline reads zero messages after a reset

You dropped the tables but not the consumer group.

**Your position in a stream lives on the broker, not in your database.** Drop
the tables without deleting the group and the pipeline wakes up believing it has
already read everything, reads nothing, reports success, and leaves you with an
empty table and no error.

`python cli.py reset` does both. If you dropped the schema by hand, delete the
groups too:

```bash
python - <<'PY'
from confluent_kafka.admin import AdminClient
from pipelines.lib.config import KAFKA
a = AdminClient({"bootstrap.servers": KAFKA})
groups = [g.group_id for g in a.list_consumer_groups(request_timeout=10).result().valid
          if g.group_id.startswith(("teach-", "notebook-", "just-looking"))]
for g, fut in (a.delete_consumer_groups(groups, request_timeout=15).items() if groups else []):
    fut.result(); print("deleted", g)
print("groups now:", [g.group_id for g in a.list_consumer_groups(request_timeout=10).result().valid])
PY
```

That bug cost an hour while this course was being built, which is why it has its
own paragraph in notebook 9.

---

## Notebook kernel cannot import `pipelines`

Jupyter was started outside the virtual environment.

```bash
source .venv/bin/activate
jupyter lab notebooks/
```

Every notebook's first cell does `sys.path.insert(0, '.')` and imports `nb`,
which adds the project root. That only works if the kernel has the project's
packages installed, which means the venv.

---

## Airflow shows no DAGs

The scheduler has not rescanned yet. It looks every few minutes.

```bash
python cli.py deploy
```

If they still do not appear, the file probably raises on import, and **a DAG
file that raises does not become a broken DAG, it becomes no DAG at all**:

```bash
docker exec nightshift-airflow airflow dags list-import-errors
```

---

## An Airflow task fails but the pipeline works on my laptop

Read the task log first. Every task runs the same command you would type:

```bash
docker exec nightshift-airflow bash -c \
  "cd /opt/kerb/teach && python -m pipelines.p1_bronze_trips --days 7"
```

If that works and the DAG does not, the difference is environment. The compose
file sets `POSTGRES_HOST=postgres` and friends for the container, because
`localhost` inside a container is the container itself.

---

## Airflow will not start

It takes 60 to 120 seconds on first boot because it migrates its own database.

```bash
docker logs nightshift-airflow --tail 40
```

If it is stuck on the database, check Postgres is healthy and that the `airflow`
database exists:

```bash
docker exec nightshift-postgres psql -U kerb -tAc "SELECT datname FROM pg_database"
```

You should see `kerb`, `paynimbus` and `airflow`. If `airflow` is missing, the
init scripts did not run, which happens when the volume already existed from a
previous project. Start again:

```bash
docker compose -f platform/docker-compose.yml down -v
docker compose -f platform/docker-compose.yml up -d
python -m seed
```

---

## The board shows `records_held` breached

**That is correct.** The payment processor genuinely sends settlements with an
empty status, the contract genuinely refuses them, and they sit in quarantine
waiting for a human.

It is a real open issue in the estate, not a setup problem. See what is being
held:

```sql
SELECT pipeline, reason, count(*) FROM teach.quarantine GROUP BY 1, 2 ORDER BY 3 DESC;
```

For a run with nothing held, set `PN_EMPTY_STATUS_SHARE=0` in `.env` and restart
the partner API.

---

## The numbers on my screen differ from the notes

The seed is deterministic, so the usual causes are:

- a different `KERB_SEED`, `KERB_DAYS` or `KERB_TRIPS_PER_DAY` in `.env`
- `--quick`, which is 7 days of 2,000 rather than 30 of 12,000
- the dataset anchors on **today minus 14 days**, so the calendar dates move as
  the weeks pass. The shape does not

---

## Everything is broken and I want to start again

```bash
docker compose -f platform/docker-compose.yml down -v      # containers and data gone
docker compose -f platform/docker-compose.yml up -d
python -m seed
python cli.py run all
python cli.py board
```

About four minutes, most of it waiting for containers. Nothing outside this
project is touched.

---

## Still stuck

Collect this before asking anybody:

```bash
docker compose -f platform/docker-compose.yml ps
docker ps -a --format '{{.Names}}\t{{.Status}}'
docker info --format 'memory: {{.MemTotal}}'
python --version
python cli.py status
```
