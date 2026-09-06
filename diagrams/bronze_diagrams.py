"""Diagrams for the bronze notebooks, one per idea as it is introduced."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("b1", "Bronze is a copy with no opinions",
         "The only job is to get the source into our database, faithfully, fast.",
         cols=4, rows=2, row_h=330)
src = p.box("kerb.trips", ["Somebody else's live table.", "It serves riders and drivers.",
                           "We are guests here."], 0, 0)
me  = p.box("teach.bronze_trips", ["Our copy. Same columns,", "same values, same names."],
            2, 0, span=2, kind="ours")
p.arrow(src, me, "one query, one window")
p.note("<b>Why so strict?</b><br><br>"
       "The moment bronze starts cleaning, renaming or joining, you can no longer answer "
       "one question: <i>is this wrong because the source sent it wrong, or because we broke "
       "it on the way in?</i><br><br>"
       "Bronze exists so that question always has an answer.", 0, 1, span=4)
pages.append(p)

p = Page("b2", "A window, anchored on the data",
         "A pipeline never reads the whole table. It rebuilds a small window, over and over.",
         cols=4, rows=2, row_h=340)
p.box("WRONG: count back from today", ["today minus 7 days", "", "A dataset generated once and "
      "left alone", "has nothing near today. You read zero", "rows and lose twenty minutes."],
      0, 0, span=2, kind="bad")
p.box("WRONG: max(date)", ["max(requested_at)", "", "One stray test row dated next year",
      "drags the anchor to a day holding", "a single ride."], 2, 0, span=2, kind="bad")
p.code(["SELECT date(requested_at)", "FROM kerb.trips", "GROUP BY 1",
        "HAVING count(*) > 100      -- a real day of trading",
        "ORDER BY 1 DESC LIMIT 1"], 0, 1, span=2)
p.note("<b>lo is inclusive. hi is exclusive. Always.</b><br><br>"
       "Mixing those up is how you get a pipeline that double counts one day, every single "
       "run, for months, while every total looks almost right.", 2, 1, span=2)
pages.append(p)

p = Page("b3", "A value you cannot read: three answers, two of them lies",
         "This is the decision at the heart of every bronze pipeline.",
         cols=3, rows=2, row_h=330)
p.box("DROP IT", ["The row count is quietly smaller.", "Nobody ever finds out.",
                  "", "A lie."], 0, 0, kind="bad")
p.box("DEFAULT IT", ["A number appears on a finance", "report that never happened.",
                     "", "A worse lie."], 1, 0, kind="bad")
p.box("HOLD IT", ["The warehouse is briefly", "incomplete, and somebody", "can see exactly why.",
                  "", "The only honest answer."], 2, 0, kind="good")
p.note("<b>Held, not lost.</b> Quarantine keeps the record, the reason, and the original "
       "payload, so the person who picks it up tomorrow has everything they need and does "
       "not have to guess. For a stream it keeps the partition and offset too, so you can go "
       "back to the exact message.", 0, 1, span=3)
pages.append(p)

path = Deck("bronze", pages).save()
export_pages(path, ["copy", "window", "piles"])
