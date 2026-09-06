# The on call agents

Asleep until a record arrives. Then they do what a good engineer does at 3am,
without the fetching.

Built with **LangChain 1.x**, using the documented **subagents as tools**
pattern. The older `create_supervisor` helper is no longer maintained.

---

## The shape

```mermaid
flowchart TB
    REC["a SignalBreach<br/><i>arrives on POST /breach</i>"]
    SUP{{"THE SUPERVISOR<br/>holds the plan<br/><i>investigates nothing</i>"}}

    T["<b>1 triage</b><br/>is this real?"]
    STOP(["STOP<br/><i>nobody is woken</i>"])
    D["<b>2 data detective</b><br/>what is wrong?"]
    L["<b>3 lineage detective</b><br/>where from?"]
    R["<b>4 remediation</b><br/>what is the fix?"]
    V["<b>5 verifier</b><br/>did it work?"]
    OUT["a page, a ticket,<br/>maybe a pull request"]

    REC --> SUP --> T
    T -->|"not real"| STOP
    T -->|"real"| D --> L --> R --> V --> OUT

    classDef rec fill:#FFFBEB,stroke:#B45309,stroke-width:2px,color:#111
    classDef ag fill:#EFF4FF,stroke:#1D4ED8,stroke-width:2px,color:#111
    classDef out fill:#ECFDF5,stroke:#047857,stroke-width:2px,color:#111
    classDef stop fill:#F4F4F5,stroke:#6B7280,stroke-width:2px,color:#111
    class REC,SUP rec
    class T,D,L,R,V ag
    class OUT out
    class STOP stop
```

---

## Why five and not one

> **An agent with every tool will use every tool.**

Give one agent SQL and file reading and it will read a file, form a theory, and
then go looking for numbers that agree with it. Split them and that becomes
impossible.

| Agent | Answers | Tools | Deliberately cannot |
|---|---|---|---|
| **1 triage** | is this real? | the signal board | query, or read code |
| **2 data detective** | what is wrong with the rows? | 7 read only warehouse tools | open a file |
| **3 lineage detective** | where did it enter? | 5 code and git tools | query the warehouse |
| **4 remediation** | what is the smallest fix? | the publishing tools | change data |
| **5 verifier** | did the number come back? | warehouse and board | change anything |

**The data detective cannot open a file**, so everything it reports came from a
query rather than from a theory.

**The lineage detective cannot query**, so it cannot quietly redo the previous
agent's work with worse tools.

Narrow the toolbox and the method emerges from the constraint, rather than from
a longer prompt everybody hopes the model reads.

---

## Triage is cheap, and runs first

If triage says the number moved for a boring reason, **nothing else runs**. Four
expensive agents are never woken and nobody is paged for a public holiday.

> Be willing to say no. A triage agent that says yes to everything has cost you
> the money it was there to save.

It can see the whole board, because one signal moving is a question and six
moving together is usually one cause, and often an upstream one.

---

## Every agent returns a schema

```python
class TriageVerdict(BaseModel):
    is_real: bool
    severity: str
    owner: str
    start_at: str
    reason: str
```

Prose is readable and unusable: a supervisor cannot branch on a paragraph.
`is_real` is a real python boolean, and that is what lets the whole thing stop
early and cheaply.

---

## Subagents as tools

```python
subagent = create_agent(model=..., tools=[...], response_format=DataVerdict)

@tool("investigate_data", description="Find what is wrong with the rows...")
def call_data(focus: str = "") -> str:
    result = subagent.invoke({"messages": [{"role": "user", "content": ...}]})
    return result["structured_response"].model_dump_json(indent=2)

supervisor = create_agent(model=..., tools=[call_triage, call_data, ...])
```

The specialists are **stateless** and start in a clean context every time, which
stops the fifth agent inheriting four agents' worth of noise.

The supervisor decides who is asked next, carries each answer forward, and stops
when the evidence is enough. **It investigates nothing itself.**

---

## What is deliberately not written down

There is **no list of known incidents** anywhere in this project. No prompt says
"if surge is missing, look in MongoDB". No rule maps a signal to a cause.

