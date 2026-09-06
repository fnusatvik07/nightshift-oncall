"""The supervisor: the main agent that holds the plan.

It does not investigate. It decides who is asked next, carries each answer
forward, and stops when the evidence is enough. It stops early too: if triage
says the number moved for a boring reason, nothing else runs and nobody is
woken.

## The pattern

This is the documented LangChain multi agent shape: **subagents as tools**. Five
specialists, each built with `create_agent`, each wrapped with `@tool`, and one
main agent holding all five. The main agent chooses; the specialists work.

The older `create_supervisor` helper is no longer maintained, and this is what
replaced it.

## The one manual step

`HumanInTheLoopMiddleware` pauses the graph before any tool in `GATED` runs. In
this system that is `request_db_change`: anything that would touch data stops
and asks. A code change does not pause here, because a pull request is already
a human gate by construction, and pausing twice for the same decision teaches
people to click through.

To resume after an interrupt you need a checkpointer, so the graph has
somewhere to keep the paused conversation. That is why one is passed in.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from events.contract import Incident

from .agents import SUPERVISOR_MODEL, build_subagent_tools
from .tools.publish import GATED

SUPERVISOR_PROMPT = """You are the on call engineer for a data platform. A signal
has breached and you are running the investigation.

You do not investigate anything yourself. You have five specialists and you call
them in order, carrying each answer forward to the next.

  1 triage              is this real, and whose is it
  2 investigate_data    what exactly is wrong with the rows
  3 investigate_lineage where did that value enter the platform
  4 remediate           produce the artifacts a person can act on
  5 verify              read the number again and report honestly

THE RULES

Call triage first, always.

If triage says the breach is not real, STOP. Do not call anything else. Say why
in one sentence. Waking four more agents for a public holiday is the failure
this design exists to prevent.

If it is real, call investigate_data, then investigate_lineage, passing the data
finding in. Then call remediate with both findings. Then call verify.

You may stop early if a specialist tells you something that makes the rest
pointless, and say so plainly when you do.

WHAT YOU MUST NOT DO

Do not claim anything is fixed. This system proposes; a person decides. A
change waiting for approval has changed nothing.

Do not skip remediate. Even when the diagnosis is uncertain, the page and the
ticket are the point: a person arriving three hours early with the queries
already run is the outcome, and a confident fix is a bonus.

At the end, write a short handover, in this shape:
  what breached, in one line
  what is wrong, in one line
  where it came from, in one line
  what was produced, listing the page, ticket and change request ids
  what a human needs to do next"""


def build_supervisor(incident: Incident, checkpointer=None):
    """The main agent, with the five specialists as its tools."""
    return create_agent(
        model=SUPERVISOR_MODEL,
        tools=build_subagent_tools(incident),
        system_prompt=SUPERVISOR_PROMPT,
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on=GATED,
            description_prefix="This would change data and needs a person to approve it",
        )],
        checkpointer=checkpointer or InMemorySaver(),
        name="supervisor",
    )


def investigate(incident: Incident, thread_id: str | None = None,
                checkpointer=None, recursion_limit: int = 40) -> dict:
    """Run the whole investigation for one incident.

    Returns the final handover, the steps taken, and whether it stopped for a
    human.
    """
    thread_id = thread_id or incident.incident_id
    saver = checkpointer or InMemorySaver()
    agent = build_supervisor(incident, saver)
    config = {"configurable": {"thread_id": thread_id},
              "recursion_limit": recursion_limit}

    plural = ("A signal has breached." if incident.signal_count == 1 else
              f"{incident.signal_count} signals breached together, and the board "
              f"has grouped them into one incident.")
    opening = f"{plural}\n\n{incident.brief()}\n\nRun the investigation."

    result = agent.invoke({"messages": [{"role": "user", "content": opening}]}, config)

    # An interrupt leaves __interrupt__ on the state. The run is not finished:
    # it is paused, on purpose, waiting for somebody.
    interrupted = bool(result.get("__interrupt__"))

    return {
        "incident_id": incident.incident_id,
        "breach_id": incident.primary.breach_id,
        "thread_id": thread_id,
        "waiting_for_human": interrupted,
        "interrupt": _describe_interrupt(result) if interrupted else None,
        "handover": result["messages"][-1].content if result.get("messages") else "",
        "steps": _steps(result),
    }


def resume(thread_id: str, incident: Incident, approve: bool,
           note: str = "", checkpointer=None) -> dict:
    """Answer a paused investigation: yes or no, with a reason.

    Rejecting is a real outcome and the reason goes back to the agent, which is
    the difference between a human gate and a rubber stamp.
    """
    from langgraph.types import Command

    saver = checkpointer or InMemorySaver()
    agent = build_supervisor(incident, saver)
    config = {"configurable": {"thread_id": thread_id}}

    decision = {"type": "accept" if approve else "reject"}
    if note:
        decision["message"] = note

    result = agent.invoke(Command(resume=[decision]), config)
    return {
        "incident_id": incident.incident_id,
        "approved": approve,
        "handover": result["messages"][-1].content if result.get("messages") else "",
        "steps": _steps(result),
    }


# ── reading the run back ───────────────────────────────────────────────────

def _steps(result: dict) -> list[dict]:
    """Which specialist was called, in what order. This is the audit trail."""
    steps = []
    for m in result.get("messages", []):
        for call in getattr(m, "tool_calls", None) or []:
            steps.append({"tool": call["name"],
                          "args": {k: str(v)[:120] for k, v in (call.get("args") or {}).items()}})
    return steps


def _describe_interrupt(result: dict) -> dict:
    """Turn the paused state into something a person can be shown."""
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return {}
    value = getattr(interrupts[0], "value", interrupts[0])
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        return {k: (str(v)[:2000] if not isinstance(v, (dict, list)) else v)
                for k, v in value.items()}
    return {"detail": str(value)[:2000]}


ONCALL_MODEL_IN_USE = os.environ.get("ONCALL_MODEL", "openai:gpt-5.4-mini")
