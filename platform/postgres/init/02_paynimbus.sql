-- ═══════════════════════════════════════════════════════════════════════════
-- PayNimbus: a different company.
--
-- It gets its own database, on purpose, so that nobody can quietly join across
-- the boundary. KERB cannot read this, exactly as it could not read a real
-- payment processor's ledger. The only way to learn anything here is to ask
-- the API, which is what notebook 5 does.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE DATABASE paynimbus;
\connect paynimbus

CREATE TABLE settlements (
    settlement_id TEXT PRIMARY KEY,      -- PayNimbus's id, not KERB's
    merchant_ref  TEXT NOT NULL UNIQUE,  -- the payment_id KERB sent us
    rail          TEXT NOT NULL,         -- upi, card, wallet. Never cash.
    gross         NUMERIC(10,2) NOT NULL,-- what the rider was charged
    fee           NUMERIC(10,2) NOT NULL,-- what PayNimbus keeps
    net           NUMERIC(10,2) NOT NULL,-- what actually reaches KERB's bank
    currency      TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('in_flight','settled','failed')),
    captured_at   TIMESTAMPTZ NOT NULL,  -- when KERB took the money
    settled_at    TIMESTAMPTZ,           -- when it reaches the bank. NULL until it does.
    retry_count   INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_settlements_ref    ON settlements (merchant_ref);
CREATE INDEX idx_settlements_status ON settlements (status);
