-- ═══════════════════════════════════════════════════════════════════════════
-- KERB Mobility: the app database.
--
-- This is the system of record for a ride hailing company. It exists to serve
-- riders and drivers, right now, quickly. It is NOT built to answer questions
-- like "what did we earn last month, by zone". That is the whole reason this
-- course exists.
--
-- The pipelines in this repo READ from here and never write. Everything they
-- build lands in a separate schema called "teach", which is created by the
-- pipelines themselves and can be dropped at any time.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS kerb;
SET search_path TO kerb, public;


-- ── zones ──────────────────────────────────────────────────────────────────
-- A dimension: something that IS, rather than something that happened. It has
-- no date column because it is not about a moment in time. Notebook 6 rebuilds
-- this one completely on every run, and explains why that is the right choice
-- here and the wrong choice for trips.
CREATE TABLE zones (
    zone_id       INTEGER PRIMARY KEY,
    zone_name     TEXT NOT NULL,
    borough       TEXT NOT NULL,
    zone_type     TEXT NOT NULL
                  CHECK (zone_type IN ('airport','cbd','residential',
                                       'industrial','suburb','unknown')),
    demand_weight NUMERIC(5,3) NOT NULL DEFAULT 1.0
);


-- ── the people ─────────────────────────────────────────────────────────────
CREATE TABLE drivers (
    driver_id    TEXT PRIMARY KEY,
    joined_at    TIMESTAMPTZ NOT NULL,
    home_zone_id INTEGER REFERENCES zones(zone_id),
    rating       NUMERIC(3,2) CHECK (rating BETWEEN 1 AND 5),
    tier         TEXT NOT NULL CHECK (tier IN ('bronze','silver','gold','platinum')),
    status       TEXT NOT NULL CHECK (status IN ('active','inactive','suspended'))
);

CREATE TABLE riders (
    rider_id     TEXT PRIMARY KEY,
    signed_up_at TIMESTAMPTZ NOT NULL,
    home_zone_id INTEGER REFERENCES zones(zone_id),
    segment      TEXT NOT NULL
                 CHECK (segment IN ('commuter','occasional','business','tourist'))
);


-- ── trips ──────────────────────────────────────────────────────────────────
-- The table the whole course starts from. A few things are deliberate:
--
--   driver_id is NULLABLE, because a ride nobody accepted has no driver. An
--   INNER JOIN to drivers would silently delete every one of those rides, and
--   notebook 7 is largely about that class of bug.
--
--   The four terminal statuses below are the entire contract in notebook 2. If
--   a fifth ever appeared, the pipeline would hold those records rather than
--   guess at what they mean.
--
--   pu_zone_id is nullable, because a small share of rides never resolve to a
--   service zone. Those rides still happened and still earned money.
CREATE TABLE trips (
    trip_id      TEXT PRIMARY KEY,
    rider_id     TEXT NOT NULL REFERENCES riders(rider_id),
    driver_id    TEXT REFERENCES drivers(driver_id),
    requested_at TIMESTAMPTZ NOT NULL,   -- the rider taps Book
    accepted_at  TIMESTAMPTZ,            -- a driver accepts and sets off
    arrived_at   TIMESTAMPTZ,            -- the driver reaches the pickup point
    started_at   TIMESTAMPTZ,            -- the rider is in, the trip begins
    ended_at     TIMESTAMPTZ,            -- dropoff
    pu_zone_id   INTEGER REFERENCES zones(zone_id),
    do_zone_id   INTEGER REFERENCES zones(zone_id),
    distance_km  NUMERIC(7,3),
    duration_s   INTEGER,
    status       TEXT NOT NULL
                 CHECK (status IN ('completed','cancelled_rider',
                                   'cancelled_driver','no_driver')),
    app_version  TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_trips_requested_at ON trips (requested_at);
CREATE INDEX idx_trips_status       ON trips (status);
CREATE INDEX idx_trips_pu_zone      ON trips (pu_zone_id);


-- ── payments ───────────────────────────────────────────────────────────────
-- What KERB knows the moment a ride ends: the rider was charged.
--
-- Whether the money actually reached the bank is a question only the payment
-- processor can answer, and KERB has no route to that database. Notebook 5 is
-- about going and asking over HTTP, and about the three possible answers.
CREATE TABLE payments (
    payment_id   TEXT PRIMARY KEY,
    trip_id      TEXT NOT NULL REFERENCES trips(trip_id) ON DELETE CASCADE,
    payment_type TEXT,      -- upi, card, wallet, cash. Cash never settles.
    status       TEXT NOT NULL
                 CHECK (status IN ('captured','failed','refunded','pending')),
    amount       NUMERIC(10,2) NOT NULL,
    captured_at  TIMESTAMPTZ
);
CREATE INDEX idx_payments_trip       ON payments (trip_id);
CREATE INDEX idx_payments_captured   ON payments (captured_at);
