"""Diagrams for the API notebook."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("a1", "Three outcomes, not two",
         "Every reference you ask a partner about ends up in exactly one of these.",
         cols=3, rows=2, row_h=320)
p.box("WRITTEN", ["They answered, and we", "understood the answer.", "", "A row lands."],
      0, 0, kind="good")
p.box("HELD", ["They answered, and we did", "not understand the answer.", "",
               "Quarantine, with the reason."], 1, 0, kind="gate")
p.box("ABSENT", ["They did not answer at all.", "", "Correct. Expected. Healthy."],
      2, 0, kind="ours")
p.note("<b>The third one is where people go wrong.</b> A charge still in flight is simply not "
       "in the response. It is not an error and it is not a null: it is missing, and missing "
       "is the right state for money that has not moved yet.<br><br>"
       "Treat absent as a failure and you page somebody every night for a system behaving "
       "exactly as designed.", 0, 1, span=3)
pages.append(p)

p = Page("a2", "Ask in batches, and pick the size on purpose",
         "Sixty thousand payments. The batch size is a decision, not a detail.",
         cols=3, rows=2, row_h=330)
p.box("BATCH = 1", ["60,000 round trips against", "a partner's system.", "",
                    "An accidental denial of service", "on a company you have a", "contract with."],
      0, 0, kind="bad")
p.box("BATCH = 250", ["240 calls.", "", "Small enough to finish,", "small enough that a failure",
                      "costs you 250 records."], 1, 0, kind="good")
p.box("BATCH = 5000", ["12 calls.", "", "Each one long enough to hit", "a timeout, and a failure",
                       "costs you the whole batch."], 2, 0, kind="bad")
p.note("<b>The number is a trade between round trips and blast radius</b>, so it belongs in a "
       "named constant where it can be argued about, not buried in a loop.<br><br>"
       "And the timeout is not optional. Without one, a partner that hangs takes your pipeline "
       "with it, forever, silently.", 0, 1, span=3)
pages.append(p)

path = Deck("api", pages).save()
export_pages(path, ["outcomes", "batching"])
