"""Build presentation/dwg_dxf.pptx: why the project turns DWG into DXF, for listeners who
know little about AI or programming.

PYTHONPATH=. uv run --with python-pptx python presentation/build_dwg_dxf.py

The story: AI reads text and pictures, not binary files; a DWG opened in a text editor is
noise, a DXF is text; but a real drawing's DXF is far too long for the AI; a program reads
it in a tenth of a second; so the program reads and calculates and the AI judges, and DXF is
what lets them work together. Few words on the slides, the narration is in the notes.

Pictures are drawn at build time from data_v3/synthetic/cone_0019/cone_0019.dxf (a gray box
when it is missing). Where every number comes from: docs/presentation.md 4절. Customer
drawings appear only as counts, sizes and timings.
"""

from pathlib import Path

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from presentation.slides import (
    CODE_BG,
    CODE_FG,
    CW,
    GRAY,
    INK,
    LIGHT,
    MONO,
    ORANGE,
    ORANGE_TINT,
    TEAL,
    TEAL_TINT,
    WHITE,
    X0,
    Deck,
    arrow,
    badge,
    chip,
    circle,
    doughnut_chart,
    picture,
    shape,
    text,
    write,
)

OUT = Path(__file__).with_name("dwg_dxf.pptx")
TITLE = "AI 는 도면을 어떻게 읽을까: DWG 를 DXF 로 바꾸는 이유"
FOOTER = "PBL cutplan_agent · DWG 와 DXF · 2026-10-24"
CONE_DXF = Path("data_v3/synthetic/cone_0019/cone_0019.dxf")
ASSETS = Path(__file__).with_name("build") / "assets"
CONE_PNG = ASSETS / "cone_0019.png"
FLAT_PNG = ASSETS / "cone_0019_flat.png"
FRAME = (20.0, 20.0, 820.0, 574.0)  # cone_0019 drawing frame in DXF units
# The cone_0019 flat pattern from the reader run of 2026-10-23 (stage 10 develop)
FLAT = {"outer": 405.65, "inner": 252.87, "angle": 68.33}
CHECK, CROSS = "✓", "✕"

# cone_0019.dxf saved as DWG with LibreDWG 0.14 dxf2dwg (6,346 bytes) and shown the way a
# text editor shows it: bytes as Latin-1, control characters as □. Bytes 0-169 and
# 3000-3169. Only 23% of the file's bytes are printable ASCII.
DWG_AS_TEXT = [
    "AC1015□□□□□□□Ü□□□□□□□□□□□□a□□□L□□□",
    "□□□□□&□□□□□□□□Ô□□□□□□□□□□□□□S□□□□□",
    "□□□W□□□s□□□b.□□N(□□□å^Aà_□:M□Ï{□#ý",
    "Þ8□_|h□Nm3_&□□□□□F%□□□□□□□□□A$Ê□□□",
    "□□□□□□□□□ú□□□□□Å□□□□□□□□□□□□□□□□□□",
    "□□□□□□□□□□□□□□□□□□□□□@*□f□□□%□G□)□",
    "DÆÀ@□□Qç4!Ø□□□□□□ê□□□□□□□□□□□□□□@*",
    "□f□□□%□□>1□DÖÀ@□□R'4!Þnfffgc□□ffff",
    "f&è□ffffff□□ææffff*□f□□□%□W□1□DÖÀ@",
]


# ---------------------------------------------------------------------- pictures
def render_cone() -> Path:
    """Draw cone_0019.dxf with the axes fixed to its frame."""
    if not CONE_DXF.is_file():
        return CONE_PNG
    import ezdxf
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import (
        BackgroundPolicy,
        ColorPolicy,
        Configuration,
    )
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.readfile(CONE_DXF)
    x0, y0, x1, y1 = FRAME
    fig = plt.figure(figsize=((x1 - x0) / 100, (y1 - y0) / 100))
    ax = fig.add_axes((0, 0, 1, 1))
    config = Configuration(
        background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK
    )
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=config).draw_layout(
        doc.modelspace(), finalize=True
    )
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(CONE_PNG, dpi=200, facecolor="white")
    plt.close(fig)
    return CONE_PNG


