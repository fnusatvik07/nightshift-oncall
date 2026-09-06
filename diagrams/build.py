"""Diagrams for the pipeline-building session. Big type, no crossings."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

# ── 1 ───────────────────────────────────────────────────────────────────────
p = Page("1 Why a pipeline exists", "Why a pipeline exists at all",
         "One database is built to serve customers. Another is built to answer questions. "
         "A pipeline is the thing that copies between them.", cols=4, rows=3, row_h=380)
p.band("THE PROBLEM", 0)
p.box("The app database", ["Built to serve a rider booking a car.",
                           "Fast, small, keeps only recent data."], 0, 0, span=2)
p.box("The finance question", ["How much did we earn last month,",
                               "broken down by zone?"], 2, 0, span=2)
p.band("WHY YOU CANNOT JUST ASK THE APP DATABASE", 1)
p.box("You compete with riders", ["Your query reads millions of rows.",
                                  "That is capacity the app needed."], 0, 1, kind="bad")
p.box("The history is not there", ["Operational databases are trimmed",
                                   "to stay fast. Last year is gone."], 1, 1, kind="bad")
p.box("The shape is wrong", ["Arranged for 'this one ride',",
                             "not for 'total by day'."], 2, 1, kind="bad")
p.box("So: make a copy", ["Somewhere else, arranged for",
                          "questions. That copy is the job."], 3, 1, kind="good")
p.band("WHAT MAKES IT A PIPELINE AND NOT A SCRIPT", 2)
p.stack("Four things, every time", ["1  it records that it ran",
                                    "2  it holds what it cannot read",
                                    "3  it writes all or nothing",
                                    "4  running it twice is safe"],
        0, 2, span=2, kind="ours",
        note="anyone can copy rows once · these four are what survive running hourly, forever")
p.note("Miss any one of them and you have a script that works until the first bad night. "
       "The rest of this session is those four ideas, applied to four different kinds of source.",
       2, 2, span=2)
pages.append(p)

# ── 2 ───────────────────────────────────────────────────────────────────────
p = Page("2 The four sources", "Four sources, four different problems",
         "This is why there are four pipelines and not one.", cols=4, rows=3, row_h=400)
p.band("WHAT WE READ", 0)
p.stack("PostgreSQL", ["kerb.trips"], 0, 0, note="a normal table")
p.stack("Kafka", ["kerb.trips.lifecycle"], 1, 0, note="a stream of events")
p.stack("MongoDB", ["driver_app_events"], 2, 0, note="documents from a phone")
p.stack("PayNimbus", ["REST API"], 3, 0, note="another company's system")
p.band("WHAT IS HARD ABOUT EACH ONE", 1)
p.box("Nothing", ["It has a shape and a WHERE clause.", "Start here."], 0, 1, kind="good")
p.box("No WHERE clause", ["You cannot ask for yesterday.", "Only 'since I last stopped'."], 1, 1, kind="gate")
p.box("No fixed shape", ["A mobile release can rename", "a field on a Tuesday."], 2, 1, kind="gate")
p.box("Not yours", ["Slow, changeable, and it will", "not ask your permission."], 3, 1, kind="bad")
p.band("SO EACH ONE NEEDS SOMETHING DIFFERENT", 2)
p.box("A window", ["Rebuild a range of days,", "never the whole table."], 0, 2)
p.box("An offset", ["Remember your position,", "and commit it after the write."], 1, 2)
p.box("A contract", ["Write down every field path", "you are willing to read."], 2, 2)
p.box("Batching", ["250 per request, and treat", "'absent' as normal."], 3, 2)
pages.append(p)

# ── 3 ───────────────────────────────────────────────────────────────────────
p = Page("3 One pipeline, inside", "What happens inside one run",
         "The same six steps whether the source is a table, a stream, a document store or an API.",
         cols=3, rows=3, row_h=360)
p.band("EVERY RUN, IN THIS ORDER", 0)
a = p.box("1  Claim the run", ["Write a row saying you started.",
                               "A job that hangs still leaves evidence."], 0, 0)
b = p.box("2  Read the window", ["Only what is new. Never the",
                                 "whole table, ever."], 1, 0)
c = p.box("3  Check each record", ["Is every value one we already",
                                   "know how to read?"], 2, 0, kind="gate")
p.arrow(a, b); p.arrow(b, c)
p.band("THEN ONE OF TWO THINGS", 1)
d_ = p.box("Understood", ["Goes to the target table."], 0, 1, kind="good")
e = p.box("Not understood", ["Goes to quarantine, with the",
                             "reason and the original record."], 1, 1, kind="bad")
p.box("Never a third option", ["Not dropped. Not defaulted to zero.",
                               "Both of those are lies."], 2, 1)
p.band("AND FINALLY", 2)
f = p.box("4  Write in one transaction", ["Delete the window, insert the new rows,",
                                          "commit once. A crash undoes both."], 0, 2, span=2, kind="ours")
p.box("5  Close the run", ["Status, rows in, rows out.", "So 'did it run' has an answer."], 2, 2)
pages.append(p)

# ── 4 ───────────────────────────────────────────────────────────────────────
p = Page("4 The signal board", "The signal board, and where it sits",
         "Five pipelines ran overnight. How do you know the numbers are true?",
         cols=4, rows=3, row_h=400)
p.band("A SIGNAL IS FOUR THINGS", 0)
p.box("A name", ["so people can talk about it"], 0, 0)
p.box("A query", ["that returns one number"], 1, 0)
p.box("A baseline", ["what it normally is"], 2, 0)
p.box("An owner", ["who gets told"], 3, 0)
p.band("START FROM HOW THINGS BREAK, NOT FROM METRICS", 1)
p.stack("Six ways it breaks", ["a job did not run",
                               "a contract held rows",
                               "a feed stopped arriving",
                               "the stream got replayed",
                               "a join dropped rows",
                               "a field got renamed"], 0, 1, span=2, kind="bad")
p.stack("Six numbers that catch it", ["pipelines_failing",
                                      "records_held",
                                      "rides_per_day",
                                      "events_per_ride",
                                      "rides_missing_fare",
                                      "surge_missing_pct"], 2, 1, span=2, kind="good")
p.band("WHERE EACH CHECK SITS, AND WHAT IT CAN STOP", 2)
p.box("A contract", ["Inside the pipeline, every record.", "CAN stop a record."], 0, 2, kind="gate")
p.box("A test", ["Inside, before the commit.", "CAN roll back a batch."], 1, 2, kind="gate")
p.box("A signal", ["Outside, afterwards, on a clock.", "Can stop NOTHING."], 2, 2, kind="good")
p.note("That last one is the point. The board has no power over your data, which is exactly "
       "what lets it watch everything without being able to break anything.", 3, 2)
pages.append(p)

path = Deck("pipelines", pages).save()
print("wrote", path.name, "with", len(pages), "pages")
export_pages(path, ["why-a-pipeline", "four-sources", "inside-one-run", "signal-board"])
