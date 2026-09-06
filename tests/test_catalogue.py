"""The KPI catalogue and the invariants, checked for the things that rot.

These are cheap tests over data rather than behaviour, and they catch the class
of mistake that only shows up at 3am: a KPI with no owner, a signal with no
baseline, two KPIs with the same name, a query that returns a table.
"""
from __future__ import annotations

import pytest

from signal_service.invariants import INVARIANTS
from signal_service.kpis import CATALOGUE, BY_NAME


@pytest.mark.parametrize("kpi", CATALOGUE, ids=lambda k: k.name)
class TestEveryKPI:

    def test_has_an_owner_who_is_not_the_data_team(self, kpi):
        """'the data team' is not an owner, it is a way of nobody looking."""
        assert kpi.owner
        assert kpi.owner.lower() not in ("data", "the data team", "team", "tbd")

    def test_says_what_it_means_for_that_owner(self, kpi):
        """They read this at 3am having never seen the code."""
        assert len(kpi.means) > 60, "means is too short to be useful at 3am"

    def test_can_actually_be_judged(self, kpi):
        """A KPI with no way to decide 'is this bad' is a number, not a signal."""
        if kpi.judgement == "fixed":
            assert kpi.baseline is not None
        else:
            assert kpi.history_sql, "a history baseline needs a history query"

    def test_watches_a_real_looking_table(self, kpi):
        assert "." in kpi.watches

    def test_severity_is_one_of_the_four(self, kpi):
        assert kpi.severity in ("low", "medium", "high", "critical")

    def test_direction_is_declared(self, kpi):
        assert kpi.watch_direction in ("both", "above", "below")


def test_names_are_unique():
    assert len(BY_NAME) == len(CATALOGUE)


def test_coverage_kpis_only_fire_downwards():
    """Coverage going UP is good news. A signal that fires on good news is noise."""
    for kpi in CATALOGUE:
        if kpi.name.endswith("_coverage_pct"):
            assert kpi.watch_direction == "below", kpi.name


def test_count_kpis_only_fire_upwards():
    """Held records falling is a Tuesday, not an incident."""
    for name in ("records_held", "pipelines_failing", "warehouse_lag_hours"):
        assert BY_NAME[name].watch_direction == "above"


def test_a_zero_baseline_has_no_generous_tolerance():
    """'Should be zero' means zero. A tolerance on it defeats the point."""
    for kpi in CATALOGUE:
        if kpi.judgement == "fixed" and kpi.baseline == 0:
            assert kpi.tolerance <= 30, kpi.name


@pytest.mark.parametrize("inv", INVARIANTS, ids=lambda i: i.name)
class TestEveryInvariant:

    def test_returns_violations_not_a_boolean(self, inv):
        """The shape is 'the rows that break it', so a failure hands you evidence."""
        assert inv.sql.strip().upper().startswith("SELECT")

    def test_says_what_it_means(self, inv):
        assert len(inv.means) > 40

    def test_names_a_layer(self, inv):
        assert inv.layer in ("bronze", "silver", "gold", "platform")


def test_invariant_names_are_unique():
    assert len({i.name for i in INVARIANTS}) == len(INVARIANTS)


def test_there_are_invariants_at_every_layer():
    """A layer with no invariant is a layer nobody is checking."""
    layers = {i.layer for i in INVARIANTS}
    assert layers == {"bronze", "silver", "gold", "platform"}
