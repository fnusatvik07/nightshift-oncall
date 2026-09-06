"""Diagrams for the files and dimension notebook."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("f1", "A CSV has no types",
         "Every value arrives as text. This is where file pipelines actually break.",
         cols=3, rows=2, row_h=320)
p.code(["trip_id,pu_zone_id,distance_km",
        "TRP00281,9.0,4.2", "TRP00282,,3.1", "TRP00283,12,x"], 0, 0, span=2)
p.box("int(\"9.0\")", ["ValueError", "", "The regulator holds zone ids", "as floats, so it writes",
                      "9.0 and not 9."], 2, 0, kind="bad")
p.note("<b>float() first, then int().</b> That looks fussy right up until the first time a "
       "pipeline dies at 2am on a value that looks perfectly fine.<br><br>"
       "And wrap every conversion, because one malformed row in a file of 1,200 must not throw "
       "away the other 1,199.", 0, 1, span=3)
pages.append(p)

p = Page("f2", "No file is not the same as an empty file",
         "They look identical in a row count, and mean completely different things.",
         cols=2, rows=2, row_h=320)
p.box("NO FILE", ["The regulator's job failed.", "", "Somebody should call them."],
      0, 0, kind="bad")
p.box("EMPTY FILE", ["The regulator ran and had", "nothing to send.", "", "Fine. Nothing to do."],
      1, 0, kind="good")
p.note("<b>A pipeline that treats them the same</b> will either page you every quiet weekend, "
       "or stay silent through a genuine outage.<br><br>"
       "So count files as well as rows, and say both numbers out loud in the run message.",
       0, 1, span=2)
pages.append(p)

p = Page("f3", "A fact and a dimension are rebuilt differently",
         "Same warehouse, same tools, two completely different write strategies.",
         cols=2, rows=2, row_h=350)
p.stack("A FACT   ·   bronze_trips", ["something that happened", "has a date",
                                      "rebuilt one WINDOW at a time",
                                      "delete the window, insert it back"], 0, 0, kind="ours",
        note="millions of rows, so you never touch all of them")
p.stack("A DIMENSION   ·   bronze_zones", ["something that IS", "has no date",
                                           "replaced ENTIRELY, every run",
                                           "delete everything, insert everything"], 1, 0,
        kind="good", note="sixty one rows, so replacing all of them is free")
p.note("<b>What a full snapshot loses is history.</b> Rename a zone and the old name is gone, "
       "with nothing recording that it ever existed. That is usually fine for reference data. "
       "When it is not, the technique is called a <b>slowly changing dimension</b>: worth having "
       "heard the phrase, not worth building today.", 0, 1, span=2)
pages.append(p)

path = Deck("files", pages).save()
export_pages(path, ["types", "missing", "dimension"])
