"""Small diagrams for the Airflow notebook, one per idea as it is introduced."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("a1", "A for loop, and an orchestrator",
         "Both run the same eight commands. Only one of them can answer a question at 3am.",
         cols=4, rows=2, row_h=340)
p.band("WHAT WE HAVE BEEN DOING:  for name in ORDER: run(name)", 0)
p.stack("one process, one line", [
    "p1  ok", "p2  ok", "p3  FAILED", "p4  never started",
    "p5  never started", "...", "p8  never started"], 0, 0, span=2, kind="bad",
    note="one failure stops everything behind it, including the six that share nothing with it")
p.note("<b>The five questions a loop cannot answer</b><br><br>"
       "The third one failed at 3am. Did the rest still run?<br>"
       "Can I retry just that one?<br>"
       "Six of these are independent. Why are they queued?<br>"
       "Yesterday's file was late. Can I rerun yesterday alone?<br>"
       "Who was told, and about which task?", 2, 0, span=2)
pages.append(p)

p = Page("a2", "A DAG is a picture of what must happen before what",
         "Airflow derives the whole thing from two lines: bronze >> silver >> gold.",
         cols=6, rows=3, row_h=260)
p.band("SIX TASKS THAT SHARE NOTHING, SO ALL SIX RUN AT ONCE", 0)
for i, (name, src) in enumerate([("p1", "postgres"), ("p2", "kafka"), ("p3", "mongodb"),
                                 ("p4", "rest api"), ("p5", "minio"), ("p6", "zones")]):
    p.box(name, [src], i, 0, kind="ours")
p.band("AND ONLY WHEN ALL SIX HAVE FINISHED", 1)
sv = p.box("p7_silver_rides", ["joins all six together", "one row per ride"], 0, 1, span=3, kind="good")
gd = p.box("p8_gold_daily", ["waits for silver", "one row per day"], 3, 1, span=3, kind="good")
p.arrow(sv, gd, "then")
p.note("<b>Gold cannot be built from a silver table that failed to refresh.</b> Not should "
       "not. Cannot. If silver fails, Airflow does not start gold, and there is no code path "
       "where it happens. That one property is why people put up with running Airflow at all.",
       0, 2, span=6)
pages.append(p)

p = Page("a3", "What a task actually is",
         "Not a copy of the pipeline. The same command a human would type.",
         cols=4, rows=2, row_h=330)
a = p.box("AIRFLOW", ["Decides when.", "Decides in what order.", "Records what happened.",
                      "Never touches a row."], 0, 0, kind="quiet")
p.code(["BashOperator(", "  task_id='p2_bronze_events',",
        "  bash_command='python -m '", "               'pipelines.p2_bronze_events',", ")"], 1, 0)
c = p.box("THE PIPELINE FILE", ["Has no idea Airflow exists.", "Runs the same on your laptop."],
          3, 0, kind="ours")
p.note("<b>Two things follow from that one line.</b><br><br>"
       "Any Airflow failure reproduces on your laptop by typing one command. There is no "
       "<i>it only breaks in Airflow</i>.<br><br>"
       "Swap Airflow for something else tomorrow and not one pipeline file changes.",
       0, 1, span=4)
pages.append(p)

p = Page("a4", "Two files, and where each one lives",
         "This is the bit that confuses everybody. It is worth thirty seconds.",
         cols=2, rows=2, row_h=360)
p.stack("THE WORK", ["pipelines/heartbeat.py", "", "python -m pipelines.heartbeat",
                     "", "It has never heard of Airflow."], 0, 0, kind="ours",
        note="you can run this yourself, right now, with no scheduler involved")
p.stack("WHEN TO RUN IT", ["airflow/dags/teach_dag.py", "", "schedule=\"*/1 * * * *\"",
                           "", "It moves no data and touches no row."], 1, 0, kind="good",
        note="Airflow watches this folder, and nothing else")
p.note("<b>Both folders are inside this one repo</b>, and both are mounted into the Airflow "
       "container, which sees them at <code>/opt/kerb/teach</code> and "
       "<code>/opt/airflow/dags</code>. Same files, different names.<br><br>"
       "So saving a file in <code>airflow/dags/</code> <b>is</b> deploying it. There is no "
       "build step and nothing to copy anywhere.", 0, 1, span=2)
pages.append(p)

path = Deck("airflow", pages).save()
export_pages(path, ["loop", "dag", "task", "where"])
