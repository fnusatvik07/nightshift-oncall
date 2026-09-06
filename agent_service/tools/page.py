"""The tool that publishes an incident page.

One tool, one page, and the page is composed here rather than by the model. The
agent supplies the findings; the shape, the ordering, the macros and the widths
are decided in code.

That split matters. Ask a model to write XHTML with Confluence macros and you
get a different page every time, some of them broken. Ask it for eight strings
and assemble them yourself and every page in the space looks the same, which is
what makes a space navigable.
"""
from __future__ import annotations

import datetime as dt
import uuid

import psycopg
from langchain.tools import tool

from pipelines.lib.config import dsn

from . import confluence as cf
from . import diagram
from .publish import SCHEMA, setup


@tool
def publish_incident_page(
    breach_id: str,
    kpi: str,
    title: str,
    owner: str,
    severity: str,
    summary: str,
    what_happened: str,
    broken_at: str,
    what_breaks_there: str,
    evidence_queries: str,
    evidence_output: str,
    what_it_means: str,
    what_to_do: str,
    appendix: str = "",
    confidence: str = "medium",
) -> str:
    """Publish the incident page to Confluence, with a diagram, and return its URL.

    Compose the arguments carefully. They become the page a person reads at 3am.

    title              one line, specific. "Surge missing for release 4.2.0",
                       never "Data quality issue"
    summary            ONE sentence. It goes in the summary table, and a reader
                       who stops there must still know what to do
    what_happened      the number, its normal value, and when it moved. Two or
                       three sentences of fact, not investigation
    broken_at          the layer where the value stops being readable. Say the
                       pipeline or table name, for example
                       "the contract in p3_bronze_driver_app"
    what_breaks_there  one sentence for the diagram caption
    evidence_queries   the SQL you actually ran, newline separated
    evidence_output    what came back. Real numbers, not descriptions
    what_it_means      the business consequence, in the owner's language
    what_to_do         numbered steps, one per line, that somebody could follow
    appendix           anything else worth keeping. Collapsed on the page
    """
    setup()

    if not cf.configured():
        return ("Confluence is not configured, so nothing was published. "
                "Set ATLASSIAN_SITE, ATLASSIAN_EMAIL, ATLASSIAN_TOKEN and "
                "CONFLUENCE_SPACE, then try again. Use write_spec to keep a "
                "local page in the meantime.")

    page_ref = f"NS-{uuid.uuid4().hex[:6].upper()}"
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    full_title = f"{title[:150]}  [{breach_id}]"

    # ── 1 · the summary, before any prose ──────────────────────────────────
    summary_table = cf.details([
        ("Status", cf.status("open")),
        ("Severity", cf.status(severity)),
        ("Owner", f"<p>{cf.esc(owner)}</p>"),
        ("Signal", f"<p><code>{cf.esc(kpi)}</code></p>"),
        ("Breach", f"<p><code>{cf.esc(breach_id)}</code></p>"),
        ("Detected", f"<p>{now}</p>"),
        ("Confidence", f"<p>{cf.esc(confidence)}</p>"),
        ("In one sentence", f"<p><strong>{cf.esc(summary)}</strong></p>"),
    ])

    provenance = cf.panel("info",
        "<p><strong>This page was written by the NIGHTSHIFT on call agent.</strong> "
        "It was triggered by a signal breach, not by a person. Nothing in the "
        "warehouse was changed to produce it: every number below came from a "
        "read only query, and the queries are quoted so you can run them "
        "yourself. Any fix described here is a proposal waiting for a human.</p>")

    # ── 2 · the body ───────────────────────────────────────────────────────
    body = [summary_table, provenance, cf.heading("Contents", 2), cf.toc(3)]

    body += [cf.heading("What happened", 2), cf.para(what_happened)]

    body += [cf.heading("Where it breaks", 2)]
    diagram_placeholder = len(body)
    body += [cf.para(what_breaks_there)]

    body += [
        cf.heading("Evidence", 2),
        cf.para("Everything below was produced by a read only query against the "
                "warehouse. Run them yourself if you want to check."),
        cf.code(evidence_queries.strip() or "-- no queries recorded", "sql",
                "the queries that were run"),
        cf.code(evidence_output.strip() or "no output recorded", "text",
                "what came back"),
    ]

    body += [cf.heading("What it means", 2), cf.para(what_it_means)]

    todo = [line.strip(" .0123456789)-") for line in what_to_do.splitlines()
            if line.strip()]
    body += [cf.heading("What to do", 2), cf.steps(todo or [what_to_do])]

    body += [
        cf.heading("Who owns this", 2),
        cf.table([
            ("Question", "Answer"),
            ("Whose signal is it", owner),
            ("What does the signal watch", kpi),
            ("Where does the value break", broken_at),
            ("Has anything been changed", "No. This system proposes only."),
        ], widths=(260, 580)),
    ]

    if appendix.strip():
        body += [cf.heading("Appendix", 2),
                 cf.expand("Everything else the investigation found",
                           cf.para(appendix))]

    # ── 3 · create, attach, then embed ─────────────────────────────────────
    # The picture can only be embedded once it is attached, and it can only be
    # attached once the page exists. So: create, attach, update.
    created = cf.create_page(full_title, "".join(body),
                             labels=["nightshift-incident", kpi, owner])
    if "error" in created:
        return f"could not publish: {created['error']}"

    page_id, url = created["id"], created["url"]

    png = diagram.render(breach_id, kpi, title, broken_at, what_breaks_there)
    if png:
        attached = cf.attach(page_id, png, comment=f"incident flow for {breach_id}")
        if "filename" in attached:
            body.insert(diagram_placeholder,
                        cf.image(attached["filename"], 940, f"where {kpi} breaks"))
            cf.update_body(page_id, full_title, "".join(body))

    with psycopg.connect(dsn(), autocommit=True) as c:
        c.execute(f"""INSERT INTO {SCHEMA}.pages
                      (page_id, breach_id, title, owner, body, url)
                      VALUES (%s, %s, %s, %s, %s, %s)
                      ON CONFLICT (page_id) DO NOTHING""",
                  (page_ref, breach_id, title, owner, "".join(body), url))

    return (f"published to Confluence: {url}\n"
            f"diagram: {'attached' if png else 'not drawn, drawio unavailable'}")


CONFLUENCE_TOOLS = [publish_incident_page]