The agents are given a method and a toolbox, not the answers. That is why a
problem nobody has seen before is worked exactly like one that has.

---

## What it may produce

| Always | When the fix is code | When the fix touches data |
|---|---|---|
| a Confluence page, with a diagram | a branch and a **pull request** | an approval request |
| a ticket, with an owner and severity | never a merge, never main | **the graph stops** |
| | two directories only | nothing is executed, ever |

### Why a page is always produced

The most common outcome of an investigation is not a fix. It is a diagnosis,
some evidence, and a decision that belongs to somebody who was asleep.

**A system that only produces output when it is confident produces nothing on
the nights you needed it most.**

---

## The guards, and why only one of them counts

**The syntactic guard** rejects anything that is not a single SELECT. Easy to
read, easy to explain, easy to fool.

**The read only transaction** is the one that matters:

```python
conn.read_only = True
```

Postgres itself refuses the write, whatever the model asked for and however the
query was spelled.

> **Whether an agent meant well is a judgement. Whether it CAN write is a fact.**

Every rule you enforce only in a system prompt is a rule you are hoping about.

### The other three facts

**Code changes are limited to two directories.** An agent that can edit the
tests which judge it is not being judged.

**A proposed edit is parsed before a human is asked.** Whether a change is right
is a judgement; whether it compiles is a fact, and facts get checked first.

**A data change stops the graph.** `HumanInTheLoopMiddleware` pauses before the
tool runs at all, and the tool would not execute the statement even if it ran. A
person does that, by hand, having read it.

```python
middleware=[HumanInTheLoopMiddleware(interrupt_on={"request_db_change": True})]
```

Resuming takes a decision **and a reason**, and rejecting is a real outcome that
goes back to the agent. That is the difference between a human gate and a rubber
stamp.

### Why code changes do not pause

A pull request is already a human gate by construction. Pausing twice for the
same decision teaches people to click through, and a gate everybody clicks
through is worse than no gate, because it looks like control.

---

## The Confluence page

Composed **in code**, not by the model. The agent supplies eight strings; the
shape, ordering, macros and column widths are fixed.

Ask a model for Confluence storage format and you get a different page every
time, some of them broken. Assemble it yourself and every page in the space
looks the same, which is what makes a space navigable rather than a pile.

Structure, in order:

1. a summary table, as the page properties macro, so a parent page can roll them into a report
2. a provenance panel saying a machine wrote this and changed nothing
3. a table of contents
4. what happened, in two or three sentences of fact
5. **an architecture diagram** of where in the flow it breaks
6. evidence, as SQL and output in code blocks
7. what it means, in the owner's language
8. numbered steps
9. an ownership table, and a collapsed appendix

> A reader should be able to stop after the summary table and still know what to
> do. Everything below the fold is for the person who wants to check the work.

### The seam

`Publisher` is an interface with two implementations: markdown on disk, or the
Confluence REST API, chosen by whether the credentials are present. Swapping one
for the other **changes no agent code**, which is why this runs for a student
with no Atlassian account and for a team with one.

---

## Running it

```bash
uvicorn agent_service.worker:app --port 8092
```

| Endpoint | Does |
|---|---|
| `POST /breach` | the doorbell. Accepts and returns `202` at once |
| `POST /sweep` | picks up anything the doorbell missed |
| `GET /investigations` | what has been worked |
| `GET /investigations/{id}` | one investigation, with its artifacts |
| `POST /investigations/{id}/resume` | approve or reject a paused one |

**The doorbell returns immediately.** An investigation takes a minute or two, and
a scheduler that blocks for two minutes on one HTTP call has stopped being a
clock.

**The sweep exists because the doorbell is allowed to fail.** The breach is
durable before anybody is notified.

---

## Cost, roughly

One investigation is five agents and a dozen or so tool calls. On
`gpt-5.4-mini` that is cents, not dollars, and triage refusing to escalate is
what keeps it there.

Set `ONCALL_SUPERVISOR_MODEL` to something stronger than `ONCALL_MODEL` if you
want a better plan without paying for it five times.
