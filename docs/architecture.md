# The architecture

What is running, why it is shaped this way, and how a row travels from a source
system to a number on a finance report.

---

## The estate

Nine containers, in three groups.

```mermaid
flowchart TB
    subgraph LAPTOP["YOUR LAPTOP"]
        JUP["Jupyter<br/>the twelve notebooks"]
        CLI["cli.py<br/>status · run · board · reset"]
        SEED["seed/<br/>generates the world"]
    end

    subgraph SYSTEMS["THE SYSTEMS THE COURSE READS FROM"]
        direction LR
        PG[("Postgres :5434<br/><b>kerb</b> the app db<br/><b>paynimbus</b> the processor<br/><b>airflow</b> its own notes")]
        MG[("MongoDB :27019<br/>driver_app_events")]
        RP[/"Redpanda :19092<br/>kerb.trips.lifecycle"/]
        MO[("MinIO :9000<br/>kerb-landing bucket")]
        PN["PayNimbus :8088<br/>REST, reads paynimbus"]
    end

    subgraph OPS["RUNNING IT, AND LOOKING AT IT"]
        direction LR
        AF["Airflow :8080"]
        PW["pgweb :8081"]
        ME["mongo-express :8082"]
        RC["redpanda console :8083"]
    end

    SEED ==> SYSTEMS
    JUP --> SYSTEMS
    CLI --> SYSTEMS
    AF -->|runs the same commands you type| SYSTEMS
    PW --> PG
    ME --> MG
    RC --> RP
    PN --> PG

    classDef me fill:#EFF4FF,stroke:#1D4ED8,stroke-width:2px,color:#111
    classDef sys fill:#F4F4F5,stroke:#111,stroke-width:1.5px,color:#111
    classDef ops fill:#ECFDF5,stroke:#047857,stroke-width:2px,color:#111
    class JUP,CLI,SEED me
    class PG,MG,RP,MO,PN sys
    class AF,PW,ME,RC ops
```

### Why one Postgres holds three databases

`kerb` is the app's system of record. `paynimbus` is a different company's
ledger. `airflow` is an orchestrator's private bookkeeping.

They are separate **databases**, not separate schemas, so that nothing can
quietly join across the boundary. KERB cannot read the processor's ledger, the
same way it could not read a real processor's ledger, and the only route to that
data is the HTTP API. That constraint is the entire subject of notebook 5.

Running them on one Postgres instance is a convenience: three instances on a
laptop is a support burden nobody needs.

### Why Redpanda and not Kafka

It speaks the Kafka protocol, so every line of Kafka code in this course is real
Kafka code, and it is one container instead of three with no ZooKeeper. Swap the
broker address for a real Kafka cluster and nothing else changes.

### Why MinIO

It speaks the S3 API. The file pipeline in notebook 6 is the same code you would
write against real S3 with a different endpoint.

---

## How a ride becomes a number

One ride happens, and five systems record a different part of it. That is not a
teaching contrivance: it is what an estate looks like once more than one team
has shipped something.

```mermaid
sequenceDiagram
    autonumber
    participant R as Rider
    participant APP as KERB app
    participant PG as Postgres<br/>kerb.trips
    participant KF as Kafka<br/>trips.lifecycle
    participant MG as MongoDB<br/>driver app
    participant PN as PayNimbus
    participant REG as Regulator

    R->>APP: taps Book
    APP->>PG: INSERT a row, status requested
    APP->>KF: requested
    APP->>MG: trip_offer, with the surge, nested
    APP->>KF: accepted
    APP->>KF: driver_arrived
    APP->>KF: started
    Note over APP,PG: the ride happens
    APP->>PG: UPDATE status completed
    APP->>KF: completed, carrying the fare
    APP->>MG: trip_end
    APP->>PG: INSERT a payment, captured
    APP-->>PN: the charge, sent to the processor
    Note over PN: two days later the money lands
    REG-->>REG: overnight, writes a CSV of the day
```

Five records of one ride, and they do not agree:

| System | What it knows | What it does not |
|---|---|---|
| `kerb.trips` | the ride happened, and how it ended | the fare, the surge, whether the money arrived |
| the stream | every step, in order, with the fare | anything about payment |
| MongoDB | the surge, and which app version sent it | anything about money or zones |
| PayNimbus | whether the money actually arrived | which ride it was for |
| the regulator's file | an audited copy of yesterday | today |

**Silver exists to make those five agree.** That is the whole job.

---

## The medallion, and where the checkpoints sit

