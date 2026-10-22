"""Shared look of the talk decks: colors, fonts, shapes and the slide frames.

A deck script (presentation/build_<part>.py) builds its slides with these helpers, so all
parts look the same and a style change is made once. Run deck scripts from the repo root
with PYTHONPATH=. so `presentation.slides` imports.
"""

import datetime
import io
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

FIXED_TIME = datetime.datetime(2026, 1, 1)

FONT = "Malgun Gothic"  # 맑은 고딕: Korean font that ships with Office on Windows
MONO = "Consolas"

INK = "1F2A30"  # dark slate: title/closing background, body text
TEAL = "2E6F73"  # steel teal: structure, "done"
ORANGE = "E8743B"  # cutting-torch orange: model stages, highlights
GRAY = "5F6B73"
LIGHT = "EEF3F4"  # card tint
TEAL_TINT = "DCEBEC"
ORANGE_TINT = "FBE7DC"
WHITE = "FFFFFF"
CODE_BG = "263238"
CODE_FG = "E6EDF0"

W, H = 13.333, 7.5
X0, CW = 0.6, 12.133  # content left edge and width


# ---------------------------------------------------------------------- primitives
def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def style_run(run, size, color, bold=False, font=FONT, italic=False):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = rgb(color)
    f.name = font
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):  # Korean glyphs use the East Asian font, not latin
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", font)


def set_bullet(paragraph, color):
    ppr = paragraph._p.get_or_add_pPr()
    ppr.set("marL", str(Inches(0.28)))
    ppr.set("indent", str(-Inches(0.22)))
    clr = ppr.makeelement(qn("a:buClr"), {})
    srgb = clr.makeelement(qn("a:srgbClr"), {"val": color})
    clr.append(srgb)
    ppr.append(clr)
    ppr.append(ppr.makeelement(qn("a:buChar"), {"char": "•"}))


def write(
    tf,
    paras,
    *,
    size=16,
    color=INK,
    bold=False,
    font=FONT,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    after=6,
    margin=0.0,
):
    """paras: list of paragraphs; a paragraph is a str, a run dict, or a list of runs.
    A dict paragraph may set bullet=True and its own size/color/bold/font/italic."""
    tf.word_wrap = True
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(after)
        runs = para if isinstance(para, list) else [para]
        bullet = False
        for r in runs:
            r = {"text": r} if isinstance(r, str) else r
            bullet = bullet or r.get("bullet", False)
            run = p.add_run()
            run.text = r["text"]
            style_run(
                run,
                r.get("size", size),
                r.get("color", color),
                r.get("bold", bold),
                r.get("font", font),
                r.get("italic", False),
            )
        if bullet:
            set_bullet(p, ORANGE)
    return tf


def text(slide, x, y, w, h, paras, **kw):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    write(box.text_frame, paras, **kw)
    return box


def shape(slide, kind, x, y, w, h, fill, *, line=None, radius=0.06):
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.shadow.inherit = False
    return s


def card(slide, x, y, w, h, paras, *, fill=LIGHT, margin=0.18, **kw):
    s = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill)
    write(s.text_frame, paras, margin=margin, **kw)
    return s


def circle(slide, x, y, d, label, fill=ORANGE, color=WHITE, size=16):
    s = shape(slide, MSO_SHAPE.OVAL, x, y, d, d, fill)
    write(
        s.text_frame,
        [{"text": label, "bold": True}],
        size=size,
        color=color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    return s


def arrow(slide, x, y, w=0.3, h=0.32, fill=ORANGE, kind=MSO_SHAPE.RIGHT_ARROW):
    return shape(slide, kind, x, y, w, h, fill)


def code(slide, x, y, w, h, lines, size=11):
    s = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, CODE_BG, radius=0.03)
    write(
        s.text_frame,
        [{"text": line} for line in lines],
        size=size,
        color=CODE_FG,
        font=MONO,
        after=2,
        margin=0.2,
    )
    return s


def chip(slide, x, y, w, h, label, *, fill=LIGHT, color=INK, size=13, bold=False):
    s = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill, radius=0.15)
    write(
        s.text_frame,
        [{"text": label, "bold": bold}],
        size=size,
        color=color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=0,
        margin=0.05,
    )
    return s


