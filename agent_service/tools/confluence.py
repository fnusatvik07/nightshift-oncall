"""Writing a Confluence page somebody is glad to open.

Most machine written pages are a wall of text with a stack trace in it. This
module builds the thing a good engineer writes by hand, using the macros
Confluence actually renders, because the difference between a page that gets
read and one that gets closed is entirely presentation.

## What a good incident page has, in order

    1  a summary table          the facts, before any prose. Six rows, no more
    2  a status panel           severity and state, coloured, scannable
    3  a table of contents      so a long page can be skipped through
    4  what happened            two sentences. Not the investigation, the fact
    5  an architecture diagram  where in the flow it broke, drawn
    6  evidence                 the queries and their output, in code blocks
    7  what it means            consequence in business terms, not table names
    8  what to do               numbered steps somebody can follow
    9  an appendix              collapsed. Everything else the agent found

The rule behind all of it: **a reader should be able to stop after the summary
table and still know what to do.** Everything below the fold is for the person
who wants to check your work.

## Storage format

Confluence pages are XHTML with macros, not markdown. `<ac:structured-macro>`
is a macro, `<ac:parameter>` configures it, `<ac:rich-text-body>` holds nested
content and `<ac:plain-text-body>` holds a CDATA block. Tables get a
`<colgroup>` so columns have deliberate widths rather than whatever the browser
decides.
"""
from __future__ import annotations

import html
import os
import pathlib

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]

SITE = os.environ.get("ATLASSIAN_SITE", "").rstrip("/")
EMAIL = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN = os.environ.get("ATLASSIAN_TOKEN", "")
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE", "")
PARENT_TITLE = os.environ.get("CONFLUENCE_PARENT", "NIGHTSHIFT on call")

TIMEOUT = 45


def configured() -> bool:
    return bool(SITE and EMAIL and TOKEN and SPACE_KEY)


def _auth() -> tuple[str, str]:
    return (EMAIL, TOKEN)


def esc(text: str) -> str:
    return html.escape(str(text), quote=False)


# ═══════════════════════════════════════════════════════════════════════════
# The pieces a page is built from
# ═══════════════════════════════════════════════════════════════════════════

COLOURS = {"critical": "Red", "high": "Red", "medium": "Yellow",
           "low": "Grey", "open": "Yellow", "resolved": "Green",
           "proposed": "Blue", "awaiting_human": "Yellow"}


def status(text: str, colour: str | None = None) -> str:
    """A coloured lozenge. Use for severity and state, never for prose."""
    c = colour or COLOURS.get(str(text).lower(), "Grey")
    return (f'<ac:structured-macro ac:name="status">'
            f'<ac:parameter ac:name="colour">{c}</ac:parameter>'
            f'<ac:parameter ac:name="title">{esc(str(text).upper())}</ac:parameter>'
            f'</ac:structured-macro>')


def toc(max_level: int = 3) -> str:
    """The index at the top. A page longer than one screen without one is a
    page people scroll past rather than read."""
    return (f'<ac:structured-macro ac:name="toc">'
            f'<ac:parameter ac:name="maxLevel">{max_level}</ac:parameter>'
            f'<ac:parameter ac:name="minLevel">2</ac:parameter>'
            f'<ac:parameter ac:name="style">disc</ac:parameter>'
            f'</ac:structured-macro>')


def panel(kind: str, body_html: str) -> str:
    """info, note, warning, tip. One per page at most, or they stop meaning
    anything."""
    return (f'<ac:structured-macro ac:name="{kind}">'
            f'<ac:rich-text-body>{body_html}</ac:rich-text-body>'
            f'</ac:structured-macro>')


def code(text: str, language: str = "sql", title: str = "") -> str:
    """A code block. Always give it a language, so it is coloured."""
    t = (f'<ac:parameter ac:name="title">{esc(title)}</ac:parameter>' if title else "")
    return (f'<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{language}</ac:parameter>{t}'
            f'<ac:plain-text-body><![CDATA[{text}]]></ac:plain-text-body>'
            f'</ac:structured-macro>')


def expand(title: str, body_html: str) -> str:
    """Collapsed detail. Everything that is evidence rather than conclusion."""
    return (f'<ac:structured-macro ac:name="expand">'
            f'<ac:parameter ac:name="title">{esc(title)}</ac:parameter>'
            f'<ac:rich-text-body>{body_html}</ac:rich-text-body>'
            f'</ac:structured-macro>')


def details(rows: list[tuple[str, str]]) -> str:
    """The page properties macro: the summary table at the top.

    Confluence can roll these up into a Page Properties Report, so a folder of
    incidents becomes a table automatically. That is the reason to use this
    macro rather than an ordinary table for the summary.
    """
    body = table(rows, widths=(220, 620), header=False)
    return (f'<ac:structured-macro ac:name="details">'
            f'<ac:rich-text-body>{body}</ac:rich-text-body>'
            f'</ac:structured-macro>')


