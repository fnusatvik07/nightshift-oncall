"""The Airflow DAG that runs the eight pipelines from this course.

WHAT AIRFLOW IS, IN ONE SENTENCE
    Airflow is a program whose only job is to start other programs, in the
    right order, at the right time, and to remember what happened.

    It does not move data. It never touches a row. Every pipeline in this
    course would run perfectly well if you typed the commands by hand at the
    right moments, forever, without sleeping. Airflow is the thing that does
    the typing.

WHAT A DAG IS
    Directed Acyclic Graph, which is three words for one idea:

        directed    the arrows point one way. bronze feeds silver, never back
        acyclic     no loops. nothing can end up waiting for itself
        graph       a set of tasks with arrows between them

    That is all. A DAG is a picture of what has to happen before what.

WHY THIS IS WORTH A WHOLE FILE
    Look at cli.py in this project. It has a list called ORDER and it runs the
    eight pipelines top to bottom. That works, and for a laptop it is enough.

    It stops being enough the moment you ask any of these questions:

        the third pipeline failed at 3am. Did the rest still run?
        it is 4am and I want to retry just that one. How?
        two of these could run at the same time. Why are they queued?
        yesterday's file arrived late. Can I rerun just yesterday?
        who has been paged, and for which task?

    Airflow answers all five, and that is the entire reason it exists.

DEPLOY IT
    The dags folder is mounted into the Airflow container. Save this file and
    the scheduler picks it up within about ten seconds.

    Then open http://localhost:8080  (kerb / kerb_local_dev)
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

# Where the course lives INSIDE the container. Not the path on your laptop.
PROJECT = "/opt/kerb/teach"


# ══ STEP 1 · Describe the DAG itself ══
#
# Everything here is a decision about WHEN and WHAT IF, never about what the
# pipelines do. Read each argument as a question being answered:
#
#   schedule          how often should this run?
#   start_date        from when does that schedule apply?
#   catchup           if I turn it on today, should it backfill every run it
#                     missed since start_date? Almost always no, and forgetting
#                     this is how people accidentally launch 400 runs at once.
#   max_active_runs   can two runs of this DAG overlap? For a pipeline that
#                     rebuilds a window, no: they would fight over the same rows.
#   retries           how many times before we admit it is broken?
#   retry_delay       how long to wait, so a database that is briefly busy gets
#                     a chance to recover rather than being hammered.
@dag(
    dag_id="teach_pipelines",
    description="bronze, silver and gold for the pipeline building course",
    schedule="0 * * * *",                       # hourly, on the hour
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,                              # do NOT backfill on first enable
    max_active_runs=1,                          # never two runs at once
    default_args={
        "retries": 2,
        "retry_delay": pendulum.duration(minutes=1),
        "owner": "data-platform",
    },
    tags=["course", "bronze", "silver", "gold"],
)
def teach_pipelines():

    # ══ STEP 2 · One task per pipeline ══
    #
    # Every task is the same shape: run one module, inside the project folder,
    # with the project on the path.
    #
    # Notice what a task is NOT. It is not a copy of the pipeline logic. Airflow
    # calls the exact same command you would type yourself:
    #
    #     python -m pipelines.p1_bronze_trips
    #
    # That matters more than it sounds. It means you can always reproduce an
    # Airflow failure on your own machine by running one line, and it means the
    # pipelines have no idea Airflow exists. Swap Airflow for anything else
    # tomorrow and not one pipeline file changes.
    def pipeline(name: str, args: str = "") -> BashOperator:
        return BashOperator(
            task_id=name,
            bash_command=f"cd {PROJECT} && python -m pipelines.{name} {args}",
            env={"PYTHONPATH": PROJECT},
            append_env=True,      # keep the estate credentials Airflow already has
        )

    # ══ STEP 3 · The six bronze pipelines ══
    #
    # These read six different systems and share nothing. None of them depends
    # on another, so Airflow is free to run all six at the same time, and it
    # will. That is the first thing an orchestrator buys you that a for-loop
    # does not.
    bronze_trips       = pipeline("p1_bronze_trips", "--days 7")
    bronze_events      = pipeline("p2_bronze_events")
    bronze_driver_app  = pipeline("p3_bronze_driver_app")
    bronze_settlements = pipeline("p4_bronze_settlements", "--limit 5000")
    bronze_regulator   = pipeline("p5_bronze_regulator", "--days 7")
    bronze_zones       = pipeline("p6_bronze_zones")

    bronze = [bronze_trips, bronze_events, bronze_driver_app,
              bronze_settlements, bronze_regulator, bronze_zones]

    # ══ STEP 4 · Silver and gold, which must wait ══
    silver = pipeline("p7_silver_rides")
    gold   = pipeline("p8_gold_daily")

    # ══ STEP 5 · Say what must happen before what ══
    #
    # This is the whole DAG, in two lines.
    #
    #     bronze >> silver     silver starts only when ALL SIX bronze succeed
    #     silver >> gold       gold starts only when silver succeeds
    #
    # Read the guarantee that gives you: gold can never be built from a silver
    # table that failed to refresh. Not "should not". Cannot. Airflow will not
    # start the task.
    #
    # That one property is why people put up with running Airflow at all.
    bronze >> silver >> gold

    # ══ STEP 6 · Check the result, and say something useful ══
    #
    # A pipeline finishing is not the same as the data being right. This task
    # runs the signal board after everything has landed.
    #
    # It deliberately does NOT fail the DAG when a signal breaches. A breach
    # means "a number moved and a human should look", not "the run is broken".
    # Failing here would page the on-call engineer for something that is often
    # a completely correct number reflecting a bad day of trading.
    @task(task_id="signal_board")
    def signal_board() -> str:
        import subprocess
        result = subprocess.run(
            ["python", "-m", "signals.board"],
            cwd=PROJECT, capture_output=True, text=True,
            env={"PYTHONPATH": PROJECT, "PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
        print(result.stdout or result.stderr)
        # returncode 1 means "a signal breached", which is information, not failure
        return "breached" if result.returncode == 1 else "clean"

    gold >> signal_board()


teach_pipelines()