def render_flat() -> Path:
    """The cone's flat pattern: an annular sector with the radii and angle of FLAT."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge

    r1, r2, angle = FLAT["outer"], FLAT["inner"], FLAT["angle"]
    fig = plt.figure(figsize=(4, 3))
    ax = fig.add_axes((0, 0, 1, 1))
    wedge = Wedge(
        (0, 0),
        r1,
        90 - angle / 2,
        90 + angle / 2,
        width=r1 - r2,
        facecolor="#FBE7DC",
        edgecolor="#E8743B",
        linewidth=2,
    )
    ax.add_patch(wedge)
    ax.set_xlim(-r1 * 0.62, r1 * 0.62)
    ax.set_ylim(r2 * 0.75, r1 * 1.04)
    ax.set_aspect("equal")
    ax.axis("off")
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FLAT_PNG, dpi=200, facecolor="white")
    plt.close(fig)
    return FLAT_PNG


# ---------------------------------------------------------------------- local shapes
def editor(s, x, y, w, h, title, lines, *, color=CODE_FG, size=15):
    """A text-editor window: a title bar and the file's text."""
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, CODE_BG, radius=0.03)
    shape(s, MSO_SHAPE.RECTANGLE, x, y + 0.45, w, 0.02, "3A4A52")
    for i, dot in enumerate(("E8743B", "C9A23B", "5FA36B")):
        shape(s, MSO_SHAPE.OVAL, x + 0.2 + i * 0.25, y + 0.15, 0.15, 0.15, dot)
    text(s, x + 1.0, y + 0.07, w - 1.2, 0.35, [title], size=13, color="B8C4C9")
    box = s.shapes.add_textbox(
        *(int(v * 914400) for v in (x + 0.3, y + 0.6, w - 0.6, h - 0.75))
    )
    write(
        box.text_frame,
        [{"text": line} for line in lines],
        size=size,
        color=color,
        font=MONO,
        after=0,
    )


def page(s, x, y, w, h, fill=WHITE, line=GRAY):
    """A sheet of paper (folded corner)."""
    return shape(s, MSO_SHAPE.FOLDED_CORNER, x, y, w, h, fill, line=line)


def verdict(s, x, y, w, glyph, color, head, sub=None):
    """A round check or cross with a short line next to it."""
    badge(s, x, y, 0.75, glyph, color, size=26)
    paras = [{"text": head, "bold": True, "size": 18}]
    if sub:
        paras.append({"text": sub, "size": 14, "color": GRAY})
    text(
        s, x + 0.95, y - 0.05, w - 0.95, 0.85, paras, anchor=MSO_ANCHOR.MIDDLE, after=2
    )


# ---------------------------------------------------------------------- slides
def title_slide(d: Deck):
    s = d.slide(
        "이번 파트의 질문은 하나입니다. 회사에서 받는 도면은 DWG 라는 파일인데, 우리는 왜 굳이 이걸 "
        "DXF 라는 파일로 바꿔서 쓰는가. 답을 따라가다 보면 AI 가 무엇을 잘하고 무엇을 못하는지, 그리고 "
        "평범한 프로그램과 AI 가 어떻게 손을 잡는지가 보입니다.",
        dark=True,
    )
    text(
        s,
        X0,
        2.2,
        CW,
        1.6,
        ["AI 는 도면을", "어떻게 읽을까"],
        size=44,
        bold=True,
        color=WHITE,
        after=4,
    )
    text(
        s,
        X0,
        4.1,
        CW,
        0.5,
        ["DWG 를 DXF 로 바꾸는 이유: 프로그램과 AI 의 분업"],
        size=20,
        color=ORANGE,
    )
    text(
        s, X0, 6.4, CW, 0.4, ["PBL cutplan_agent · 2026-10-24"], size=14, color="B8C4C9"
    )


