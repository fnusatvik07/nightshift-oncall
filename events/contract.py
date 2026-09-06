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
