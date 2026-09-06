"""Small diagrams for the Kafka notebook, one per idea as it is introduced."""
from clean import Page, Deck, export_pages, INK, BLUE, GREEN, RED, AMBER, MUTED

pages = []

p = Page("k1", "A producer, a topic, a consumer",
         "Three words. That is the whole shape of Kafka.", cols=4, rows=1, row_h=330)
a = p.box("PRODUCER", ["Anything that sends events.", "The KERB app. You, in a minute."], 0, 0, kind="ours")
b = p.box("THE BROKER", ["A program that holds events,", "in order, for a while."], 1, 0, span=2)
c = p.box("CONSUMER", ["Anything that reads them.", "Our pipeline. And four other teams."], 3, 0, kind="good")
p.arrow(a, b, "produce"); p.arrow(b, c, "consume")
pages.append(p)

p = Page("k2", "A topic is split into partitions",
         "So that more than one reader can work at the same time.", cols=4, rows=2, row_h=300)
p.band("TOPIC  kerb.trips.lifecycle", 0)
p.stack("partition 0", ["offset 0", "offset 1", "offset 2", "..."], 0, 0, kind="ours",
        note="messages arrive in order, and stay in order")
p.stack("partition 1", ["offset 0", "offset 1", "offset 2", "..."], 1, 0, kind="ours")
p.stack("partition 2", ["offset 0", "offset 1", "offset 2", "..."], 2, 0, kind="ours")
p.note("<b>Order is only guaranteed inside one partition.</b><br><br>"
       "Across partitions there is no order at all. That is why a message carries a "
       "<b>key</b>: the same key always goes to the same partition, so all five events "
       "of one ride stay in the order they happened.", 3, 0)
pages.append(p)

p = Page("k3", "A consumer group is a bookmark",
         "Reading does not remove anything. So the reader has to remember where it got to.",
         cols=4, rows=2, row_h=320)
p.band("THE SAME TOPIC, READ BY TWO DIFFERENT TEAMS", 0)
p.stack("teach-bronze-events", ["position  396,937", "still to read     2"], 0, 0,
        span=2, kind="good", note="our pipeline")
p.stack("fraud-service", ["position  120,004", "still to read 276,935"], 2, 0,
        span=2, kind="ours", note="somebody else's, three days behind")
p.note("<b>Two bookmarks, stored on the broker, under two names.</b> Neither can affect "
       "the other. The fraud team could be a week behind and our pipeline would never "
       "notice.<br><br>This is also why <code>reset</code> has to delete the group: our "
       "bookmark lives on the broker, not in our database.", 0, 1, span=4)
pages.append(p)

p = Page("k4", "The order of the last three lines",
         "Read a batch. Write it. Only then say you have read it.",
         cols=4, rows=2, row_h=340)
p.band("TWO POSSIBLE ORDERS. ONLY ONE OF THEM IS SAFE.", 0)
p.stack("WRITE, THEN COMMIT  ·  what we do", ["1  read 5,000 messages", "2  write them to postgres",
                            "3  CRASH", "4  offset never moved"], 0, 0, span=2, kind="good",
        note="next run reads the same 5,000 again. The primary key refuses the duplicates. Nothing is lost.")
p.stack("COMMIT, THEN WRITE  ·  what the default does", ["1  read 5,000 messages", "2  offset moves", "3  CRASH",
                              "4  rows never written"], 2, 0, span=2, kind="bad",
        note="those 5,000 are gone. No error, no gap, nothing to detect. Nobody will ever know.")
p.note("<b>Duplicates you can remove. Missing data you cannot invent.</b><br><br>"
       "That is the trade, and it is not close. Reading a message more than once is called "
       "<b>at-least-once</b> delivery, and it is what almost every real streaming pipeline "
       "chooses. It only works because the table has a primary key that makes the second "
       "copy a no-op.", 0, 1, span=4)
pages.append(p)

path = Deck("kafka", pages).save()
export_pages(path, ["shape", "partitions", "groups", "commit"])