def ai_reads_slide(d: Deck):
    s = d.content(
        "AI 는 무엇을 읽을 수 있나",
        "사람이 쓴 글자와 그림으로 배웠다. 0 과 1 로 된 파일은 못 읽는다",
        "먼저 AI 가 무엇을 읽는지부터 보겠습니다. 요즘 AI, 정확히는 언어 모델은 사람이 쓴 엄청난 양의 "
        "글자로 배웠고, 최근 모델은 그림도 함께 배웠습니다. 그래서 글자나 그림을 주면 읽고 글자로 "
        "답합니다. 그런데 컴퓨터 파일 중에는 사람이 읽으라고 만든 게 아니라 프로그램끼리 쓰라고 0 과 "
        "1 로 꽉 채운 파일이 있습니다. 이걸 바이너리 파일이라고 하는데, AI 는 이런 걸 배운 적이 없어서 "
        "읽지 못합니다. 그리고 DWG 가 바로 이런 파일입니다.",
    )
    inputs = [
        ("글자", '"이 도면의 재질은?"', TEAL_TINT, CHECK, TEAL),
        ("그림", "도면 사진 · 스캔", TEAL_TINT, CHECK, TEAL),
        ("0 과 1 의 파일", "바이너리 (DWG 등)", LIGHT, CROSS, GRAY),
    ]
    for i, (head, sub, fill, glyph, color) in enumerate(inputs):
        y = 1.95 + i * 1.5
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, X0, y, 3.9, 1.15, fill)
        text(
            s,
            X0 + 0.3,
            y,
            3.4,
            1.15,
            [
                {"text": head, "bold": True, "size": 20},
                {"text": sub, "size": 14, "color": GRAY},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
        arrow(s, X0 + 4.1, y + 0.4, 1.0, 0.36, fill=ORANGE if i < 2 else "C9D3D6")
        badge(s, X0 + 5.25, y + 0.2, 0.75, glyph, color, size=26)
    circle(s, X0 + 6.5, 2.75, 2.2, "AI", fill=INK, size=48)
    arrow(s, X0 + 8.9, 3.65, 0.9, 0.4)
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, X0 + 9.95, 3.1, CW - 9.95, 1.5, ORANGE_TINT)
    text(
        s,
        X0 + 10.1,
        3.1,
        CW - 10.25,
        1.5,
        [
            {"text": "글자로 답한다", "bold": True, "size": 17},
            {"text": '"재질은 SPCC 입니다"', "size": 15, "color": GRAY},
        ],
        anchor=MSO_ANCHOR.MIDDLE,
        after=2,
    )


def notepad_slide(d: Deck):
    s = d.content(
        "같은 도면을 메모장으로 열면",
        "DWG 는 기호 덩어리, DXF 는 글자",
        "실제로 같은 도면을 두 형식으로 저장해서 메모장으로 열어 봤습니다. 원뿔 도면 하나입니다. "
        "왼쪽 DWG 는 보시다시피 알 수 없는 기호뿐입니다. 사람이 읽을 수 있는 글자는 23% 이고 그마저 "
        "의미가 없습니다. 사람도 못 읽고 AI 도 못 읽습니다. 오른쪽 DXF 는 다릅니다. LINE, 즉 선이 "
        "하나 있고, 시작점이 100, 86 이고 끝점이 250, 86 이라고 글자로 적혀 있습니다. DXF 는 도면을 "
        "글자로 적은 파일입니다. 그럼 AI 에게 DXF 를 주면 되지 않을까요?",
    )
    w = (CW - 0.4) / 2
    editor(s, X0, 1.85, w, 3.75, "cone_0019.dwg — 메모장", DWG_AS_TEXT, size=15)
    editor(
        s,
        X0 + w + 0.4,
        1.85,
        w,
        3.75,
        "cone_0019.dxf — 메모장",
        [
            "LINE      ← 선",
            "8",
            "DIM",
            "10        ← 시작점 x",
            "100.0",
            "20        ← 시작점 y",
            "86.0",
            "11        ← 끝점 x",
            "250.0",
        ],
        size=15,
    )
    verdict(s, X0, 5.85, w, CROSS, GRAY, "사람도 AI 도 못 읽는다", "읽히는 글자 23%")
    verdict(
        s,
        X0 + w + 0.4,
        5.85,
        w,
        CHECK,
        TEAL,
        "글자로 읽힌다",
        "선 하나: (100, 86) → (250, 86)",
    )


def too_long_slide(d: Deck):
    s = d.content(
        "그런데 너무 길다",
        "AI 가 한 번에 읽는 양은 약 50쪽. 실제 도면 한 장의 DXF 는 약 2,500쪽",
        "그런데 문제가 있습니다. DXF 는 글자이긴 한데 너무 깁니다. 회사 도면 한 장을 DXF 로 바꾸면 "
        "12만 줄이 넘습니다. 한 쪽에 50줄씩 인쇄하면 2,500쪽, 책 몇 권 분량입니다. 반면 지금 쓰는 AI 가 "
        "한 번에 읽고 기억할 수 있는 양은 이 DXF 로 치면 50쪽 정도입니다. 50배가 넘게 모자랍니다. "
        "모델이 낼 수 있는 최대치로 늘려도 800쪽이 안 됩니다. 그래서 AI 에게 DXF 를 통째로 주는 방법은 "
        "안 됩니다.",
    )
    # AI: one page
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, X0, 1.85, 3.6, 4.75, ORANGE_TINT)
    page(s, X0 + 1.15, 2.2, 1.3, 1.65)
    text(
        s,
        X0,
        4.05,
        3.6,
        0.8,
        ["약 50쪽"],
        size=34,
        bold=True,
        color=ORANGE,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        X0,
        4.9,
        3.6,
        1.0,
        [
            {"text": "AI 가 한 번에 읽는 양", "bold": True, "size": 16},
            {"text": "16,384 토큰", "size": 13, "color": GRAY},
        ],
        align=PP_ALIGN.CENTER,
        after=2,
    )
    text(
        s,
        X0 + 3.65,
        3.5,
        0.9,
        0.8,
        ["×50"],
        size=26,
        bold=True,
        color=INK,
        align=PP_ALIGN.CENTER,
    )
    # DXF: 50 pages of 50 pages each
    x0 = X0 + 4.6
    w = CW - 4.6
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x0, 1.85, w, 4.75, LIGHT)
    cols, rows = 10, 5
    pw, ph, gx, gy = 0.5, 0.58, 0.18, 0.12
    left = x0 + (w - (cols * pw + (cols - 1) * gx)) / 2
    for r in range(rows):
        for c in range(cols):
            page(s, left + c * (pw + gx), 2.1 + r * (ph + gy), pw, ph, line="9AA6AC")
    text(
        s,
        x0,
        5.65,
        w * 0.5,
        0.8,
        ["약 2,500쪽"],
        size=30,
        bold=True,
        color=INK,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        x0 + w * 0.5,
        5.65,
        w * 0.5,
        0.8,
        [
            {"text": "실제 도면 한 장의 DXF", "bold": True, "size": 16},
            {"text": "12만 줄 · 아이콘 1개 = 50쪽", "size": 13, "color": GRAY},
        ],
        anchor=MSO_ANCHOR.MIDDLE,
        after=2,
    )


