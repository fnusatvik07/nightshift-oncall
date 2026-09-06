"""Grouping breaches into incidents, before anybody is paged.

## The arithmetic that makes this necessary

Thirteen signals watch one warehouse. When a pipeline dies, six of them breach
in the same cycle, for one reason:

    pipelines_failing        1        the pipeline failed
    warehouse_lag_hours     26        so gold is a day behind
    rides_per_day        4,102        so yesterday looks quiet
    revenue_per_day    612,000        so revenue looks down
    fare_coverage_pct     71.2        so fares look missing
    records_held         3,140        and the held pile grew

Emitting six records means six investigations, six pages, six tickets, six
times the model spend, and a person on call who has to work out they are the
same thing before they can begin.

**Correlate before you page.** One incident, one page, one owner, and the other
five signals attached as corroboration, which is also stronger evidence: six
signals moving together says far more than one moving alone.

## The rules, in the order they are applied

They are deliberately simple and deliberately conservative. A rule that groups
two genuinely separate problems is worse than a rule that misses a grouping,
because the second costs money and the first costs a missed incident.

    1  everything is broken     more than half the board moved at once. That is
                                never six separate problems
    2  the work did not happen  pipelines_failing or warehouse_lag_hours moved,
                                so every other number is downstream of that
    3  same table               signals watching the same table, moving in the
                                same cycle, are one story
    4  otherwise                separate incidents, one each

Rule 2 is the one that earns its keep. If the pipeline did not run, then rides,
revenue and coverage are all wrong **because** of that, and investigating them
separately is five wasted investigations that all end at the same sentence.
"""
from __future__ import annotations

import datetime as dt
import uuid

from events.contract import Incident, SignalBreach

# The signals that explain other signals. If one of these moved, the rest of
# the board is very probably downstream of it, so it leads the incident.
UPSTREAM_FIRST = ("pipelines_failing", "warehouse_lag_hours", "records_held")

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# more than this share of the board moving at once is one event, not many
ESTATE_WIDE_SHARE = 0.5


def _worst(breaches: list[SignalBreach]) -> str:
    return max((b.severity for b in breaches),
               key=lambda s: SEVERITY_ORDER.get(s, 0))


def _lead(breaches: list[SignalBreach]) -> SignalBreach:
    """Which signal leads. The most upstream one, then the most severe."""
    for name in UPSTREAM_FIRST:
        for b in breaches:
            if b.kpi == name:
                return b
    return max(breaches, key=lambda b: (SEVERITY_ORDER.get(b.severity, 0),
                                        abs(b.deviation)))


def _incident(breaches: list[SignalBreach], why: str) -> Incident:
    lead = _lead(breaches)
    related = [b for b in breaches if b.breach_id != lead.breach_id]
    return Incident(
        incident_id=f"INC{uuid.uuid4().hex[:10].upper()}",
        detected_at=dt.datetime.now(dt.timezone.utc),
        primary=lead,
        related=related,
        correlation=why,
        severity=_worst(breaches),
        owners=sorted({b.owner for b in breaches}),
    )


def group(breaches: list[SignalBreach], board_size: int) -> list[Incident]:
    """Turn the breaches from one cycle into as few incidents as is honest."""
    if not breaches:
        return []
    if len(breaches) == 1:
        return [_incident(breaches, "a single signal moved")]

    # ── rule 1 · everything is broken ──────────────────────────────────────
    if board_size and len(breaches) / board_size > ESTATE_WIDE_SHARE:
        return [_incident(
            breaches,
            f"{len(breaches)} of {board_size} signals moved in the same cycle. "
            f"That is one estate wide event, not {len(breaches)} problems, and "
            f"the cause is upstream of all of them.")]

    # ── rule 2 · the work did not happen ───────────────────────────────────
    upstream = [b for b in breaches if b.kpi in UPSTREAM_FIRST[:2]]
    if upstream:
        names = " and ".join(b.kpi for b in upstream)
        return [_incident(
            breaches,
            f"{names} moved in the same cycle, so every other signal here is "
            f"downstream of work that did not happen. Investigating them "
            f"separately would end at the same sentence five times.")]

    # ── rule 3 · same table ────────────────────────────────────────────────
    by_table: dict[str, list[SignalBreach]] = {}
    for b in breaches:
        by_table.setdefault(b.watches, []).append(b)

    incidents = []
    for table, group_of in by_table.items():
        if len(group_of) > 1:
            incidents.append(_incident(
                group_of,
                f"{len(group_of)} signals watching {table} moved in the same "
                f"cycle, so they are one story about that table."))
        else:
            incidents.append(_incident(
                group_of, "a single signal moved, unrelated to the others"))
    return incidents


def explain(incidents: list[Incident]) -> str:
    """One readable line per incident, for a log or a terminal."""
    out = []
    for inc in incidents:
        signals = inc.signal_count
        suffix = "" if signals == 1 else f", grouping {signals} signals"
        out.append(f"{inc.incident_id}  {inc.severity:8} {inc.primary.kpi}{suffix}")
    return "\n".join(out)
