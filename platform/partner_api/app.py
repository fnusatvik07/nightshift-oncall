"""PayNimbus: the payment processor KERB uses. A different company.

This service reads the `paynimbus` database, which KERB has no access to. That
separation is the entire point. PayNimbus is the only party that knows whether
a charge actually cleared, what it kept as a fee, and when the money reached
KERB's bank account.

One endpoint matters: a lookup. KERB sends the references it is still waiting
on, and PayNimbus answers for the ones that have resolved.

Two behaviours here are deliberate, and both are lessons in notebook 5.

    A charge that has not resolved is simply ABSENT from the answer. It is not
    an error and it is not a null. A processor does not know the future either.

    A share of answers arrive with status "". Not "failed", not "settled", an
    empty string, because the field was never set and the wire format has no
    null for a scalar string. Money in that state can neither be recognised as
    revenue nor chased as missing, and defaulting it either way is a lie to
    somebody in finance.

Both are tunable through environment variables, so an instructor can turn the
empty statuses off for a clean run or up for a dramatic one.
"""
from __future__ import annotations

import os
import random
from typing import Optional

import psycopg
from fastapi import Body, FastAPI
from pydantic import BaseModel, Field

DSN = os.environ["PN_DSN"]

# what share of resolved settlements come back with an unreadable status
EMPTY_STATUS_SHARE = float(os.environ.get("PN_EMPTY_STATUS_SHARE", "0.34"))

app = FastAPI(title="PayNimbus", version="1.0")


@app.get("/health")
def health():
    with psycopg.connect(DSN) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM settlements")
        n = cur.fetchone()[0]
    return {"ok": True, "settlements_on_file": n,
            "empty_status_share": EMPTY_STATUS_SHARE}


class Lookup(BaseModel):
    refs: list[str] = Field(..., max_length=1000,
                            description="the merchant references you are waiting on")
    as_of: Optional[str] = Field(None,
                                 description="only report what had resolved by this date")


# Status is DERIVED, not read from the column.
#
# `settled_at` is when the money is due to reach the bank, and a charge counts
# as settled once that moment has passed. Reading a frozen status column
# instead was wrong in a way that only showed up over time: the ledger is
# written once at seed time, so a charge that was in flight then would stay in
# flight forever while the clock moved on. A real processor's ledger is live.
LOOKUP_SQL = """
    SELECT settlement_id, merchant_ref, rail, gross, fee, net, currency,
           CASE WHEN status = 'failed'   THEN 'failed'
                WHEN settled_at IS NULL  THEN 'in_flight'
                WHEN settled_at <= now() THEN 'settled'
                ELSE 'in_flight' END      AS status,
           captured_at,
           CASE WHEN status <> 'failed' AND settled_at <= now()
                THEN settled_at END       AS settled_at,
           retry_count
    FROM settlements
    WHERE merchant_ref = ANY(%s)
      AND (status = 'failed' OR (settled_at IS NOT NULL AND settled_at <= now()))
"""


@app.post("/v1/settlements/lookup")
def lookup(body: Lookup = Body(...)):
    """Which of these charges have resolved, and how?"""
    if not body.refs:
        return {"count": 0, "settlements": []}

    sql, params = LOOKUP_SQL, [body.refs]
    if body.as_of:
        # a processor cannot tell you about a settlement that has not happened
        sql += " AND (settled_at IS NULL OR settled_at::date <= %s)"
        params.append(body.as_of)

    with psycopg.connect(DSN) as c, c.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    out = []
    for sid, ref, rail, gross, fee, net, ccy, status, cap, setl, retries in rows:
        if EMPTY_STATUS_SHARE and random.random() < EMPTY_STATUS_SHARE:
            status = ""          # the field was never set. See the module docstring.
        out.append({
            "settlement_id": sid,
            "merchant_ref": ref,
            "rail": rail,
            "gross": float(gross),
            "fee": float(fee),
            "net": float(net),
            "currency": ccy,
            "status": status,
            "retry_count": retries,
            "captured_at": cap.isoformat() if cap else None,
            "settled_at": setl.isoformat() if setl else None,
        })
    return {"count": len(out), "settlements": out}