def program_slide(d: Deck):
    s = d.content(
        "프로그램은 이걸 0.1초에 읽는다",
        "평범한 프로그램은 긴 파일을 빠르고 정확하게 처리한다",
        "그럼 이 2,500쪽은 누가 읽을까요. 평범한 프로그램입니다. 도면 파일을 읽는 공개 프로그램 "
        "라이브러리로 같은 12만 줄짜리 DXF 를 읽게 했더니 0.1초 남짓 걸렸습니다. 그 사이에 선이 1,243개, "
        "글자가 330개라는 걸 하나도 틀리지 않고 셌습니다. 지치지도 않고 실수도 없습니다. 그런데 "
        "프로그램은 '이 선들이 모여서 원뿔이구나' 같은 판단은 못 합니다. 정해 준 일만 정확히 할 뿐입니다.",
    )
    stats = [("0.1초", "12만 줄을 읽는 시간"), ("1,243", "선"), ("330", "글자")]
    w = (CW - 2 * 0.3) / 3
    for i, (value, label) in enumerate(stats):
        x = X0 + i * (w + 0.3)
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.9, w, 2.4, TEAL_TINT)
        text(
            s,
            x,
            2.2,
            w,
            1.1,
            [value],
            size=54,
            bold=True,
            color=TEAL,
            align=PP_ALIGN.CENTER,
        )
        text(s, x, 3.4, w, 0.6, [label], size=17, color=GRAY, align=PP_ALIGN.CENTER)
    half = (CW - 0.4) / 2
    verdict(
        s,
        X0 + 0.3,
        4.95,
        half,
        CHECK,
        TEAL,
        "빠르고 정확하다",
        "지치지 않고, 틀리지 않는다",
    )
    verdict(
        s,
        X0 + half + 0.7,
        4.95,
        half,
        "?",
        ORANGE,
        "'이게 원뿔이다' 는 모른다",
        "정해 준 일만 한다",
    )
    text(
        s,
        X0,
        6.25,
        CW,
        0.4,
        ["실제 입력 도면 한 장의 DXF (1.1 MB) 를 ezdxf 로 읽은 결과 (2026-10-23)"],
        size=12,
        color=GRAY,
    )


