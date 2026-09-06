"""Diagrams for the silver notebook."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("s1", "Five tables in. One row per ride out.",
         "Silver is where the sources stop being separate.",
         cols=5, rows=3, row_h=250)
p.band("BRONZE   ·   five faithful copies, each shaped like its source", 0)
for i, (name, what) in enumerate([("bronze_trips", "one row per ride"),
                                  ("bronze_events", "five rows per ride"),
                                  ("bronze_driver_app", "the surge"),
                                  ("bronze_settlements", "the money"),
                                  ("bronze_zones", "the zone names")]):
    p.box(name, [what], i, 0, kind="ours")
p.band("SILVER   ·   the first table anybody outside the team would recognise", 1)
p.box("silver_rides", ["one row per ride, with the fare, the surge, the money and the",
                       "zone name attached. Seconds turned into minutes. No rider_id."],
      0, 1, span=5, kind="good")
p.note("<b>Three things silver is allowed to do that bronze was not:</b> convert units, "
       "invent columns that existed in no single source, and drop a personal identifier "
       "nothing downstream uses. Carrying a rider id you do not need is a liability, "
       "not an asset.", 0, 2, span=5)
pages.append(p)

p = Page("s2", "The most expensive word in data engineering",
         "Change one LEFT to INNER and nothing goes wrong. The number is just smaller.",
         cols=2, rows=2, row_h=350)
p.stack("LEFT JOIN   ·   keep the ride", ["cancelled ride, no completed event   kept",
                                          "no driver app record                 kept",
                                          "settlement is T+2, not there yet     kept",
                                          "0.4% never resolved to a zone        kept"],
        0, 0, kind="good", note="84,027 rides")
p.stack("INNER JOIN  ·  drop the ride", ["cancelled ride, no completed event   GONE",
                                         "no driver app record                 GONE",
                                         "settlement is T+2, not there yet     GONE",
                                         "0.4% never resolved to a zone        GONE"],
        1, 0, kind="bad", note="74,743 rides. 9,284 disappeared.")
p.note("<b>Picture how that presents itself in production.</b><br><br>"
       "No error. No failed run. No log line. Somebody changes a join to make a query faster, "
       "the ride count drops four percent, and it takes three weeks to notice and a day to "
       "find.<br><br><b>A wrong answer that runs successfully is worse than a crash, because "
       "a crash tells you.</b>", 0, 1, span=2)
pages.append(p)

p = Page("s3", "ON, or WHERE. It is not a style choice.",
         "The same condition in the wrong clause turns a LEFT JOIN back into an INNER one.",
         cols=2, rows=2, row_h=330)
p.code(["LEFT JOIN bronze_events e", "  ON  e.trip_id = t.trip_id",
        "  AND e.event = 'completed'", "", "-- correct"], 0, 0)
p.code(["LEFT JOIN bronze_events e", "  ON  e.trip_id = t.trip_id",
        "WHERE e.event = 'completed'", "", "-- an inner join wearing a disguise"], 1, 0)
p.note("<b>The WHERE runs after the join.</b> The LEFT JOIN carefully kept the rides with no "
       "completed event, giving them NULL, and then <code>WHERE e.event = 'completed'</code> "
       "throws every one of those NULL rows away.<br><br>"
       "Same rows lost as an INNER JOIN, with a LEFT JOIN sitting in the query looking "
       "reassuring.", 0, 1, span=2)
pages.append(p)

path = Deck("silver", pages).save()
export_pages(path, ["shape", "join", "where"])
