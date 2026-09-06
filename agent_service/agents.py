"""The five specialists.

Each one answers exactly one question, holds exactly the tools needed to answer
it, and hands back a typed verdict rather than prose.

    1 TRIAGE            is this real, and whose is it?
    2 DATA DETECTIVE    what is wrong with the rows?
    3 LINEAGE DETECTIVE where did that value enter the platform?
    4 REMEDIATION       what is the smallest thing that fixes it?
    5 VERIFIER          did the number actually come back?

## Why five and not one

An agent with every tool will use every tool. The data detective cannot open a
file, so it cannot guess from the code and call it evidence. The lineage
detective cannot query the warehouse, so it cannot quietly re-do the previous
agent's work with worse tools. Narrow the toolbox and the method emerges from
the constraint rather than from the prompt.

## Why every one returns a schema

`response_format` makes each agent hand back a pydantic object. Prose is
readable and unusable: the supervisor cannot branch on a paragraph. A typed
`is_real: bool` is what lets the whole thing stop early and cheaply.

## What is deliberately not written down anywhere

There is no list of known incidents. Nowhere does any prompt say "if surge is
missing, look in MongoDB". The agents are given a method and a toolbox, not the
answers, which is why a problem nobody has seen before is still worked the same
way.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain.tools import tool
from pydantic import BaseModel, Field

from events.contract import Incident

from .tools.lineage import LINEAGE_TOOLS
from .tools.page import CONFLUENCE_TOOLS
from .tools.publish import PUBLISH_TOOLS
from .tools.verify import VERIFY_TOOLS
from .tools.warehouse import READ_TOOLS
from .tools.signals import SIGNAL_TOOLS

MODEL = os.environ.get("ONCALL_MODEL", "openai:gpt-5.4-mini")
SUPERVISOR_MODEL = os.environ.get("ONCALL_SUPERVISOR_MODEL", MODEL)


# ═══════════════════════════════════════════════════════════════════════════
# The verdicts. Each agent's answer, typed.
# ═══════════════════════════════════════════════════════════════════════════

class TriageVerdict(BaseModel):
    is_real: bool = Field(description="is this damage, or a boring reason a number moved")
    severity: str = Field(description="low, medium, high or critical")
    owner: str = Field(description="the team this belongs to")
    start_at: str = Field(description="the table or system to look at first")
    reason: str = Field(description="one or two sentences a person can read")


class DataVerdict(BaseModel):
    finding: str = Field(description="what is actually wrong with the rows")
    evidence: str = Field(description="the queries run and the numbers returned")
    affected_table: str = Field(description="where the wrong values live")
    affected_column: str = Field(default="", description="the column, if it is one column")
    scale: str = Field(description="how many rows, and over what period")
    confidence: str = Field(description="high, medium or low")


class LineageVerdict(BaseModel):
    entered_at: str = Field(description="the pipeline or layer where the value first went wrong")
    cause: str = Field(description="what caused it, as specifically as the evidence allows")
    evidence: str = Field(description="the files read and what was found, plus anything from git")
    recent_change: str = Field(default="", description="a recent change that fits, or empty")
    confidence: str = Field(description="high, medium or low")


class RemediationVerdict(BaseModel):
    kind: str = Field(description="code_change, db_change, or investigate")
    summary: str = Field(description="the proposed fix in one line")
    artifacts: str = Field(description="what was produced: page id, ticket id, change request id")
    waiting_for_human: bool = Field(description="true when nothing can proceed without approval")


class VerifierVerdict(BaseModel):
    resolved: bool = Field(description="has the number actually come back to normal")
    change_applied: bool = Field(
        description="is the change on disk, or still waiting on a branch")
    pipeline_ran: bool = Field(default=False,
        description="was a pipeline re-run, and did it succeed")
    invariants_held: bool = Field(default=True,
        description="did every invariant still hold afterwards")
    current_value: str = Field(description="what the number is now, against its baseline")
    checked: str = Field(description="what was re-read, and what each thing said")
    recommendation: str = Field(description="what should happen next")


# ═══════════════════════════════════════════════════════════════════════════
# 1 · Triage. Cheap on purpose.
# ═══════════════════════════════════════════════════════════════════════════

TRIAGE_PROMPT = """You decide whether a number that moved is worth investigating.

Numbers move for boring reasons: a public holiday, a new city launching, a
backfill, a deliberate change somebody announced. Before anything else, decide
whether this is damage.

You are cheap on purpose, so that the expensive agents are never woken for
noise. You cannot query the database and you cannot read code. If you could
investigate, you would investigate everything, and a full diagnosis would be
paid for every time a number wobbled.

What you can do is look at the whole board. One signal moving is a question.
Six moving together is usually one cause, and often an upstream one.

Judge it on:
  how far the number is from normal, in the units of the thing itself
  what the KPI description says it means, which is written for its owner
  whether other signals moved at the same time
  whether the direction is the one that is actually bad