def strengths_slide(d: Deck):
    s = d.content(
        "잘하는 것이 다르다",
        "프로그램은 읽기와 계산, AI 는 판단",
        "정리하면 둘은 잘하는 게 정반대입니다. 프로그램은 긴 파일을 순식간에 읽고, 길이나 각도를 "
        "정확히 계산합니다. 하지만 그림을 보고 이게 무슨 모양인지 판단하거나, 사람이 대충 적은 글자를 "
        "정리하는 건 못 합니다. AI 는 반대로 그림을 보고 모양을 알아보고, 애매한 글자를 알아듣는 건 "
        "잘하지만, 긴 파일은 못 읽고 정밀한 계산은 자주 틀립니다. 그러면 둘을 같이 쓰면 되겠죠.",
    )
    rows = [
        "긴 파일 읽기",
        "정확한 계산 (길이 · 각도)",
        "그림 보고 모양 판단",
        "애매한 글자 알아듣기",
    ]
    marks = [(True, False), (True, False), (False, True), (False, True)]
    label_w, col_w, row_h = 5.2, 3.2, 0.85
    cols_x = [X0 + label_w + 0.2, X0 + label_w + 0.2 + col_w + 0.3]
    for j, (name, fill, color) in enumerate(
        [("프로그램", TEAL, WHITE), ("AI", INK, WHITE)]
    ):
        chip(
            s,
            cols_x[j],
            1.85,
            col_w,
            0.7,
            name,
            fill=fill,
            color=color,
            size=20,
            bold=True,
        )
    for i, (name, (prog, ai)) in enumerate(zip(rows, marks)):
        y = 2.75 + i * (row_h + 0.1)
        shape(
            s, MSO_SHAPE.ROUNDED_RECTANGLE, X0, y, CW, row_h, LIGHT if i % 2 else WHITE
        )
        text(
            s,
            X0 + 0.3,
            y,
            label_w,
            row_h,
            [name],
            size=19,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        for j, good in enumerate((prog, ai)):
            badge(
                s,
                cols_x[j] + col_w / 2 - 0.35,
                y + (row_h - 0.7) / 2,
                0.7,
                CHECK if good else CROSS,
                TEAL if good else "C9D3D6",
                size=24,
            )


def together_slide(d: Deck, cone: Path, flat: Path):
    s = d.content(
        "함께 하면: 원뿔 도면 한 장",
        "프로그램이 읽고, AI 가 판단하고, 프로그램이 계산한다",
        "실제로 원뿔 도면 한 장을 이렇게 처리했습니다. 먼저 프로그램이 DXF 를 읽어 선과 원과 글자 66개, 치수 150, "
        "표제란의 재질 SPCC 두께 4 를 정리합니다. AI 에게는 이 긴 파일 대신, 프로그램이 그린 그림과 "
        "짧은 요약만 줍니다. AI 는 그걸 보고 '이건 원뿔이고, 정면도 평면도 우측면도가 있다'고 판단합니다. "
        "그러면 프로그램이 원뿔 전개 공식으로 철판을 잘라야 할 모양, 즉 전개도를 정확히 계산합니다. "
        "참고로 이 실행에서 AI 가 작은 지름을 92 로 읽었는데 정답은 100 이었습니다. AI 판단은 틀릴 수 "
        "있어서, 그걸 잡아내는 장치를 만드는 게 다음 과제입니다.",
    )
    y = 2.0
    pic_w = 2.9
    picture(s, cone, X0, y + 0.25, pic_w)
    steps = [
        (
            X0 + pic_w + 0.55,
            "프로그램이 정리",
            ["요소 66개", "치수 150", "SPCC · 두께 4"],
            TEAL,
        ),
        (X0 + pic_w + 3.55, "AI 가 판단", ['"원뿔"', "정면 · 평면 · 우측면"], ORANGE),
    ]
    for x, head, lines, color in steps:
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 2.5, 2.5, color)
        text(
            s,
            x,
            y,
            2.5,
            2.5,
            [{"text": line, "bold": True, "size": 17} for line in lines],
            color=WHITE,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=6,
        )
        text(
            s,
            x,
            y + 2.6,
            2.5,
            0.45,
            [head],
            size=16,
            bold=True,
            color=color,
            align=PP_ALIGN.CENTER,
        )
    flat_x = X0 + pic_w + 6.55
    picture(s, flat, flat_x, y + 0.05, CW - (flat_x - X0))
    for x in (X0 + pic_w + 0.05, X0 + pic_w + 3.07, X0 + pic_w + 6.07):
        arrow(s, x, y + 1.07, 0.42, 0.36)
    text(
        s,
        X0,
        y + 2.6,
        pic_w,
        0.45,
        ["DXF 도면"],
        size=16,
        bold=True,
        color=INK,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        flat_x,
        y + 2.6,
        CW - (flat_x - X0),
        0.45,
        ["프로그램이 전개도 계산"],
        size=16,
        bold=True,
        color=TEAL,
        align=PP_ALIGN.CENTER,
    )
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, X0, 5.45, CW, 1.1, ORANGE_TINT)
    text(
        s,
        X0 + 0.3,
        5.45,
        CW - 0.6,
        1.1,
        [
            [
                {"text": "AI 는 판단만, ", "bold": True, "color": ORANGE},
                {"text": "읽기와 계산은 프로그램 → 서로의 약점을 메운다", "bold": True},
            ]
        ],
        size=20,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def convert_slide(d: Deck):
    s = d.content(
        "그래서 DWG 를 DXF 로 바꾼다",
        "DXF 는 프로그램과 AI 를 잇는 다리",
        "이제 처음 질문에 답할 수 있습니다. DWG 는 AutoCAD 회사가 형식을 공개하지 않은 0 과 1 의 "
        "파일이라 AI 도 못 읽고, 우리가 쓰는 공개 프로그램도 못 읽습니다. 그래서 무료 공개 도구인 "
        "LibreDWG 로 DXF 로 바꿉니다. 명령 한 줄이면 됩니다. DXF 가 되면 프로그램이 정확하게 읽을 수 "
        "있고, 프로그램이 정리한 결과를 AI 에게 넘길 수 있습니다. DXF 는 이 둘을 잇는 다리입니다.",
    )
    flow = [
        ("DWG", "회사 도면", INK, WHITE),
        ("변환", "LibreDWG", ORANGE_TINT, INK),
        ("DXF", "글자 파일", TEAL_TINT, INK),
        ("프로그램", "읽기 · 계산", TEAL, WHITE),
        ("AI", "판단", ORANGE, WHITE),
    ]
    w, gap = 2.1, (CW - 5 * 2.1) / 4
    for i, (head, sub, fill, color) in enumerate(flow):
        x = X0 + i * (w + gap)
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.3, w, 1.5, fill)
        text(
            s,
            x,
            2.3,
            w,
            1.5,
            [{"text": head, "bold": True, "size": 22}, {"text": sub, "size": 14}],
            color=color,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
        if i < 4:
            arrow(s, x + w + (gap - 0.32) / 2, 2.88, 0.32, 0.34)
    for x, glyph, color, head in [
        (X0, CROSS, GRAY, "AI 도, 공개 프로그램도\n못 읽는다"),
        (X0 + 2 * (w + gap), CHECK, TEAL, "프로그램이\n정확히 읽는다"),
    ]:
        badge(s, x + w / 2 - 0.35, 4.1, 0.7, glyph, color, size=24)
        text(
            s,
            x,
            4.9,
            w,
            0.8,
            head.split("\n"),
            size=14,
            bold=True,
            color=GRAY,
            align=PP_ALIGN.CENTER,
        )
    chip(
        s,
        X0 + (CW - 6.4) / 2,
        6.0,
        6.4,
        0.55,
        "dwg2dxf -o 도면.dxf 도면.dwg",
        fill=CODE_BG,
        color=CODE_FG,
        size=16,
    )


def limits_slide(d: Deck):
    s = d.content(
        "변환이 늘 되는 건 아니다",
        "회사 도면 536장 중 87장은 제대로 바뀌지 않았다",
        "물론 변환이 늘 되는 건 아닙니다. 회사 도면 536장을 바꿔 보니 87장은 제대로 안 바뀌었습니다. "
        "그중 77장은 더 고약합니다. 변환 도구가 '성공했다'고 끝내 놓고 내용이 빈 파일을 만들었습니다. "
        "그래서 '성공'이라는 말을 믿지 않고, 결과 파일에 선이 실제로 들어 있는지 확인합니다. 실패한 "
        "도면은 다른 변환 도구로 다시 시도하거나, PDF 가 있으면 그림으로 읽는 길로 보냅니다.",
    )
    doughnut_chart(
        s,
        X0,
        1.8,
        6.4,
        4.8,
        ["정상  449", "빈 파일  77", "못 엶  10"],
        [449, 77, 10],
        [TEAL, ORANGE, GRAY],
        hole=55,
    )
    x = X0 + 6.8
    w = CW - 6.8
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.9, w, 2.4, INK)
    text(
        s,
        x,
        2.1,
        w,
        1.0,
        ['"성공"'],
        size=48,
        bold=True,
        color=ORANGE,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        x,
        3.2,
        w,
        0.8,
        ["77장: 그런데 내용은 비어 있다"],
        size=19,
        bold=True,
        color=WHITE,
        align=PP_ALIGN.CENTER,
    )
    verdict(s, x + 0.1, 4.75, w, CHECK, TEAL, "결과를 직접 확인", "선이 들어 있나")


