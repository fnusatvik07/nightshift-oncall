"""A deliberately small diagram library, built for readability on a projector.

The earlier set overlapped because boxes were sized by hand and text was left to
find its own room. Here it is the other way round: a box is sized from the text
it has to hold, everything sits on a coarse grid, and arrows only ever run along
grid lines. Colour is used for meaning and nothing else.

    d = Page("title", "subtitle")
    a = d.box("kerb.trips", ["one row per ride"], col=0, row=0)
    b = d.box("bronze", ["landed untouched"], col=2, row=0)
    d.arrow(a, b, "copied")
    Deck("file", [d]).save()
"""
from __future__ import annotations
import pathlib, subprocess
import xml.sax.saxutils as sx

HERE = pathlib.Path(__file__).parent
PNG = HERE / "png"; PNG.mkdir(exist_ok=True)

INK, PAPER = "#111111", "#FFFFFF"
GREY, RULE, MUTED = "#F4F4F5", "#D4D4D8", "#6B7280"
BLUE, GREEN, RED, AMBER = "#1D4ED8", "#047857", "#B91C1C", "#B45309"
BLUE_BG, GREEN_BG, RED_BG, AMBER_BG = "#EFF4FF", "#ECFDF5", "#FEF2F2", "#FFFBEB"
F = "Helvetica"

# one coarse grid, so nothing can drift a few pixels out of line
COL, ROW, PAD = 470, 320, 90
BAND_H = 84
TITLE_H = 150


def esc(s: str) -> str:
    return sx.escape(s, {'"': "&quot;", "'": "&apos;"})