def table(rows: list[tuple], widths: tuple[int, ...] = (), header: bool = True) -> str:
    """A table with deliberate column widths.

    Without a colgroup, Confluence gives every column the same width and a
    two column table of labels and paragraphs looks broken.
    """
    if not rows:
        return ""
    n = len(rows[0])
    widths = widths or tuple([760 // n] * n)
    cols = "".join(f'<col style="width: {w}px;" />' for w in widths[:n])

    out = [f"<table data-layout=\"default\"><colgroup>{cols}</colgroup><tbody>"]
    for i, row in enumerate(rows):
        cells = []
        for j, cell in enumerate(row):
            body = cell if str(cell).startswith("<") else f"<p>{esc(cell)}</p>"
            if (header and i == 0) or (not header and j == 0):
                cells.append(f"<th>{body}</th>")
            else:
                cells.append(f"<td>{body}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def heading(text: str, level: int = 2) -> str:
    return f"<h{level}>{esc(text)}</h{level}>"


def para(text: str) -> str:
    """Plain prose. Blank lines become separate paragraphs."""
    return "".join(f"<p>{esc(b.strip())}</p>"
                   for b in str(text).split("\n\n") if b.strip())


def steps(items: list[str]) -> str:
    return "<ol>" + "".join(f"<li><p>{esc(i)}</p></li>" for i in items) + "</ol>"


def image(filename: str, width: int = 900, alt: str = "") -> str:
    """Embed an attachment on this page. Upload it first."""
    return (f'<ac:image ac:align="center" ac:width="{width}" ac:alt="{esc(alt)}">'
            f'<ri:attachment ri:filename="{esc(filename)}" /></ac:image>')


def link(url: str, text: str) -> str:
    return f'<a href="{esc(url)}">{esc(text)}</a>'


# ═══════════════════════════════════════════════════════════════════════════
# Talking to Confluence
# ═══════════════════════════════════════════════════════════════════════════

def _space_id() -> str | None:
    r = httpx.get(f"{SITE}/wiki/api/v2/spaces", auth=_auth(), timeout=TIMEOUT,
                  params={"keys": SPACE_KEY, "limit": 1})
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def _find_page(title: str, space_id: str) -> dict | None:
    r = httpx.get(f"{SITE}/wiki/api/v2/spaces/{space_id}/pages", auth=_auth(),
                  timeout=TIMEOUT, params={"title": title, "limit": 1})
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0] if results else None


def ensure_parent(space_id: str) -> str | None:
    """One parent page for every incident, so they do not litter the space.

    Created on first use, with a Page Properties Report on it, so the parent
    becomes an index of every incident without anybody maintaining one.
    """
    existing = _find_page(PARENT_TITLE, space_id)
    if existing:
        return existing["id"]

    body = (
        panel("info", "<p>Pages under here are written automatically by the "
                      "NIGHTSHIFT on call agent when a signal breaches. "
                      "Nothing in the warehouse is changed to produce them.</p>")
        + heading("Incidents", 2)
        + '<ac:structured-macro ac:name="detailssummary">'
          '<ac:parameter ac:name="cql">'
          f'label = "nightshift-incident" and space = "{esc(SPACE_KEY)}"'
          '</ac:parameter></ac:structured-macro>'
    )
    return create_page(PARENT_TITLE, body, space_id=space_id, parent_id=None,
                       labels=["nightshift"]).get("id")


def create_page(title: str, body_html: str, space_id: str | None = None,
                parent_id: str | None = "auto", labels: list[str] | None = None) -> dict:
    """Create a page. Returns {id, url} or {error}."""
    if not configured():
        return {"error": "Confluence is not configured. Set ATLASSIAN_SITE, "
                         "ATLASSIAN_EMAIL, ATLASSIAN_TOKEN and CONFLUENCE_SPACE."}
    try:
        space_id = space_id or _space_id()
        if not space_id:
            return {"error": f"no space with key {SPACE_KEY!r}"}

        if parent_id == "auto":
            parent_id = ensure_parent(space_id)

        payload = {
            "spaceId": space_id,
            "status": "current",
            "title": title[:255],
            "body": {"representation": "storage", "value": body_html},
        }
        if parent_id:
            payload["parentId"] = parent_id

        r = httpx.post(f"{SITE}/wiki/api/v2/pages", auth=_auth(), json=payload,
                       timeout=TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"{r.status_code}: {r.text[:300]}"}
        page = r.json()
        page_id = page["id"]

        for label in labels or []:
            httpx.post(f"{SITE}/wiki/rest/api/content/{page_id}/label", auth=_auth(),
                       json=[{"prefix": "global", "name": label}], timeout=TIMEOUT)

        return {"id": page_id,
                "url": f"{SITE}/wiki/spaces/{SPACE_KEY}/pages/{page_id}"}
    except Exception as e:                          # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def attach(page_id: str, path: pathlib.Path, comment: str = "") -> dict:
    """Attach a file to a page, so a diagram can be embedded in the body."""
    try:
        with open(path, "rb") as fh:
            r = httpx.put(
                f"{SITE}/wiki/rest/api/content/{page_id}/child/attachment",
                auth=_auth(), timeout=TIMEOUT,
                headers={"X-Atlassian-Token": "no-check"},
                files={"file": (path.name, fh, "image/png")},
                data={"comment": comment, "minorEdit": "true"})
        if r.status_code >= 400:
            return {"error": f"{r.status_code}: {r.text[:200]}"}
        return {"filename": path.name}
    except Exception as e:                          # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def update_body(page_id: str, title: str, body_html: str) -> dict:
    """Replace a page's body. Needed because a diagram can only be embedded
    after it has been attached, and it can only be attached after the page
    exists."""
    try:
        cur = httpx.get(f"{SITE}/wiki/api/v2/pages/{page_id}", auth=_auth(),
                        timeout=TIMEOUT).json()
        version = cur["version"]["number"] + 1
        r = httpx.put(f"{SITE}/wiki/api/v2/pages/{page_id}", auth=_auth(),
                      timeout=TIMEOUT,
                      json={"id": page_id, "status": "current", "title": title,
                            "body": {"representation": "storage", "value": body_html},
                            "version": {"number": version, "message": "diagram attached"}})
        if r.status_code >= 400:
            return {"error": f"{r.status_code}: {r.text[:200]}"}
        return {"id": page_id, "version": version}
    except Exception as e:                          # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