def closing_slide(d: Deck):
    s = d.slide(
        "정리하겠습니다. AI 는 글자와 그림을 읽고 0 과 1 의 파일은 못 읽습니다. 그래서 DWG 를 글자 파일인 "
        "DXF 로 바꿉니다. 그런데 DXF 는 AI 가 읽기엔 너무 길어서, 읽기와 계산은 프로그램이 하고 AI 는 "
        "판단만 합니다. 서로 못하는 걸 채워 주는 분업이고, DXF 가 그 둘을 이어 줍니다. 질문 받겠습니다.",
        dark=True,
    )
    text(s, X0, 0.8, CW, 0.8, ["정리"], size=36, bold=True, color=WHITE)
    points = [
        "AI 는 글자와 그림을 읽는다. 0 과 1 의 파일(DWG)은 못 읽는다",
        "DXF 는 글자지만 너무 길다 (약 2,500쪽)",
        "읽기와 계산은 프로그램, 판단은 AI",
        "DXF 는 둘을 잇는 다리",
    ]
    for i, point in enumerate(points):
        y = 1.9 + i * 1.05
        circle(s, X0, y, 0.65, str(i + 1), size=18)
        text(
            s,
            X0 + 0.95,
            y,
            CW - 0.95,
            0.65,
            [point],
            size=22,
            color=WHITE,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    text(s, X0, 6.3, CW, 0.6, ["질문"], size=26, bold=True, color=ORANGE)


def main() -> None:
    cone, flat = render_cone(), render_flat()
    d = Deck(OUT, TITLE, FOOTER)
    title_slide(d)
    ai_reads_slide(d)
    notepad_slide(d)
    too_long_slide(d)
    program_slide(d)
    strengths_slide(d)
    together_slide(d, cone, flat)
    convert_slide(d)
    limits_slide(d)
    closing_slide(d)
    print(f"{d.count} slides -> {d.save()}")


if __name__ == "__main__":
    main()
