"""The whole system, on one page, for the README."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

# ── 1 · the whole thing ────────────────────────────────────────────────────
p = Page("s1", "NIGHTSHIFT, on one page",
         "Sources at the top. The copy in the middle. Two services underneath. "
         "People at the bottom. Nothing reads upward.",
         cols=5, rows=5, row_h=300)

p.band("1  SOURCES   ·   not ours to change", 0)
for i, (name, sub) in enumerate([
        ("kerb.trips", "PostgreSQL"), ("trips.lifecycle", "Kafka"),
        ("driver_app_events", "MongoDB"), ("PayNimbus", "a partner's REST API"),
        ("regulator/", "gzipped CSV in S3")]):
    p.box(name, [sub], i, 0, kind="quiet")

p.band("2  INGEST   ·   copy it, and check it on the way in", 1)
p.box("six pipelines", ["One per source, each with its own contract.",
                        "What nobody can read goes to quarantine."],
      0, 1, span=3, kind="ours")
p.box("teach.quarantine", ["Held, with the reason and payload.",
                           "An inbox with an owner."], 3, 1, span=2, kind="gate")

p.band("3  THE WAREHOUSE   ·   the only thing the services ever read", 2)
p.box("bronze", ["landed untouched"], 0, 2, kind="ours")
p.box("silver", ["one row per ride"], 1, 2, kind="ours")
p.box("gold", ["one row per day"], 2, 2, kind="ours")
p.box("teach.runs", ["did it run,", "and finish"], 3, 2, kind="ours")
p.box("17 invariants", ["things that must", "NEVER be false"], 4, 2, kind="gate")

p.band("4  TWO SERVICES   ·   this is what the project is about", 3)
board = p.box("THE SIGNAL BOARD", ["13 KPIs on a clock. Groups before it pages.",
                                   "One record per cause, not per signal."],
              0, 3, span=2, kind="good")
agents = p.box("THE ON CALL AGENTS", ["Asleep until a record arrives. Five specialists.",
                                      "Diagnoses, proposes, verifies. Changes nothing."],
               3, 3, span=2, kind="good")
p.arrow(board, agents, "one incident")

p.band("5  PEOPLE   ·   every outcome is something a person decides on", 4)
p.box("A CONFLUENCE PAGE", ["diagnosis, evidence,", "and a diagram"], 0, 4, kind="gate")
p.box("A TICKET", ["with an owner", "and a severity"], 1, 4, kind="gate")
p.box("A PULL REQUEST", ["never merged,", "an allow list of four"], 2, 4, kind="gate")
p.box("AN APPROVAL", ["for anything touching data.", "The graph stops."], 3, 4, kind="bad")
p.box("A HUMAN", ["decides.", "", "Always."], 4, 4, kind="quiet")
pages.append(p)

# ── 2 · what happens when a number moves ───────────────────────────────────
p = Page("s2", "What happens when a number moves",
         "Nobody types anything after the first line.",
         cols=6, rows=2, row_h=330)
steps = [
    ("1  A FIELD MOVES", "A mobile release sends surge at a new path."),
    ("2  NOTHING FAILS", "Every pipeline runs. Every row count is unchanged."),
    ("3  THE CLOCK", "60 seconds later, one of 13 KPIs is out of range."),
    ("4  ONE RECORD", "Grouped with anything else that moved for the same reason."),
    ("5  FIVE AGENTS", "Real, then what, then where from, then the fix, then proof."),
    ("6  A PAGE", "With an owner, a diagram, the evidence and a diff."),
]
boxes = [p.box(t, [d], i, 0, kind=("bad" if i < 2 else "ours" if i < 5 else "good"))
         for i, (t, d) in enumerate(steps)]
for a, b in zip(boxes, boxes[1:]):
    p.arrow(a, b)
p.note("<b>Step 2 is the whole problem.</b> A pipeline that fails wakes somebody. A pipeline "
       "that succeeds while quietly carrying less data than it should wakes nobody, and every "
       "row count check you can write stays green through it.<br><br>"
       "<b>Step 6 is the whole point.</b> Not a fix: a person arriving at a diagnosis three "
       "hours early, with the queries already run and the change written out.", 0, 1, span=6)
pages.append(p)

# ── 3 · what it cannot do ──────────────────────────────────────────────────
p = Page("s3", "What it cannot do, and why that is a fact rather than a promise",
         "Every boundary is enforced by a property of the system, not by a prompt.",
         cols=4, rows=2, row_h=340)
p.box("CANNOT WRITE TO THE WAREHOUSE",
      ["The connection is opened", "read only, so Postgres itself", "refuses the write.", "",
       "Not a rule in a prompt."], 0, 0, kind="good")
p.box("CANNOT EDIT ITS OWN TESTS",
      ["Code changes are limited to", "four directories.", "",
       "An agent that can edit the", "tests judging it is not", "being judged."], 1, 0, kind="good")
p.box("CANNOT SHIP A CHANGE",
      ["A branch and a pull request,", "in an isolated worktree.", "",
       "Never a merge, never main,", "never your working tree."], 2, 0, kind="gate")
p.box("CANNOT TOUCH DATA",
      ["The graph STOPS and waits", "for a person.", "",
       "The tool would not run the", "statement even if it ran."], 3, 0, kind="bad")
p.note("<b>Whether an agent meant well is a judgement. Whether it CAN write is a fact.</b><br><br>"
       "Build on facts. Every rule you enforce only in a system prompt is a rule you are hoping "
       "about, and hope is not a security model. 191 tests hold these four boundaries in place, "
       "and none of them needs a database.", 0, 1, span=4)
pages.append(p)

path = Deck("system", pages).save()
export_pages(path, ["architecture", "what-happens", "boundaries"])