def _height(lines: list, w: int, size: int = 19) -> int:
    """Enough room for the text and no more, so the words fill the box."""
    per = max(1, int((w - 44) / (size * 0.52)))
    n = sum(max(1, -(-len(l) // per)) for l in lines)
    return 34 + 40 + n * int(size * 1.5) + 22


class Page:
    def __init__(self, name, title, subtitle="", cols=5, rows=4, row_h=ROW):
        self.name, self.title, self.subtitle = name, title, subtitle
        self.row_h = row_h
        self.w = PAD * 2 + cols * COL
        self.h = TITLE_H + rows * row_h + PAD
        self.c, self.n = [], 1
        # rows that carry a band need their boxes pushed below it, otherwise the
        # band and the boxes are handed the same y and draw on top of each other
        self.bands = set()
        self._text(title, PAD, 44, self.w - PAD * 2, 46, 34, INK, bold=True)
        if subtitle:
            self._text(subtitle, PAD, 96, self.w - PAD * 2, 34, 21, MUTED)

    def _id(self):
        self.n += 1
        return f"n{self.n}"

    def _add(self, style, label, x, y, w, h):
        i = self._id()
        self.c.append(f'<mxCell id="{i}" value="{esc(label)}" style="{style}" vertex="1" '
                      f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
                      f'as="geometry"/></mxCell>')
        return dict(id=i, x=x, y=y, w=w, h=h)

    def _text(self, body, x, y, w, h, size, colour, bold=False, align="left"):
        s = (f"text;html=1;strokeColor=none;fillColor=none;align={align};verticalAlign=top;"
             f"whiteSpace=wrap;fontFamily={F};fontSize={size};fontColor={colour};"
             f"{'fontStyle=1;' if bold else ''}")
        return self._add(s, body, x, y, w, h)

    def at(self, col, row, span=1):
        y = TITLE_H + row * self.row_h + (BAND_H if row in self.bands else 0)
        return PAD + col * COL, y, span * COL - 60

    # ── the only shape, in four flavours ────────────────────────────────────
    def box(self, title, lines, col, row, span=1, kind="plain", size=19):
        x, y, w = self.at(col, row, span)
        stroke, fill, tcol = {
            "plain":  (INK,   PAPER,    INK),
            "ours":   (BLUE,  BLUE_BG,  BLUE),
            "good":   (GREEN, GREEN_BG, GREEN),
            "bad":    (RED,   RED_BG,   RED),
            "gate":   (AMBER, AMBER_BG, AMBER),
            "quiet":  (RULE,  GREY,     MUTED),
        }[kind]
        h = _height(lines, w, size)
        body = "".join(f"<div style='margin-top:9px'>{l}</div>" for l in lines)
        label = (f"<div style='font-size:24px;font-weight:600;color:{tcol}'>{title}</div>"
                 f"<div style='font-size:{size}px;color:{INK};line-height:1.45'>{body}</div>")
        s = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
             f"strokeWidth=2;fontFamily={F};align=left;verticalAlign=top;spacing=20;")
        return self._add(s, label, x, y, w, h)

    def stack(self, title, items, col, row, span=1, kind="plain", note=""):
        """A named group holding a list of real component names.

        A technical architecture has to name everything, and naming everything
        in prose sprawls. One box, one list, one line per component.
        """
        x, y, w = self.at(col, row, span)
        stroke, fill, tcol = {
            "plain": (INK, PAPER, INK), "ours": (BLUE, BLUE_BG, BLUE),
            "good": (GREEN, GREEN_BG, GREEN), "bad": (RED, RED_BG, RED),
            "gate": (AMBER, AMBER_BG, AMBER), "quiet": (RULE, GREY, MUTED),
        }[kind]
        h = 34 + 40 + len(items) * 30 + (34 if note else 0) + 20
        rows = "".join(f"<div style=\'font-family:Courier New;font-size:17px;"
                       f"margin-top:7px\'>{i}</div>" for i in items)
        tail = (f"<div style=\'font-size:16px;color:{MUTED};margin-top:12px\'>{note}</div>"
                if note else "")
        label = (f"<div style=\'font-size:22px;font-weight:600;color:{tcol}\'>{title}</div>"
                 f"{rows}{tail}")
        st = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
              f"strokeWidth=2;fontFamily={F};align=left;verticalAlign=top;spacing=18;")
        return self._add(st, label, x, y, w, h)

    def band(self, text, row, kind="plain", span=None):
        self.bands.add(row)
        x = PAD
        w = self.w - PAD * 2
        y = TITLE_H + row * self.row_h
        fill, tcol = {"plain": (INK, PAPER), "ours": (BLUE, PAPER),
                      "good": (GREEN, PAPER), "bad": (RED, PAPER),
                      "quiet": (GREY, MUTED)}[kind]
        s = (f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor=none;"
             f"fontFamily={F};fontSize=20;fontColor={tcol};fontStyle=1;align=left;spacing=22;")
        return self._add(s, text, x, y, w, 56)

    def code(self, lines, col, row, span=2):
        x, y, w = self.at(col, row, span)
        body = "<br>".join(l.replace(" ", "&nbsp;") for l in lines)
        h = 40 + len(lines) * 30
        s = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=#0F172A;strokeColor=#0F172A;"
             f"fontFamily=Courier New;fontSize=18;fontColor=#E2E8F0;align=left;"
             f"verticalAlign=top;spacing=18;")
        return self._add(s, body, x, y, w, h)

    def note(self, text, col, row, span=2, size=20):
        x, y, w = self.at(col, row, span)
        h = _height([text], w, size) - 34
        s = (f"rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=none;"
             f"fontFamily={F};fontSize={size};fontColor={INK};align=left;verticalAlign=top;")
        return self._add(s, text, x, y, w, h)

    def arrow(self, a, b, label="", colour=INK, dashed=False, down=False):
        i = self._id()
        s = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor={colour};strokeWidth=2.5;"
             f"endArrow=blockThin;endFill=1;endSize=7;fontFamily={F};fontSize=17;"
             f"fontColor={colour};labelBackgroundColor={PAPER};spacing=8;")
        if dashed:
            s += "dashed=1;dashPattern=8 6;"
        s += ("exitX=0.5;exitY=1;entryX=0.5;entryY=0;" if down
              else "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
        self.c.append(f'<mxCell id="{i}" value="{esc(label)}" style="{s}" edge="1" parent="1" '
                      f'source="{a["id"]}" target="{b["id"]}">'
                      f'<mxGeometry relative="1" as="geometry"/></mxCell>')

    def xml(self):
        return (f'<diagram name="{esc(self.name)}">'
                f'<mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1" '
                f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
                f'pageWidth="{self.w}" pageHeight="{self.h}" math="0" shadow="0" background="{PAPER}">'
                f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{"".join(self.c)}</root>'
                f'</mxGraphModel></diagram>')


class Deck:
    def __init__(self, filename, pages):
        self.filename, self.pages = filename, pages

    def save(self):
        body = "".join(p.xml() for p in self.pages)
        p = HERE / f"{self.filename}.drawio"
        p.write_text(f'<mxfile host="app" agent="nightshift">{body}</mxfile>')
        return p


def export_pages(path, names):
    for i, n in enumerate(names):
        out = PNG / f"{path.stem}-{i+1}-{n}.png"
        subprocess.run(["drawio", "-x", "-f", "png", "-s", "2", "--no-sandbox", "-b", "30",
                        "-p", str(i + 1), "-o", str(out), str(path)],
                       capture_output=True, timeout=300)
        print(f"  {out.name}", "ok" if out.exists() else "FAILED")
