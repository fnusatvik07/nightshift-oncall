# Setting it up

The short version is in the [README](../README.md). This is the long version,
with every failure we have actually hit.

If you use Claude Code, [CLAUDE.md](../CLAUDE.md) is written to be executed:
open the repo and say *"set this project up locally for me"*.

---

## What you need

| | Minimum | Why |
|---|---|---|
| **Docker Desktop** | any recent version | nine containers |
| **Docker memory** | **6 GB** | Airflow alone wants 1.5 GB |
| **Disk** | about 6 GB free | 2 GB of images, plus the data |
| **Python** | 3.11 | the code uses `X \| None` and modern `psycopg` |
| **Time** | 10 minutes | most of it downloading images, once |

### Raising Docker's memory

This is the single most common reason a first run fails, so do it before
anything else.

**macOS and Windows:** Docker Desktop, the gear icon, Resources, Memory. Drag it
to 6 GB or more. Apply and restart.

**Linux:** Docker uses the host's memory directly, so there is nothing to set.
Just make sure the machine has it.

What happens if you skip this: everything starts, everything looks fine, and
then partway through seeding the kernel kills Redpanda for using too much
memory. You find out much later, as a `Connection refused` on port 19092 that
makes no sense. Check for it with:

```bash
docker ps -a --filter "status=exited" --format '{{.Names}}\t{{.Status}}'
```

`Exited (137)` means the kernel killed it. Always memory.

---

## The five steps

### 1. Python

```bash
git clone https://github.com/fnusatvik07/nightshift-build.git
cd nightshift-build

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Check it took:

```bash
python -c "import psycopg, confluent_kafka, pymongo, minio; print('imports ok')"
```

<details>
<summary>If <code>confluent-kafka</code> fails to install</summary>

<br>

On Apple Silicon and most Linux distributions there is a prebuilt wheel and this
does not happen. If you do end up compiling, you need `librdkafka`:

```bash
brew install librdkafka                 # macOS
sudo apt-get install librdkafka-dev     # Debian and Ubuntu
```

</details>

### 2. Settings

```bash
cp .env.example .env
```

Nothing in it needs changing. The values match the containers.

**One idea in that file is worth understanding**, because it explains something
that otherwise looks like magic. `pipelines/lib/config.py` loads `.env` like
this:

```python
load_dotenv(ROOT / ".env", override=False)
```

`override=False` means **a variable already set in the environment wins**. On
your laptop nothing is set, so `.env` supplies `POSTGRES_HOST=localhost`. Inside
the Airflow container, compose sets `POSTGRES_HOST=postgres`, so that wins
instead.

The same pipeline code therefore runs in both places, unchanged. That is the
whole trick, and it is one flag.

### 3. Check your ports

A port clash produces a confusing error much later, so look first:

```bash
for p in 5434 27019 19092 9000 9001 8080 8081 8082 8083 8088; do
  lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && echo "port $p is in use"
done
echo "checked"
```

If one is taken, change that single variable in `.env`. Every address in the
project is read from there, so that really is enough.

| Variable | Default | Service |
|---|---|---|
| `POSTGRES_PORT` | 5434 | Postgres |
| `MONGO_PORT` | 27019 | MongoDB |
| `REDPANDA_PORT` | 19092 | Redpanda |
| `MINIO_PORT` | 9000 | MinIO API |
| `MINIO_CONSOLE_PORT` | 9001 | MinIO browser UI |
| `PARTNER_API_PORT` | 8088 | PayNimbus |
| `AIRFLOW_PORT` | 8080 | Airflow |
| `PGWEB_PORT` | 8081 | pgweb |
| `MONGO_EXPRESS_PORT` | 8082 | Mongo Express |
| `REDPANDA_CONSOLE_PORT` | 8083 | Redpanda Console |

If you change `MONGO_PORT`, remember `MONGO_URI` also carries the port. It is
the one place a value appears twice.

### 4. Start the estate

```bash
docker compose -f platform/docker-compose.yml up -d
```

The first run pulls about 2 GB and builds two images. Give it several minutes
and do not interrupt it.

Then watch for health, rather than guessing:

```bash
watch -n 3 'docker compose -f platform/docker-compose.yml ps'
```

You want `healthy` against Postgres, Mongo, Redpanda, MinIO and the partner API.
**Airflow takes 60 to 120 seconds longer** than the rest, because it migrates
its own database on first boot. It is not needed until notebook 12.

### 5. Generate the data

```bash
python -m seed
```

About 40 seconds for a month of trading:

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

`--quick` gives you 7 days instead of 30, in about 10 seconds, and every lesson
still works.

> **Why the data ends two weeks ago.** It is deliberate. A pipeline that asks
> for "the last seven days counting back from today" reads exactly nothing, and
> notebook 2 walks into that on purpose before showing you how to anchor a
> window on the data instead of on the clock.

---

## Prove it works

```bash
python cli.py status
python cli.py run all
python cli.py board
```

A correct board looks like this:

```
  signal board   6 signals, 1 breached

    ok    pipelines_failing        0.000 runs
  BREACH  records_held         1,605.000 rows
    ok    rides_per_day       13,483.000 rides
    ok    events_per_ride          4.770
    ok    rides_missing_fare       0.000 rides
    ok    surge_missing_pct        0.000 %
```

**That one breach is supposed to be there.** The payment processor sends some
settlements with an empty status, the contract refuses them, and they sit in
quarantine waiting for a human. It is a real open issue in the estate, not a
setup problem. Notebook 5 is about it.

---

## Open the notebooks

```bash
jupyter lab notebooks/
```

Start at `01-what-is-a-pipeline.ipynb` and work down.

Run Jupyter **from the activated virtual environment**. If you do not, the
kernel will not find `pipelines` and every notebook fails on its first cell.

---

## Starting again

| You want | Command |
|---|---|
| the warehouse empty, sources untouched | `python cli.py reset` |
| different data, same containers | `python -m seed --force` |
| the containers gone, data kept | `docker compose -f platform/docker-compose.yml down` |
| everything gone, including the data | `docker compose -f platform/docker-compose.yml down -v` |

After `down -v` you are back to step 4, including the seed.

---

## Day to day

```bash
docker compose -f platform/docker-compose.yml stop     # end of the day
docker compose -f platform/docker-compose.yml start    # next morning
```

The data lives in Docker volumes, so it survives a stop, a restart, and a
reboot. You only lose it with `down -v`.