Be willing to say no. A triage agent that says yes to everything has cost you
the money it was there to save."""


def triage_agent():
    return create_agent(
        model=MODEL,
        tools=SIGNAL_TOOLS,
        system_prompt=TRIAGE_PROMPT,
        response_format=TriageVerdict,
        name="triage",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2 · Data detective. Reads rows. Cannot read code.
# ═══════════════════════════════════════════════════════════════════════════

DATA_PROMPT = """You find out what is actually wrong with the data.

You can query the warehouse, read only. You cannot open a source file, so you
cannot guess from the code and present it as evidence. Everything you report
must be something a query returned.

A method that works, in this order:

  1 look at the run log first. A pipeline that did not run leaves perfectly
    valid rows behind, and every value check passes. Rule that out before
    anything else.
  2 look at what is being held. Quarantine is the loudest evidence in the
    warehouse, and it comes with the reason attached and the payload intact.
  3 profile the column the KPI is about. How many rows, how many missing, how
    many distinct.
  4 split it. By day, by version, by source, by whatever column exists. The
    shape of the split is usually the answer: "all of it, since Tuesday" and
    "only from one app version" are different incidents.

Quote real numbers. "Many rows are null" is not evidence. "40,000 of 84,689,
all of them since 2026-08-19" is.

Say so plainly when the data looks fine. That is a useful finding, and it moves
the investigation to the pipeline rather than the rows."""


def data_agent():
    return create_agent(
        model=MODEL,
        tools=READ_TOOLS,
        system_prompt=DATA_PROMPT,
        response_format=DataVerdict,
        name="data_detective",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3 · Lineage detective. Reads code and history. Cannot read rows.
# ═══════════════════════════════════════════════════════════════════════════

LINEAGE_PROMPT = """You find where a wrong value entered the platform.

You can read pipeline and service source, search it, read the contracts, and
read recent git history. You cannot query the database: the previous agent has
already established what is wrong with the rows, and re-doing that badly with
the wrong tools helps nobody.

A method that works:

  1 find the pipeline that writes the affected table. search_code is faster
    than reading files.
  2 read its contract. The contract is the list of values that pipeline knows
    how to interpret, and a value arriving outside it is the single most common
    cause of a column going quiet.
  3 read the part of the pipeline that produces the affected column, whole.
  4 ask what changed recently. Most incidents are somebody's Tuesday afternoon,
    and the commit message usually says what they thought they were doing.

Be specific about the layer. "Something upstream" is not a finding. "The
contract in p3_bronze_driver_app knows four paths for surge and the documents
are arriving with a fifth" is.

If the code looks correct, say so. That points at the source system, which is
somebody else's estate and a different conversation."""


