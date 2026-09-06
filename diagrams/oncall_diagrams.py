"""Diagrams for the two services notebooks."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("o1", "Two services, and one record between them",
         "Band four of the architecture. Everything above this has already happened.",
         cols=4, rows=2, row_h=340)
p.band("THE WAREHOUSE  ·  the only thing either service ever reads", 0)
a = p.box("THE SIGNAL BOARD", ["Runs on a clock.", "13 queries, one number each.",
                               "Emits a record when one breaches.", "",
                               "Knows nothing about agents."], 0, 0, span=2, kind="ours")
b = p.box("THE AGENT SYSTEM", ["Asleep until a record arrives.", "Diagnoses, proposes, verifies.",
                               "Changes nothing.", "",
                               "Knows nothing about KPIs."], 2, 0, span=2, kind="good")
p.arrow(a, b, "one record")
p.note("<b>Neither service imports the other.</b> They share one pydantic model, in a package "
       "that neither of them owns, and they talk over HTTP. That is what lets you restart "
       "either one mid sentence, deploy them separately, and rewrite one of them next year "
       "without touching the other.<br><br>"
       "<b>The record is written to the database BEFORE the doorbell is rung.</b> A failed "
       "notification then costs latency, not an incident.", 0, 1, span=4)
pages.append(p)

p = Page("o2", "A KPI is not a signal",
         "The distinction the whole service rests on.",
         cols=2, rows=2, row_h=340)
p.box("A KPI", ["A number with a definition", "and an owner.", "",
                "\"revenue yesterday\"", "", "It is never wrong.", "It cannot fire."],
      0, 0, kind="ours")
p.box("A SIGNAL", ["A KPI, plus a baseline,", "plus a tolerance.", "",
                   "\"revenue yesterday, which is", "normally 1.9 million\"", "",
                   "This one can breach."], 1, 0, kind="good")
p.note("<b>You cannot alert on a KPI</b>, because a number on its own has no opinion about "
       "itself. You can only alert once somebody has written down what normal looks like, "
       "and that sentence is the part nobody wants to write.<br><br>"
       "Two kinds of baseline. <b>Computed from history</b> for things that vary, like rides "
       "per day. <b>Decided by a person</b> for things that should not vary at all: zero held "
       "records is not an average, it is a rule.", 0, 1, span=2)
pages.append(p)

p = Page("o3", "The five agents, and why five",
         "Each answers one question. None of them can do another's job.",
         cols=5, rows=2, row_h=300)
for i, (n, q, can) in enumerate([
        ("1 TRIAGE", "Is this real?", "reads the board only"),
        ("2 DATA", "What is wrong?", "queries, cannot read code"),
        ("3 LINEAGE", "Where from?", "reads code, cannot query"),
        ("4 REMEDIATION", "What is the fix?", "writes artifacts only"),
        ("5 VERIFIER", "Did it work?", "reads the number again")]):
    kind = "ours" if i < 3 else ("gate" if i == 3 else "good")
    p.box(n, [q, "", can], i, 0, kind=kind)
p.note("<b>An agent with every tool will use every tool.</b> The data detective cannot open a "
       "file, so it cannot guess from the code and call it evidence. The lineage detective "
       "cannot query the warehouse, so it cannot re-do the previous agent's work with worse "
       "tools.<br><br>"
       "<b>Narrow the toolbox and the method emerges from the constraint</b>, rather than from "
       "a longer prompt. And every one returns a typed verdict, because a supervisor cannot "
       "branch on a paragraph.", 0, 1, span=5)
pages.append(p)

p = Page("o4", "What it is allowed to produce",
         "It proposes. A person decides. Nothing it does changes a number.",
         cols=4, rows=2, row_h=330)
p.box("A PAGE", ["Always. Even when it", "found nothing.", "",
                 "The diagnosis, the evidence,", "and what to do."], 0, 0, kind="good")
p.box("A TICKET", ["So it is somebody's,", "with a severity", "and an owner."], 1, 0, kind="good")
p.box("A PULL REQUEST", ["For a code fix.", "A branch and a commit.", "",
                         "Never a merge.", "The review IS the gate."], 2, 0, kind="gate")
p.box("AN APPROVAL REQUEST", ["For anything touching data.", "", "The graph STOPS here",
                              "and waits for a person.", "Nothing is executed."], 3, 0, kind="bad")
p.note("<b>Whether an agent meant well is a judgement. Whether it CAN write is a fact.</b><br><br>"
       "The warehouse connection is opened read only, so Postgres itself refuses a write no "
       "matter what the model asked for. Code changes are limited to two directories, because "
       "an agent that can edit the tests which judge it is not being judged. Every rule you "
       "enforce only in a prompt is a rule you are hoping about.", 0, 1, span=4)
pages.append(p)

path = Deck("oncall", pages).save()
export_pages(path, ["two-services", "kpi-vs-signal", "five-agents", "artifacts"])
