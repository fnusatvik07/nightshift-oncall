"""The one record that crosses the line between the two services.

The signal board emits it. The agent system consumes it. Nothing else in the
project depends on it, and neither service defines it, which is the point: a
contract owned by one side is not a contract, it is an interface you are
allowed to change unilaterally.

Everything the agent needs to start work is in here. If the agent has to call
back to the signal board to find out what happened, the record is incomplete.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]


class SignalBreach(BaseModel):
    """A number moved, and here is everything a person would want to know.

    Read the fields as the four questions somebody asks when woken up:

        what moved            kpi, value, baseline, direction
        how far               deviation, severity
        whose is it           owner
        where do I start      watches, means
    """

    # ── identity ───────────────────────────────────────────────────────────
    breach_id: str = Field(description="stable id, so the same breach is not worked twice")
    detected_at: dt.datetime

    # ── what moved ─────────────────────────────────────────────────────────
    kpi: str = Field(description="the kpi name, e.g. surge_coverage_pct")
    title: str = Field(description="the kpi in words, for a human")
    value: float
    baseline: float
    unit: str = ""
    direction: Literal["above", "below"] = "above"
    deviation: float = Field(description="how far from baseline, in the unit of the kpi")
    z_score: float | None = Field(default=None, description="only when the baseline came from history")

    # ── whose, and where to start ──────────────────────────────────────────
    severity: Severity = "medium"
    owner: str = Field(description="the team, by name. Not 'the data team'")
    watches: str = Field(description="the table or system this kpi reads")
    means: str = Field(description="what the number means, written for the owner")

    # ── context the agent would otherwise have to go and fetch ─────────────
    history: list[float] = Field(default_factory=list,
                                 description="recent readings, oldest first")
    evaluated_sql: str = Field(default="", description="the exact query that produced the value")

    def fingerprint(self) -> str:
        """The same kpi breaching the same way is the same incident.

        Without this, a board on a five minute clock opens 288 investigations a
        day for one broken pipeline, and the agent system becomes the outage.
        """
        raw = f"{self.kpi}|{self.direction}|{round(self.value, 3)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "SignalBreach":
        return cls.model_validate(json.loads(raw))

    def one_line(self) -> str:
        arrow = "up" if self.direction == "above" else "down"
        return (f"{self.kpi} is {arrow} at {self.value:,.3f}{self.unit} "
                f"against a baseline of {self.baseline:,.3f}{self.unit} "
                f"({self.severity}, {self.owner})")


class Incident(BaseModel):
    """One cause, however many signals noticed it.

    This is the record that actually crosses between the two services, and the
    reason it exists is arithmetic. Thirteen signals watch one warehouse. When a
    pipeline dies, six of them breach in the same cycle, for one reason. Emitting
    six records means six investigations, six pages, six tickets and six times
    the model spend, for a single cause, and the person on call has to work out
    that they are the same thing before they can start.

    So the board correlates before it pages. The agent receives one incident with
    a primary signal and the others attached as corroboration, which is also
    better evidence: six signals moving together is a much stronger statement
    than one signal moving alone.
    """

    incident_id: str
    detected_at: dt.datetime

    primary: SignalBreach = Field(
        description="the signal to lead with, usually the most upstream one")
    related: list[SignalBreach] = Field(
        default_factory=list, description="the others that moved for the same reason")

    correlation: str = Field(
        description="why these were grouped, in words a person can check")
    severity: Severity = "medium"
    owners: list[str] = Field(default_factory=list)

    @property
    def breaches(self) -> list[SignalBreach]:
        return [self.primary, *self.related]

    @property
    def signal_count(self) -> int:
        return 1 + len(self.related)

    def one_line(self) -> str:
        if not self.related:
            return self.primary.one_line()
        others = ", ".join(b.kpi for b in self.related)
        return (f"{self.primary.one_line()}  "
                f"(and {len(self.related)} more: {others})")

    def brief(self) -> str:
        """Everything an agent needs to start, as text rather than JSON."""
        lines = [f"INCIDENT {self.incident_id}   severity {self.severity}",
                 f"  why grouped: {self.correlation}",
                 f"  owners:      {', '.join(self.owners)}",
                 "",
                 "  LEAD SIGNAL"]
        b = self.primary
        lines += [f"    {b.kpi}  ({b.title})",
                  f"    value {b.value}{b.unit}, normally {b.baseline}{b.unit}, "
                  f"{b.direction}",
                  f"    watches {b.watches}",
                  f"    means   {b.means}"]
        if self.related:
            lines += ["", "  ALSO MOVED, at the same time"]
            for r in self.related:
                lines.append(f"    {r.kpi:26} {r.value:>12,.3f}{r.unit:<4} "
                             f"normally {r.baseline:>12,.3f}   {r.owner}")
        return "\n".join(lines)