def lineage_agent():
    return create_agent(
        model=MODEL,
        tools=LINEAGE_TOOLS,
        system_prompt=LINEAGE_PROMPT,
        response_format=LineageVerdict,
        name="lineage_detective",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4 · Remediation. Writes artifacts. Never writes data.
# ═══════════════════════════════════════════════════════════════════════════

REMEDIATION_PROMPT = """You turn a diagnosis into something a person can act on.

You change nothing. You produce artifacts, and a human decides.

ALWAYS, without exception:
  publish_incident_page  the Confluence page: what happened, a diagram of where
              it breaks, the evidence with the real queries and their real
              output, what it means and what to do. Write it for the owner, who
              was asleep and has never read this code. Do this even when you are
              not confident, and say so in the confidence field.
              If it reports that Confluence is not configured, use write_spec
              instead so the diagnosis is at least kept locally.
  raise_ticket  so it is somebody's, with a severity and an owner.

THEN, depending on what the fix actually is:

  If the fix is a CODE change, use propose_code_change. It opens a branch and a
  pull request in an isolated checkout. It never merges and it never touches
  the main branch. Make the change as small as the diagnosis allows: one line
  that adds a known path beats a refactor nobody asked for. Read the file first
  with read_source and copy the exact text you are replacing.

  Then put it on the page. propose_code_change hands you back a diff and, when
  a remote exists, a pull request URL. Pass BOTH to publish_incident_page as
  change_diff and pull_request, and describe the change in words in
  proposed_change.

  If no pull request could be opened, that changes nothing about your job: fill
  in proposed_change and change_diff anyway. A reader who has to work the fix
  out again from the evidence has been given a diagnosis, not a page.

  If the fix would change DATA, use request_db_change. That tool runs nothing.
  It records the statement, estimates the blast radius, states how to reverse
  it, and stops for a human. Never propose a data change without saying how to
  undo it.

  If you do not know the fix, that is a legitimate outcome. The page and the
  ticket are still worth having: a person arriving at a diagnosis three hours
  early, with the queries already run, is the point.

Rules you do not get to break:
  never claim something is fixed. You proposed. Somebody else decides.
  never change data. Not through a tool, not by asking another agent.
  smallest change that addresses the cause, and say what it does not address."""


def remediation_agent():
    return create_agent(
        model=MODEL,
        # it may read the file it is about to propose changing, and nothing else
        tools=[*CONFLUENCE_TOOLS, *PUBLISH_TOOLS,
               LINEAGE_TOOLS[1], LINEAGE_TOOLS[4]],
        system_prompt=REMEDIATION_PROMPT,
        response_format=RemediationVerdict,
        name="remediation",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5 · Verifier. Reads the number again.
# ═══════════════════════════════════════════════════════════════════════════

VERIFIER_PROMPT = """You prove whether a change worked. You do not take anybody's
word for it, including the previous agent's.

An agent will happily tell you it fixed something. Your job is to show a
pipeline that ran and a number that moved, or to say plainly that neither
happened.

THE ORDER THAT WORKS

  1 check_file_on_disk. Is the change actually applied, or is it sitting on a
    branch waiting for a human? A proposal that is waiting has fixed NOTHING,
    and this is the single most common way an incident gets closed while still
    broken. If it is not on disk, stop here and say so.

  2 run_pipeline, if and only if the change is on disk. A fix in bronze does
    not reach the number a signal watches until silver and gold have run, so
    leave with_downstream on unless you have a reason not to.

  3 run_invariants. This is how you tell "the number came back" apart from "the
    number came back and something else broke". A fix that resolves one signal
    and violates an invariant is not a fix.

  4 get_signal, on the signal that started this. Compare it to the baseline in
    the breach you were given. That last pair is the only thing that counts as
    success.

WHAT YOU MUST NOT DO

Do not report resolved because a change was proposed. Proposed is not applied.

Do not report resolved because a pipeline ran. A pipeline running is not a
number moving.

A FAILING PIPELINE IS SOMETIMES CORRECT. If the fix was a guard that refuses
bad input, then the pipeline failing on that input is the guard working. Read
the output and say which it is, rather than assuming a non zero exit is a
broken change."""


def verifier_agent():
    return create_agent(
        model=MODEL,
        tools=[*VERIFY_TOOLS, *READ_TOOLS, *SIGNAL_TOOLS],
        system_prompt=VERIFIER_PROMPT,
        response_format=VerifierVerdict,
        name="verifier",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Wrapping each one as a tool the supervisor can call.
#
# This is the documented multi agent pattern in LangChain: subagents as tools.
# The supervisor decides who is asked next and carries the answer forward.
# Each subagent is stateless and starts in a clean context, which is what stops
# the fifth agent inheriting four agents' worth of noise.
# ═══════════════════════════════════════════════════════════════════════════

def _run(agent, instruction: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": instruction}]})
    structured = result.get("structured_response")
    if structured is not None:
        return structured.model_dump_json(indent=2)
    return result["messages"][-1].content


def build_subagent_tools(incident: Incident):
    """Build the five tools, each closed over this specific incident.

    An incident may carry several signals that moved for one reason. Every
    specialist sees all of them, because six signals moving together is far
    stronger evidence than one moving alone, and the corroboration usually
    points straight at the layer to start from.
    """
    breach = incident.primary

    context = (
        f"{incident.brief()}\n\n"
        f"THE LEAD SIGNAL, IN FULL\n"
        f"  breach id  {breach.breach_id}\n"
        f"  direction  {breach.direction}\n"
        f"  history    {breach.history}\n"
        f"  the query  {breach.evaluated_sql}\n"
    )

    @tool("triage", description=(
        "Decide whether this breach is real and worth investigating, and whose it is. "
        "Call this first, always. If it says the breach is not real, stop."))
    def call_triage() -> str:
        return _run(triage_agent(), context + "\nIs this real, and whose is it?")

    @tool("investigate_data", description=(
        "Find out what is actually wrong with the rows. Queries the warehouse. "
        "Call this after triage says the breach is real."))
    def call_data(focus: str = "") -> str:
        return _run(data_agent(), context + f"\nWhat is wrong with the data? {focus}")

    @tool("investigate_lineage", description=(
        "Find where the wrong value entered the platform. Reads pipeline code and "
        "git history. Call this after investigate_data, and pass its finding in."))
    def call_lineage(data_finding: str) -> str:
        return _run(lineage_agent(), context +
                    f"\nThe data detective found:\n{data_finding}\n\n"
                    f"Where did this enter the platform?")

    @tool("remediate", description=(
        "Produce the artifacts: always a page and a ticket, plus a pull request for a "
        "code fix or an approval request for a data change. Pass in everything learned "
        "so far. This never changes data."))
    def call_remediation(data_finding: str, lineage_finding: str) -> str:
        return _run(remediation_agent(), context +
                    f"\nThe data detective found:\n{data_finding}\n\n"
                    f"The lineage detective found:\n{lineage_finding}\n\n"
                    f"Produce the artifacts. Change nothing.")

    @tool("verify", description=(
        "Re-read the number and report whether it came back. Call this last."))
    def call_verifier(what_was_proposed: str) -> str:
        return _run(verifier_agent(), context +
                    f"\nWhat was proposed:\n{what_was_proposed}\n\n"
                    f"Has the number come back?")

    return [call_triage, call_data, call_lineage, call_remediation, call_verifier]
