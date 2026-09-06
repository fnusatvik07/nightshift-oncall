"""The fixed parts of the world: zones, drivers, riders.

Everything here is deterministic. Given the same KERB_SEED you get the same
sixty one zones, the same drivers, the same riders, on any machine. That is not
a nicety: a course where the numbers on the screen differ from the numbers in
the notes is a course nobody trusts.
"""
from __future__ import annotations

import datetime as dt
import random

# 61 zones, which is enough for a join to be interesting and few enough that
# the dimension can be rebuilt whole on every run.
ZONE_NAMES = [
    ("Kempegowda Airport", "North", "airport"),
    ("Airport Road North", "North", "airport"),
    ("Yelahanka", "North", "suburb"),
    ("Hebbal", "North", "residential"),
    ("Sahakar Nagar", "North", "residential"),
    ("RT Nagar", "North", "residential"),
    ("Jalahalli", "North", "industrial"),
    ("Peenya Industrial", "North", "industrial"),
    ("Yeshwanthpur", "North", "industrial"),
    ("Malleshwaram", "North", "residential"),
    ("Rajajinagar", "West", "residential"),
    ("Vijayanagar", "West", "residential"),
    ("Basaveshwaranagar", "West", "residential"),
    ("Nagarbhavi", "West", "suburb"),
    ("Kengeri", "West", "suburb"),
    ("Rajarajeshwari Nagar", "West", "suburb"),
    ("Magadi Road", "West", "residential"),
    ("Mysore Road", "West", "industrial"),
    ("Chandra Layout", "West", "residential"),
    ("Bapuji Nagar", "West", "residential"),
    ("MG Road", "Central", "cbd"),
    ("Brigade Road", "Central", "cbd"),
    ("Cubbon Park", "Central", "cbd"),
    ("Shivajinagar", "Central", "cbd"),
    ("Richmond Town", "Central", "residential"),
    ("Lavelle Road", "Central", "cbd"),
    ("Vasanth Nagar", "Central", "cbd"),
    ("Seshadripuram", "Central", "residential"),
    ("Chickpet", "Central", "cbd"),
    ("KR Market", "Central", "cbd"),
    ("Indiranagar", "East", "cbd"),
    ("Domlur", "East", "cbd"),
    ("Old Airport Road", "East", "cbd"),
    ("Marathahalli", "East", "residential"),
    ("Whitefield", "East", "cbd"),
    ("Brookefield", "East", "residential"),
    ("Kadugodi", "East", "suburb"),
    ("Mahadevapura", "East", "industrial"),
    ("KR Puram", "East", "residential"),
    ("Ramamurthy Nagar", "East", "residential"),
    ("Banaswadi", "East", "residential"),
    ("Kalyan Nagar", "East", "residential"),
    ("HBR Layout", "East", "residential"),
    ("CV Raman Nagar", "East", "residential"),
    ("Koramangala", "South", "cbd"),
    ("HSR Layout", "South", "residential"),
    ("BTM Layout", "South", "residential"),
    ("Jayanagar", "South", "residential"),
    ("JP Nagar", "South", "residential"),
    ("Banashankari", "South", "residential"),
    ("Basavanagudi", "South", "residential"),
    ("Wilson Garden", "South", "residential"),
    ("Bommanahalli", "South", "suburb"),
    ("Electronic City", "South", "industrial"),
    ("Bannerghatta Road", "South", "residential"),
    ("Sarjapur Road", "South", "residential"),
    ("Bellandur", "South", "cbd"),
    ("Hulimavu", "South", "suburb"),
    ("Kanakapura Road", "South", "suburb"),
    ("Jigani", "South", "industrial"),
    ("Attibele", "South", "suburb"),
]

TIERS = ["bronze", "silver", "gold", "platinum"]
SEGMENTS = ["commuter", "occasional", "business", "tourist"]

# Which app version a ride was booked on. The last one is the release that
# moves the surge field, and notebook 4 is about finding that.
APP_VERSIONS = ["4.0.6", "4.1.2", "4.1.5", "4.2.0"]


def zones() -> list[tuple]:
    """61 rows. A cbd zone pulls more demand than a suburb, which is what
    makes the ride distribution across zones look like a city rather than
    like a random number generator."""
    weight = {"airport": 2.4, "cbd": 3.0, "residential": 1.4,
              "industrial": 0.8, "suburb": 0.5, "unknown": 0.2}
    return [(i + 1, name, borough, kind, weight[kind])
            for i, (name, borough, kind) in enumerate(ZONE_NAMES)]


def drivers(rng: random.Random, n: int, first_day: dt.date) -> list[tuple]:
    joined_from = (dt.datetime.combine(first_day, dt.time(), dt.timezone.utc)
                   - dt.timedelta(days=900))
    out = []
    for i in range(1, n + 1):
        out.append((
            f"DRV{i:06d}",
            joined_from + dt.timedelta(days=rng.randrange(900),
                                       seconds=rng.randrange(86400)),
            rng.randrange(1, len(ZONE_NAMES) + 1),
            round(rng.uniform(3.6, 5.0), 2),
            rng.choices(TIERS, weights=[40, 32, 20, 8])[0],
            rng.choices(["active", "inactive", "suspended"], weights=[92, 7, 1])[0],
        ))
    return out


def riders(rng: random.Random, n: int, first_day: dt.date) -> list[tuple]:
    signed_from = (dt.datetime.combine(first_day, dt.time(), dt.timezone.utc)
                   - dt.timedelta(days=1200))
    out = []
    for i in range(1, n + 1):
        out.append((
            f"RDR{i:07d}",
            signed_from + dt.timedelta(days=rng.randrange(1200),
                                       seconds=rng.randrange(86400)),
            rng.randrange(1, len(ZONE_NAMES) + 1),
            rng.choices(SEGMENTS, weights=[45, 34, 15, 6])[0],
        ))
    return out