```mermaid
flowchart LR
    SRC["the six sources"] --> GATE{{"THE CONTRACT<br/>per record, inside the pipeline<br/><b>can block</b>"}}
    GATE -->|understood| BRONZE["BRONZE<br/>a faithful copy"]
    GATE -->|not understood| Q[["QUARANTINE<br/>the record, the reason,<br/>the original payload"]]
    BRONZE --> TX{{"THE TRANSACTION<br/>after the write, before the commit<br/><b>can roll back</b>"}}
    TX --> SILVER["SILVER<br/>one clean row per ride"]
    SILVER --> GOLD["GOLD<br/>one row per day"]
    GOLD --> BOARD{{"THE SIGNAL BOARD<br/>on a clock, outside everything<br/><b>blocks nothing, ever</b>"}}
    BRONZE -.-> BOARD
    SILVER -.-> BOARD
    Q -.-> BOARD

    classDef gate fill:#FFFBEB,stroke:#B45309,stroke-width:2px,color:#111
    classDef layer fill:#EFF4FF,stroke:#1D4ED8,stroke-width:2px,color:#111
    classDef good fill:#ECFDF5,stroke:#047857,stroke-width:2px,color:#111
    classDef bad fill:#FEF2F2,stroke:#B91C1C,stroke-width:2px,color:#111
    class GATE,TX,BOARD gate
    class BRONZE,SILVER layer
    class GOLD good
    class Q bad
```

Three checkpoints, and people collapse them into one word, quality, and then
argue past each other. They are not the same thing. See
[contracts.md](contracts.md).

---

## Where the code lives

```
pipelines/
├── lib/
│   ├── config.py       every address in the system. One file, on purpose
│   └── run.py          the four rules: run log, quarantine, write_window
├── p1_bronze_trips.py         a database table
├── p2_bronze_events.py        a stream
├── p3_bronze_driver_app.py    a document store
├── p4_bronze_settlements.py   somebody else's API
├── p5_bronze_regulator.py     files in object storage
├── p6_bronze_zones.py         a dimension, replaced whole
├── p7_silver_rides.py         the join
└── p8_gold_daily.py           the aggregate
```

**One file per pipeline, and one pipeline per source.** Six sources, six bronze
pipelines. Not one pipeline with six branches, because the day one of them
breaks you want to rerun exactly that one.

**Nothing shared except `lib/`.** A pipeline that imports another pipeline has
made them one deployment, and you will find that out at the worst moment.

### config.py, and the one flag that matters

```python
load_dotenv(ROOT / ".env", override=False)
```

`override=False` means a variable already set in the environment wins. On your
laptop `.env` supplies `POSTGRES_HOST=localhost`. Inside the Airflow container,
compose supplies `POSTGRES_HOST=postgres`, and that wins.

**Not one line of pipeline code changes between the two.** Every address in the
project goes through this file for exactly that reason.

### run.py, and the four rules

Every pipeline gets these without writing them again:

```python
with Run("p1_bronze_trips") as r:        # 1. observable: a row in teach.runs
    r.rows_in = len(rows)
    r.quarantine(payload, reason)         # 2. honest: held, not dropped

    with write_window(TABLE, "trip_date", lo, hi) as cur:
        cur.executemany(INSERT, keep)     # 3. idempotent  4. atomic
```

`write_window` deletes the window it is about to rebuild and inserts the new
rows **in the same transaction**. Run it twice and you get the same table, not
double the rows. Kill it halfway and the delete rolls back with the insert, so a
reader never sees a table with a hole in it.

---

## Orchestration

`airflow/dags/teach_pipelines.py` is a real DAG in a real scheduler.

```mermaid
flowchart LR
    subgraph B["six tasks that share nothing, so all six run at once"]
        direction TB
        T1[p1_bronze_trips]
        T2[p2_bronze_events]
        T3[p3_bronze_driver_app]
        T4[p4_bronze_settlements]
        T5[p5_bronze_regulator]
        T6[p6_bronze_zones]
    end
    T1 & T2 & T3 & T4 & T5 & T6 --> S[p7_silver_rides] --> G[p8_gold_daily] --> SB[signal_board]

    classDef bronze fill:#EFF4FF,stroke:#1D4ED8,stroke-width:2px,color:#111
    classDef later fill:#ECFDF5,stroke:#047857,stroke-width:2px,color:#111
    classDef board fill:#FFFBEB,stroke:#B45309,stroke-width:2px,color:#111
    class T1,T2,T3,T4,T5,T6 bronze
    class S,G later
    class SB board
```

Airflow derives all of that from one line:

```python
bronze >> silver >> gold
```

And the guarantee it buys is absolute: **gold can never be built from a silver
table that failed to refresh.** Not "should not". Cannot. See
[orchestration.md](orchestration.md).

`airflow/dags/` in this repo is mounted straight into the scheduler, so saving a
file there **is** deploying it.

---

## What is deliberately not here

**No dbt, no Spark, no cloud warehouse.** Every one of them would be a
reasonable production choice and every one would hide the thing being taught.
You cannot see what `delete the window then insert it back in one transaction`
means when a tool does it for you.

**No retry framework, no circuit breaker.** They belong in a shared client. Put
them in a teaching pipeline and the lesson disappears under plumbing.

**No streaming compute.** The stream is read in batches by a pipeline that
finishes. Continuous processing is a different course.
