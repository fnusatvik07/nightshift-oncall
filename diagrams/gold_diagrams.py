"""Diagrams for the gold and signal board notebook."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("g1", "Three checkpoints, and they are not the same thing",
         "People collapse these into one word, quality, and then argue past each other.",
         cols=3, rows=2, row_h=380)
p.box("THE CONTRACT", ["WHERE  inside the pipeline",
                       "WHEN   per record, on the way in",
                       "CAN IT BLOCK?  yes, that is its job",
                       "", "An unreadable value is held", "before it is ever published."],
      0, 0, kind="gate")
p.box("THE TESTS", ["WHERE  inside the transaction",
                    "WHEN   after the write, before the commit",
                    "CAN IT BLOCK?  yes, it rolls back",
                    "", "The whole batch, judged at once,", "before anyone can read it."],
      1, 0, kind="ours")
p.box("THE SIGNAL BOARD", ["WHERE  outside everything",
                           "WHEN   on a clock, after the run",
                           "CAN IT BLOCK?  no. Nothing. Ever.",
                           "", "It notices that a number moved", "and says whose it is."],
      2, 0, kind="good")
p.note("<b>A check that can block a write is a contract.</b> A check that cannot is a signal. "
       "Calling both of them monitoring is how a team ends up with alerts nobody reads and "
       "pipelines that fail for reasons nobody wanted them to.", 0, 1, span=3)
pages.append(p)

p = Page("g2", "A signal is four things",
         "There is no model here and no intelligence.",
         cols=4, rows=2, row_h=300)
p.box("A NAME", ["so a person can", "talk about it"], 0, 0)
p.box("A QUERY", ["that returns exactly", "one number"], 1, 0)
p.box("A BASELINE", ["what that number", "normally is"], 2, 0)
p.box("AN OWNER", ["who gets told", "when it moves"], 3, 0, kind="good")
p.note("<b>Deciding that 34% is far from 0.09% is arithmetic.</b> Pretending otherwise is how "
       "people end up buying something they could have written in an afternoon.<br><br>"
       "The owner is the field that makes the difference between an alert and a fix. A breach "
       "with no name attached is a number on a screen that everybody assumes somebody else "
       "is looking at.", 0, 1, span=4)
pages.append(p)

p = Page("g3", "Two kinds of baseline",
         "Some numbers have a history. Some have a rule.",
         cols=2, rows=2, row_h=340)
p.stack("COMPUTED FROM HISTORY", ["rides_per_day", "", "mean of the days before",
                                  "spread from those same days",
                                  "breach when it is 4 spreads out"], 0, 0, kind="ours",
        note="a quiet Tuesday is not a breach. A feed that stopped is.")
p.stack("DECIDED BY A PERSON", ["records_held", "pipelines_failing", "",
                                "expected value: 0", "no history involved"], 1, 0, kind="good",
        note="zero held records is not an average, it is a rule")
p.note("<b>And one that needs both.</b> events_per_ride has a fixed baseline of 4.7 with a "
       "tolerance of 1.0, because a completed ride emits five events and a cancelled one emits "
       "three. The true average sits a little under five, and that is correct, not a fault. "
       "Set the baseline to exactly 5 and the board cries wolf on day one.", 0, 1, span=2)
pages.append(p)

path = Deck("gold", pages).save()
export_pages(path, ["checkpoints", "signal", "baselines"])