# ---------------------------------------------------------------------- slide frames
class Deck:
    def __init__(self, out: Path, title: str, footer: str):
        self.out, self.title, self.footer = out, title, footer
        self.prs = Presentation()
        self.prs.slide_width = Inches(W)
        self.prs.slide_height = Inches(H)
        self.blank = self.prs.slide_layouts[6]
        self.count = 0

    def slide(self, notes, *, dark=False):
        s = self.prs.slides.add_slide(self.blank)
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = rgb(INK if dark else WHITE)
        s.notes_slide.notes_text_frame.text = notes
        self.count += 1
        return s

    def content(self, title, message, notes):
        """A light slide with the title, a one-line message under it and the footer."""
        s = self.slide(notes)
        text(s, X0, 0.45, CW, 0.75, [title], size=34, bold=True, anchor=MSO_ANCHOR.TOP)
        text(s, X0, 1.15, CW, 0.45, [message], size=17, color=GRAY)
        text(s, X0, 6.95, 9.0, 0.3, [self.footer], size=10, color=GRAY)
        text(
            s,
            W - X0 - 1.0,
            6.95,
            1.0,
            0.3,
            [str(self.count)],
            size=10,
            color=GRAY,
            align=PP_ALIGN.RIGHT,
        )
        return s

    def save(self):
        props = self.prs.core_properties
        props.title = self.title
        props.author = "PBL cutplan_agent"
        props.created = props.modified = FIXED_TIME
        props.revision = 1
        buffer = io.BytesIO()
        self.prs.save(buffer)
        reproducible(buffer.getvalue(), self.out)
        return self.out


def reproducible(data: bytes, path: Path) -> None:
    """Rewrite the zip with fixed entry times, so the same slides give the same bytes and
    a rebuild without changes leaves git clean."""
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                entry = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(entry, src.read(info.filename))


# ---------------------------------------------------------------------- charts and pictures
def plain_chart(chart):
    """No title and no frame around the chart area."""
    chart.has_title = False
    space = chart._chartSpace
    sp_pr = space.find(qn("c:spPr"))
    if sp_pr is None:
        sp_pr = space.makeelement(qn("c:spPr"), {})
        space.find(qn("c:chart")).addnext(sp_pr)
    sp_pr.append(sp_pr.makeelement(qn("a:noFill"), {}))
    line = sp_pr.makeelement(qn("a:ln"), {})
    line.append(line.makeelement(qn("a:noFill"), {}))
    sp_pr.append(line)


def bar_chart(
    slide,
    x,
    y,
    w,
    h,
    categories,
    values,
    colors,
    *,
    number_format="0",
    horizontal=True,
    label_size=14,
    gap=60,
):
    """One-series bar chart with a value label on each bar and no axis numbers or grid."""
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION

    data = CategoryChartData()
    data.categories = categories
    data.add_series("values", values)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    chart = slide.shapes.add_chart(
        kind, Inches(x), Inches(y), Inches(w), Inches(h), data
    ).chart
    plain_chart(chart)
    chart.has_legend = False
    chart.font.size = Pt(label_size)
    chart.font.name = FONT
    chart.font.color.rgb = rgb(INK)
    plot = chart.plots[0]
    plot.gap_width = gap
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = number_format
    labels.number_format_is_linked = False
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    labels.font.size = Pt(label_size)
    labels.font.bold = True
    for point, color in zip(plot.series[0].points, colors):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = rgb(color)
    value_axis = chart.value_axis
    value_axis.visible = False
    value_axis.has_major_gridlines = False
    value_axis.minimum_scale = 0
    category_axis = chart.category_axis
    category_axis.format.line.fill.background()
    category_axis.tick_labels.font.size = Pt(label_size)
    if horizontal:
        category_axis.reverse_order = True  # first category on top
    return chart


def doughnut_chart(slide, x, y, w, h, categories, values, colors, *, hole=58):
    """Doughnut with value labels and a legend on the right."""
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

    data = CategoryChartData()
    data.categories = categories
    data.add_series("values", values)
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.DOUGHNUT, Inches(x), Inches(y), Inches(w), Inches(h), data
    ).chart
    plain_chart(chart)
    chart.font.size = Pt(14)
    chart.font.name = FONT
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.RIGHT
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(15)
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(14)
    plot.data_labels.font.bold = True
    plot.data_labels.font.color.rgb = rgb(WHITE)
    plot.data_labels.number_format = "0"
    plot.data_labels.number_format_is_linked = False
    for point, color in zip(plot.series[0].points, colors):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = rgb(color)
    hole_size = plot._element.find(qn("c:holeSize"))
    if hole_size is None:
        hole_size = plot._element.makeelement(qn("c:holeSize"), {})
        plot._element.append(hole_size)
    hole_size.set("val", str(hole))
    return chart


def picture(slide, path, x, y, w=None, h=None):
    """A picture, or a gray box naming the missing file so the deck still builds."""
    if Path(path).is_file():
        return slide.shapes.add_picture(
            str(path),
            Inches(x),
            Inches(y),
            Inches(w) if w else None,
            Inches(h) if h else None,
        )
    return card(
        slide,
        x,
        y,
        w or 4,
        h or 3,
        [f"그림 없음: {path}"],
        size=12,
        color=GRAY,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def badge(slide, x, y, d, glyph, fill, color=WHITE, size=None):
    """A round marker with one symbol or number in it."""
    return circle(
        slide, x, y, d, glyph, fill=fill, color=color, size=size or int(d * 30)
    )
