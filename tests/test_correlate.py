"""Grouping, tested.

The rules decide whether one broken pipeline produces one page or six. Getting
them wrong in either direction is expensive:

    too eager   two real problems become one incident, and one gets missed
    too shy     one cause becomes six investigations and six times the spend

So each rule gets a test that pins the behaviour, and one that pins the
behaviour it must NOT have.
"""
from __future__ import annotations

import datetime as dt

from events.contract import SignalBreach
from signal_service import correlate


def breach(kpi: str, owner: str = "ops", watches: str = "teach.gold_daily",
           severity: str = "medium", value: float = 1.0) -> SignalBreach:
    return SignalBreach(
        breach_id=f"BRC-{kpi}", detected_at=dt.datetime.now(dt.timezone.utc),
        kpi=kpi, title=kpi, value=value, baseline=0.0, deviation=value,
        severity=severity, owner=owner, watches=watches, means=f"about {kpi}")


# ── rule 1 · everything is broken ──────────────────────────────────────────

def test_most_of_the_board_moving_is_one_incident():
    """Seven of thirteen signals moving is one event, not seven problems."""
    breaches = [breach(f"kpi_{i}", watches=f"table_{i}") for i in range(7)]
    incidents = correlate.group(breaches, board_size=13)

    assert len(incidents) == 1
    assert incidents[0].signal_count == 7
    assert "estate wide" in incidents[0].correlation


def test_a_minority_of_the_board_is_not_automatically_one_incident():
    """Two unrelated signals on two tables stay two incidents."""
    breaches = [breach("a", watches="teach.gold_daily"),
                breach("b", watches="teach.bronze_events")]
    incidents = correlate.group(breaches, board_size=13)
    assert len(incidents) == 2


# ── rule 2 · the work did not happen ───────────────────────────────────────

def test_a_failed_pipeline_absorbs_everything_else():
    """If the work did not happen, every other number is downstream of that."""
    breaches = [
        breach("rides_per_day", watches="teach.gold_daily"),
        breach("revenue_per_day", owner="finance", watches="teach.gold_daily"),
        breach("pipelines_failing", owner="data-platform", watches="teach.runs",
               severity="critical"),
    ]
    incidents = correlate.group(breaches, board_size=13)

    assert len(incidents) == 1
    assert incidents[0].primary.kpi == "pipelines_failing"
    assert incidents[0].signal_count == 3
    assert "downstream" in incidents[0].correlation


def test_warehouse_lag_also_leads():
    breaches = [breach("avg_fare", owner="pricing"),
                breach("warehouse_lag_hours", owner="data-platform",
                       watches="teach.gold_daily")]
    incidents = correlate.group(breaches, board_size=13)
    assert len(incidents) == 1
    assert incidents[0].primary.kpi == "warehouse_lag_hours"


# ── rule 3 · same table ────────────────────────────────────────────────────

def test_signals_watching_the_same_table_are_one_story():
    breaches = [breach("completion_rate", watches="teach.gold_daily"),
                breach("cancellation_rate", watches="teach.gold_daily"),
                breach("events_per_ride", watches="teach.bronze_events")]
    incidents = correlate.group(breaches, board_size=13)

    assert len(incidents) == 2
    grouped = [i for i in incidents if i.signal_count == 2]
    assert len(grouped) == 1
    assert grouped[0].primary.watches == "teach.gold_daily"


# ── the incident itself ────────────────────────────────────────────────────

def test_a_single_breach_still_becomes_an_incident():
    """One signal is still an incident, so the agent has one shape to handle."""
    incidents = correlate.group([breach("surge_coverage_pct")], board_size=13)
    assert len(incidents) == 1
    assert incidents[0].signal_count == 1
    assert incidents[0].related == []


def test_nothing_in_means_nothing_out():
    assert correlate.group([], board_size=13) == []


def test_severity_is_the_worst_of_the_group():
    breaches = [breach("a", severity="low", watches="t"),
                breach("b", severity="critical", watches="t")]
    assert correlate.group(breaches, board_size=13)[0].severity == "critical"


def test_owners_are_collected_and_deduplicated():
    breaches = [breach("a", owner="pricing", watches="t"),
                breach("b", owner="finance", watches="t"),
                breach("c", owner="pricing", watches="t")]
    incident = correlate.group(breaches, board_size=13)[0]
    assert incident.owners == ["finance", "pricing"]


def test_every_breach_survives_the_grouping():
    """Grouping must never lose a signal. Losing one is a missed incident."""
    breaches = [breach(f"kpi_{i}", watches="teach.gold_daily") for i in range(6)]
    incidents = correlate.group(breaches, board_size=13)

    kept = {b.breach_id for inc in incidents for b in inc.breaches}
    assert kept == {b.breach_id for b in breaches}


def test_the_brief_names_every_signal():
    """The agent must be told about the corroborating signals, not just the lead."""
    breaches = [breach("pipelines_failing", watches="teach.runs"),
                breach("rides_per_day", watches="teach.gold_daily"),
                breach("revenue_per_day", watches="teach.gold_daily")]
    brief = correlate.group(breaches, board_size=13)[0].brief()

    for name in ("pipelines_failing", "rides_per_day", "revenue_per_day"):
        assert name in brief
