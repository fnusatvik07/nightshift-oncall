"""Diagrams for notebook 1, the introduction."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("i1", "Why not just query the app database?",
         "Three things go wrong, and only the first one is obvious.",
         cols=3, rows=2, row_h=340)
p.box("YOU COMPETE WITH RIDERS", ["The report reads millions of rows.",
                                  "While it runs, the database has",
                                  "less capacity for the person",
                                  "trying to book a car.", "",
                                  "A slow report is annoying.",
                                  "A slow booking screen loses money."], 0, 0, kind="bad")
p.box("THE ANSWER CHANGES", ["Run the same query twice and",
                             "get two numbers, because rows",
                             "moved underneath you.", "",
                             "Nobody can reconcile a report",
                             "that will not sit still."], 1, 0, kind="bad")
p.box("IT IS THE WRONG SHAPE", ["The app database is built to",
                                "answer 'where is my driver'.", "",
                                "Not 'what did we earn last",
                                "month, by zone, by rail'."], 2, 0, kind="bad")
p.note("<b>So make a copy.</b> On our own hardware, on our own clock, shaped for the questions "
       "people actually ask. Everything in this course is that one idea, done carefully.",
       0, 1, span=3)
pages.append(p)

p = Page("i2", "Bronze, silver, gold",
         "Three layers. Each one is allowed to do things the one before it was not.",
         cols=3, rows=2, row_h=350)
p.box("BRONZE", ["A faithful copy of one source.", "", "No joins. No renames.",
                 "No cleaning. No opinions.", "",
                 "So that 'did we break it, or did", "they send it broken' always",
                 "has an answer."], 0, 0, kind="ours")
p.box("SILVER", ["One clean row per thing.", "", "Joins allowed. Unit conversions",
                 "allowed. Dropping what nothing", "uses, allowed.", "",
                 "The first table a stranger", "could read."], 1, 0, kind="good")
p.box("GOLD", ["The answer, at the grain", "somebody asks for.", "",
               "One row per day, per zone,", "per whatever the question is.", "",
               "If you cannot say the column", "name to a finance manager,", "it does not belong."],
      2, 0, kind="gate")
p.note("<b>The names do not matter. The discipline does.</b> What matters is that each layer has "
       "one job, and that you can always walk backwards from a number in gold to the exact row "
       "in bronze that produced it, and from there to the source.", 0, 1, span=3)
pages.append(p)

p = Page("i3", "A script, and a pipeline",
         "Same code, in both. Everything else is different.",
         cols=2, rows=2, row_h=360)
p.stack("A SCRIPT", ["run it twice -> double the rows",
                     "crashes halfway  -> half written",
                     "bad value        -> crash, or silently dropped",
                     "did it run?      -> check your memory",
                     "how long?        -> nobody knows"], 0, 0, kind="bad")
p.stack("A PIPELINE", ["run it twice -> the same table",
                       "crashes halfway  -> nothing written",
                       "bad value        -> held, with the reason",
                       "did it run?      -> a row in teach.runs",
                       "how long?        -> in that same row"], 1, 0, kind="good")
p.note("<b>Four rules, and they are the whole course.</b><br><br>"
       "<b>Idempotent</b>: running it twice is the same as running it once.<br>"
       "<b>Atomic</b>: all of it lands, or none of it does.<br>"
       "<b>Honest</b>: a value you cannot read is held, never dropped and never defaulted.<br>"
       "<b>Observable</b>: every run leaves a row saying what happened.", 0, 1, span=2)
pages.append(p)

path = Deck("intro", pages).save()
export_pages(path, ["why", "layers", "rules"])
