"""Diagrams for the document and API notebooks."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("d1", "A document is not a row",
         "The source is nested. The target is flat. Somebody has to decide which values become columns.",
         cols=4, rows=2, row_h=380)
p.code(["{", "  \"event_id\": \"EVT0001\",", "  \"trip_id\":  \"TRP00281\",",
        "  \"app\":     { \"version\": \"4.1.2\" },",
        "  \"payload\": { \"surge_multiplier\": 1.4,", "               \"eta_s\": 240 },",
        "  ... fourteen more fields", "}"], 0, 0, span=2)
p.box("teach.bronze_driver_app", ["event_id, trip_id, driver_id,", "event_type, happened_at,",
      "app_version, surge", "", "Six columns, out of twenty fields."], 2, 0, span=2, kind="ours")
p.note("<b>Six of twenty, on purpose.</b> Bronze copies what the business has agreed it needs, "
       "not everything that happens to exist. Landing every field of every document gives you "
       "a table nobody can read and a schema that changes under you every release.",
       0, 1, span=4)
pages.append(p)

p = Page("d2", "The failure this notebook is really about",
         "A field moves. Nothing breaks. Nobody finds out for three weeks.",
         cols=4, rows=2, row_h=360)
p.stack("MONDAY", ["payload.surge_multiplier  1.4"], 0, 0, span=2, kind="good",
        note="the pricing team gets its number")
p.stack("TUESDAY, release 4.2", ["pricing.surge_multiplier  1.4", "payload.surge_multiplier  --"],
        2, 0, span=2, kind="bad",
        note="a perfectly reasonable refactor, and nobody told the data team")
p.note("<b>Watch what does NOT happen.</b><br><br>"
       "The pipeline does not fail. It reads the document fine.<br>"
       "The rows still land. The count is unchanged.<br>"
       "Surge is just empty, on some rows, starting Tuesday.<br><br>"
       "<b>Every row count check you can write stays green through that.</b> Which is why the "
       "contract is a list of every path the value has ever legitimately lived at, and why a "
       "document matching none of them is held rather than defaulted to zero.", 0, 1, span=4)
pages.append(p)

p = Page("d3", "Zero is not the same as unknown",
         "The one decision that separates a warehouse people trust from one they do not.",
         cols=2, rows=2, row_h=330)
p.box("surge = 0", ["There genuinely was no surge", "on this ride.", "", "A fact."],
      0, 0, kind="good")
p.box("surge = 0", ["We could not find the field.", "", "A lie, and once written the two",
                    "are indistinguishable."], 1, 0, kind="bad")
p.note("<b>Holding it costs you an incomplete table for a day.</b><br>"
       "<b>Defaulting it costs you a wrong number forever, with nothing to point at.</b><br><br>"
       "Picture a report that averages surge. Every defaulted zero drags the average down and "
       "quietly misprices the product, and no check anywhere goes red.", 0, 1, span=2)
pages.append(p)

path = Deck("docs", pages).save()
export_pages(path, ["shape", "moved", "zero"])
