"""Build presentation/dwg_dxf.pptx: DWG and DXF, why the project converts, and how.

PYTHONPATH=. uv run --with python-pptx python presentation/build_dwg_dxf.py

Few words per slide; the numbers are charts and the example is the drawing itself, rendered
from data_v3/synthetic/cone_0019/cone_0019.dxf at build time (a gray box when the file is
missing). Where every number comes from: docs/presentation.md 4절. Customer drawings appear
only as counts and sizes.
"""

from pathlib import Path

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from presentation.slides import (
    CW,
    GRAY,
    INK,
    LIGHT,
    ORANGE,
    ORANGE_TINT,
    TEAL,
    TEAL_TINT,
    WHITE,
    X0,
    Deck,
    arrow,
    badge,
    bar_chart,
    card,
    chip,
    circle,
    code,
    doughnut_chart,
    picture,
    shape,
    text,
)

OUT = Path(__file__).with_name("dwg_dxf.pptx")
TITLE = "DWG 와 DXF: 도면 파일을 LLM agent 가 다루려면"
FOOTER = "PBL cutplan_agent · DWG 와 DXF · 2026-10-24"
CONE_DXF = Path("data_v3/synthetic/cone_0019/cone_0019.dxf")
CONE_PNG = Path(__file__).with_name("build") / "assets" / "cone_0019.png"
FRAME = (20.0, 20.0, 820.0, 574.0)  # cone_0019 drawing frame in DXF units
CHECK, CROSS = "✓", "✕"


def render_cone() -> Path:
    """Draw cone_0019.dxf with the axes fixed to its frame, so DXF coordinates map
    linearly onto the picture (see at())."""
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
    CONE_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CONE_PNG, dpi=200, facecolor="white")
    plt.close(fig)
    return CONE_PNG


def at(px, py, pw, dx, dy):
    """Slide position (inches) of DXF point (dx, dy) on a picture placed at px, py with
    width pw."""
    x0, y0, x1, y1 = FRAME
    ph = pw * (y1 - y0) / (x1 - x0)
    return px + (dx - x0) / (x1 - x0) * pw, py + (y1 - dy) / (y1 - y0) * ph


def title_slide(d: Deck):
    s = d.slide(
        "이번 파트는 도면 파일 형식 이야기입니다. 고객 도면은 대부분 DWG 로 오는데, 우리 파이프라인은 "
        "전부 DXF 를 읽습니다. 두 형식이 무엇이 다른지, 왜 굳이 DXF 로 바꾸는지, 'DXF 는 텍스트라서 "
        "LLM 이 읽을 수 있다'는 말이 사실인지 실제 파일로 확인한 결과, 그리고 변환 방법과 한계를 "
        "보여 드리겠습니다.",
        dark=True,
    )
    text(
        s,
        X0,
        2.2,
        CW,
        1.6,
        ["DWG 와 DXF", "도면 파일을 LLM agent 가 다루려면"],
        size=40,
        bold=True,
        color=WHITE,
        after=4,
    )
    text(
        s,
        X0,
        4.0,
        CW,
        0.5,
        ["왜 DXF 로 바꾸고, 어떻게 바꾸나"],
        size=20,
        color=ORANGE,
    )
    text(
        s, X0, 6.4, CW, 0.4, ["PBL cutplan_agent · 2026-10-24"], size=14, color="B8C4C9"
    )


def compare_slide(d: Deck):
    s = d.content(
        "DWG 와 DXF",
        "같은 도면, 다른 그릇",
        "DWG 는 AutoCAD 가 기본으로 저장하는 바이너리 형식이고, Autodesk 가 공식 사양을 공개하지 "
        "않았습니다. Open Design Alliance 의 역공학 사양이나 GNU LibreDWG 같은 도구로 읽습니다. DXF 는 "
        "Autodesk 가 다른 프로그램과 도면을 주고받으라고 사양을 공개한 교환 형식이고 보통 텍스트입니다. "
        "아래 막대는 우리 입력 도면 9장을 DXF 로 바꿨을 때의 평균 크기로, 약 6배 커집니다.",
    )
    tiles = [
        ("DWG", ["AutoCAD 저장 형식", "바이너리", "사양 비공개"], INK, WHITE, "B8C4C9"),
        ("DXF", ["교환 형식", "텍스트", "사양 공개"], TEAL_TINT, INK, TEAL),
    ]
    w = 4.6
    for i, (name, tags, fill, color, tag_color) in enumerate(tiles):
        x = X0 if i == 0 else X0 + CW - w
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.8, w, 2.6, fill)
        text(
            s,
            x + 0.35,
            1.95,
            w - 0.7,
            0.9,
            [name],
            size=44,
            bold=True,
            color=color,
        )
        for j, tag in enumerate(tags):
            chip(
                s,
                x + 0.35,
                2.95 + j * 0.47,
                w - 0.7,
                0.38,
                tag,
                fill=WHITE if i else "33434B",
                color=tag_color if i else WHITE,
                size=14,
                bold=True,
            )
    mid = X0 + w + 0.3
    mw = CW - 2 * w - 0.6
    arrow(s, mid + 0.2, 2.85, mw - 0.4, 0.5)
    chip(s, mid, 2.2, mw, 0.45, "dwg2dxf", fill=ORANGE_TINT, size=16, bold=True)
    text(
        s,
        X0,
        4.7,
        CW,
        0.4,
        ["평균 파일 크기 (우리 입력 도면 9장, MB)"],
        size=14,
        bold=True,
        color=GRAY,
    )
    bar_chart(
        s,
        X0,
        5.0,
        CW,
        1.75,
        ["DWG", "DXF"],
        [0.30, 1.80],
        [INK, TEAL],
        number_format="0.00",
        label_size=15,
        gap=40,
    )


def inside_slide(d: Deck):
    s = d.content(
        "파일을 열어 보면",
        "DWG 는 버전 문자열 뒤가 바이너리, DXF 는 '코드 / 값' 두 줄의 반복",
        "DWG 는 처음 6바이트가 버전 문자열이고 그 뒤는 압축된 바이너리라 사람이 읽을 수 없습니다. "
        "왼쪽은 우리 입력 도면 536장의 버전 분포로, R2007 과 R2004 형식이 거의 전부입니다. 이 버전이 "
        "뒤에서 볼 변환 실패와 관련이 있습니다. 오른쪽은 합성 도면 cone_0019.dxf 의 선 하나를 그대로 "
        "옮긴 것입니다. 한 줄은 그룹 코드, 다음 줄은 값입니다. 0 은 엔티티 시작, 8 은 레이어, "
        "10·20 은 시작점, 11·21 은 끝점입니다. 좌표는 있지만 '정면도의 윗변'이라는 뜻은 없습니다.",
    )
    text(
        s,
        X0,
        1.8,
        5.6,
        0.4,
        ["DWG 536장의 버전 (처음 6바이트, 장)"],
        size=15,
        bold=True,
        color=GRAY,
    )
    doughnut_chart(
        s,
        X0,
        2.2,
        5.6,
        4.4,
        ["R2007  301", "R2004  231", "R2010  4"],
        [301, 231, 4],
        [ORANGE, TEAL, GRAY],
    )
    text(
        s,
        X0 + 6.1,
        1.8,
        CW - 6.1,
        0.4,
        ["DXF: cone_0019.dxf 의 선 하나 (그대로)"],
        size=15,
        bold=True,
        color=GRAY,
    )
    code(
        s,
        X0 + 6.1,
        2.2,
        CW - 6.1,
        4.4,
        [
            "0        ← 엔티티 시작",
            "LINE",
            "8        ← 레이어",
            "DIM",
            "10       ← 시작점 x",
            "100.0",
            "20       ← 시작점 y",
            "86.0",
            "11       ← 끝점 x",
            "250.0",
            "21       ← 끝점 y",
            "86.0",
            "…",
        ],
        size=15,
    )


def inputs_slide(d: Deck):
    s = d.content(
        "왜 DXF 인가: 코드가 얻는 것",
        "DXF 는 LLM 이 아니라 코드가 정확히 읽으라고 쓴다",
        "도면을 프로그램에 넣는 방법은 세 가지입니다. DWG 를 그대로 쓰면 우리 도구가 아예 읽지 "
        "못합니다. PDF 나 이미지로 쓰면 코드가 얻는 것은 픽셀뿐이라, 선과 치수와 글자를 OCR 이나 VLM 으로 "
        "다시 추정해야 하고 숫자를 잘못 읽을 수 있습니다. DXF 는 좌표, 치수 값, 글자가 정확한 값으로 "
        "들어 있어서 코드가 그대로 계산에 씁니다. 그래서 DXF 를 쓰는 이유는 LLM 이 읽을 수 있어서가 "
        "아니라, 코드가 정확히 읽을 수 있어서입니다. 사양이 공개돼 있어 ezdxf 같은 오픈소스로 다룰 수 "
        "있고, 텍스트라 사람이 열어 디버깅하기도 쉽습니다.",
    )
    lanes = [
        ("DWG 그대로", [("읽지 못함", LIGHT)], CROSS, GRAY),
        (
            "PDF · 이미지",
            [("픽셀", LIGHT), ("OCR · VLM 으로 추정", ORANGE_TINT)],
            "?",
            ORANGE,
        ),
        (
            "DXF",
            [("좌표 · 치수 · 글자", TEAL_TINT), ("그대로 계산", TEAL_TINT)],
            CHECK,
            TEAL,
        ),
    ]
    for r, (name, steps, glyph, color) in enumerate(lanes):
        y = 1.9 + r * 1.55
        chip(
            s,
            X0,
            y,
            2.6,
            1.05,
            name,
            fill=INK if r == 2 else LIGHT,
            color=WHITE if r == 2 else INK,
            size=20,
            bold=True,
        )
        x = X0 + 2.6
        for label, fill in steps:
            arrow(s, x + 0.15, y + 0.36, 0.45, 0.34, fill=GRAY if r == 0 else ORANGE)
            chip(s, x + 0.75, y, 3.0, 1.05, label, fill=fill, size=18, bold=True)
            x += 0.75 + 3.0
        arrow(s, x + 0.15, y + 0.36, 0.45, 0.34, fill=GRAY if r == 0 else ORANGE)
        badge(s, x + 0.8, y + 0.05, 0.95, glyph, color)


def cone_slide(d: Deck, png: Path):
    s = d.content(
        "cone_0019: DXF 에서 바로 읽은 값",
        "모델 없이 코드가 읽고, 전개도는 이 값으로 계산한다",
        "합성 도면 cone_0019 를 DXF 에서 그대로 그린 그림입니다. 판독기는 이 파일에서 ① 표제란의 재질 "
        "SPCC 4t, 축척 1/2, 도면 번호를 모델 없이 정규식으로 읽었고, ② 치수 150 을 치수 엔티티에서 "
        "읽었고, ③ 좌표로 뷰 세 개를 나눴습니다. 전개도는 이 값으로 코드가 계산합니다. 이미지였다면 "
        "이 숫자들을 모두 추정해야 했습니다.",
    )
    px, py, pw = X0, 1.75, 7.2
    picture(s, png, px, py, pw)
    marks = [
        ("1", 575, 125),  # title block
        ("2", 175, 42),  # dimension 150 under the front view
        ("3", 490, 280),  # right view
    ]
    for label, dx, dy in marks:
        cx, cy = at(px, py, pw, dx, dy)
        badge(s, cx - 0.25, cy - 0.25, 0.5, label, ORANGE, size=16)
    rows = [
        ("1", "표제란", "SPCC, 4t · 1/2 · SYN-00019"),
        ("2", "치수", "150 × 150 × 150"),
        ("3", "뷰", "3개 → 전개도 계산"),
    ]
    x = X0 + pw + 0.35
    w = CW - pw - 0.35
    for i, (label, head, value) in enumerate(rows):
        y = 1.85 + i * 1.5
        badge(s, x, y + 0.3, 0.6, label, ORANGE, size=18)
        card(
            s,
            x + 0.8,
            y,
            w - 0.8,
            1.2,
            [
                {"text": head, "bold": True, "size": 15, "color": GRAY},
                {"text": value, "bold": True, "size": 18},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
            after=2,
        )
    chip(
        s,
        x,
        6.3,
        w,
        0.45,
        "모델 호출 0번",
        fill=TEAL,
        color=WHITE,
        size=15,
        bold=True,
    )


def factcheck_slide(d: Deck):
    s = d.content(
        "사실 확인: LLM 이 DXF 를 통째로 읽을 수 있나",
        "텍스트인 것은 맞다. 크기가 서버 컨텍스트의 최대 133배다",
        "'DXF 는 텍스트라서 LLM agent 가 읽을 수 있다'는 말을 확인했습니다. 막대는 DXF 파일 전체의 "
        "토큰 수를, 지금 서버의 컨텍스트 16,384 토큰의 몇 배인지로 나타낸 것입니다. Qwen3.6-27B "
        "토크나이저로 셌습니다. 합성 도면은 0.3배로 들어가지만, 실제 입력 도면은 50배에서 133배입니다. "
        "회색 막대는 모델 자체의 최대 길이 262,144 토큰으로, 이것도 넘습니다. 그래서 텍스트인 것은 맞지만 "
        "통째로 넣는 것은 안 됩니다.",
    )
    text(
        s,
        X0,
        1.8,
        8.4,
        0.4,
        ["DXF 전체 토큰 ÷ 서버 컨텍스트 16,384"],
        size=15,
        bold=True,
        color=GRAY,
    )
    bar_chart(
        s,
        X0,
        2.2,
        8.4,
        4.5,
        [
            "합성 cone_0019",
            "실제 도면 A",
            "실제 도면 B",
            "실제 도면 C",
            "모델 최대 길이",
        ],
        [0.29, 50.3, 51.1, 133.0, 16.0],
        [TEAL, ORANGE, ORANGE, ORANGE, GRAY],
        number_format='0.0"배"',
        label_size=15,
    )
    x = X0 + 8.8
    w = CW - 8.8
    for i, (glyph, color, head, sub) in enumerate(
        [
            (CHECK, TEAL, "텍스트다", "메모장 · grep 으로 열림"),
            (CROSS, ORANGE, "통째로는 못 넣는다", "실제 도면 82만–218만 토큰"),
        ]
    ):
        y = 2.3 + i * 2.15
        badge(s, x + w / 2 - 0.5, y, 1.0, glyph, color, size=34)
        text(
            s,
            x,
            y + 1.1,
            w,
            0.9,
            [{"text": head, "bold": True, "size": 18}, {"text": sub, "size": 13}],
            color=INK,
            align=PP_ALIGN.CENTER,
            after=2,
        )


def barriers_slide(d: Deck):
    s = d.content(
        "통째로 넣으면 안 되는 이유 셋",
        "크기 · 의미 · 인코딩",
        "크기 말고도 두 가지가 더 있습니다. 의미: DXF 에는 그룹 코드와 좌표뿐이고, 실제 도면 하나에 "
        "엔티티가 7천 개를 넘기도 합니다. 정면도나 지름 150 같은 뜻은 엔티티 사이의 위치 관계에서 "
        "나오는데, 그걸 LLM 에게 계산시키는 것은 '계산은 코드가 한다'는 원칙에 어긋납니다. 인코딩: "
        "한글이 CP949 로 저장된 파일이 있어서 UTF-8 로 읽으면 글자가 깨집니다.",
    )
    tiles = [
        ("1", "크기", "×133", "서버 컨텍스트의 최대 133배"),
        ("2", "의미", "7,245", "엔티티 수. 대부분 선 좌표"),
        ("3", "인코딩", "CP949", "UTF-8 로 읽으면 한글이 깨진다"),
    ]
    w = (CW - 2 * 0.3) / 3
    for i, (num, head, value, sub) in enumerate(tiles):
        x = X0 + i * (w + 0.3)
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.85, w, 4.7, LIGHT)
        badge(s, x + w / 2 - 0.4, 2.15, 0.8, num, ORANGE, size=22)
        text(
            s,
            x,
            3.15,
            w,
            0.6,
            [head],
            size=22,
            bold=True,
            color=TEAL,
            align=PP_ALIGN.CENTER,
        )
        text(
            s,
            x,
            3.85,
            w,
            1.1,
            [value],
            size=50,
            bold=True,
            color=ORANGE,
            align=PP_ALIGN.CENTER,
        )
        text(
            s,
            x + 0.3,
            5.2,
            w - 0.6,
            0.9,
            [sub],
            size=16,
            color=GRAY,
            align=PP_ALIGN.CENTER,
        )


def pipeline_slide(d: Deck):
    s = d.content(
        "그래서: 코드가 읽고, LLM 은 좁게 본다",
        "LLM 에게는 코드가 만든 요약과 그림만",
        "그래서 판독기는 DXF 를 LLM 에 통째로 주지 않습니다. ezdxf 로 코드가 파싱하고, 코드가 뷰를 "
        "나누고 치수와 표제란을 찾습니다. LLM 에게는 DXF 에서 그린 그림, 표제란 글자, 요약만 주고 뷰 "
        "종류나 형상 같은 좁은 판단만 맡깁니다. agent 로 확장해도 같습니다. DXF 전체가 아니라 표제란 "
        "텍스트나 한 뷰의 치수처럼 필요한 조각만 꺼내 주는 tool 을 만듭니다.",
    )
    steps = [
        ("DXF", LIGHT, INK),
        ("코드\nezdxf 파싱", TEAL, WHITE),
        ("코드\n뷰 · 치수 · 표제란", TEAL, WHITE),
        ("LLM 입력\n그림 · 요약", ORANGE, WHITE),
        ("LLM 판단\n뷰 · 형상", ORANGE_TINT, INK),
    ]
    w, gap = 2.15, (CW - 5 * 2.15) / 4
    for i, (label, fill, color) in enumerate(steps):
        x = X0 + i * (w + gap)
        head, *rest = label.split("\n")
        card(
            s,
            x,
            2.0,
            w,
            1.6,
            [{"text": head, "bold": True, "size": 19}]
            + [{"text": line, "size": 15} for line in rest],
            fill=fill,
            color=color,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.1,
            after=4,
        )
        if i < 4:
            arrow(s, x + w + (gap - 0.3) / 2, 2.64, 0.3, 0.32)
    w2 = (CW - 0.4) / 2
    for i, (glyph, color, fill, head) in enumerate(
        [
            (CROSS, GRAY, LIGHT, "DXF 통째로 → LLM"),
            (CHECK, TEAL, TEAL_TINT, "필요한 조각만 tool 로 → LLM"),
        ]
    ):
        x = X0 + i * (w2 + 0.4)
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 4.2, w2, 1.7, fill)
        badge(s, x + 0.35, 4.55, 1.0, glyph, color, size=34)
        text(
            s,
            x + 1.6,
            4.2,
            w2 - 1.8,
            1.7,
            [head],
            size=22,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def tools_slide(d: Deck):
    s = d.content(
        "DWG → DXF 변환 도구",
        "이 레포는 LibreDWG. 실패하는 도면은 ODA File Converter 가 다음 후보",
        "변환 도구는 세 가지입니다. GNU LibreDWG 의 dwg2dxf 는 오픈소스 명령행 도구로 이 레포가 "
        "씁니다. Open Design Alliance 의 ODA File Converter 는 무료이고 윈도우, 리눅스, 맥에서 GUI 와 "
        "명령행 모두 되며, ezdxf 의 odafc 애드온으로 부를 수 있습니다. 아직 설치하지 않았습니다. "
        "AutoCAD 는 다른 이름으로 저장에서 DXF 를 고르거나 DXFOUT 명령을 쓰는데 상용입니다. 참고로 "
        "ezdxf 는 DWG 를 직접 읽지 못합니다.",
    )
    tools = [
        (
            "LibreDWG",
            "dwg2dxf",
            ["오픈소스", "명령행", "Linux · Windows"],
            "이 레포 사용 중",
            TEAL,
        ),
        (
            "ODA",
            "File Converter",
            ["무료", "GUI · 명령행", "Win · Linux · macOS"],
            "다음 후보",
            ORANGE,
        ),
        (
            "AutoCAD",
            "다른 이름으로 저장",
            ["상용", "DXFOUT", "Win · macOS"],
            "쓰지 않음",
            GRAY,
        ),
    ]
    w = (CW - 2 * 0.3) / 3
    for i, (name, sub, tags, status, color) in enumerate(tools):
        x = X0 + i * (w + 0.3)
        shape(
            s,
            MSO_SHAPE.ROUNDED_RECTANGLE,
            x,
            1.85,
            w,
            4.75,
            TEAL_TINT if i == 0 else LIGHT,
        )
        text(
            s,
            x,
            2.1,
            w,
            0.7,
            [name],
            size=30,
            bold=True,
            color=INK,
            align=PP_ALIGN.CENTER,
        )
        text(s, x, 2.8, w, 0.45, [sub], size=16, color=GRAY, align=PP_ALIGN.CENTER)
        for j, tag in enumerate(tags):
            chip(
                s,
                x + 0.45,
                3.5 + j * 0.55,
                w - 0.9,
                0.42,
                tag,
                fill=WHITE,
                size=14,
            )
        chip(
            s,
            x + 0.45,
            5.75,
            w - 0.9,
            0.5,
            status,
            fill=color,
            color=WHITE,
            size=15,
            bold=True,
        )


def howto_slide(d: Deck):
    s = d.content(
        "이 레포에서 변환하기",
        "Ubuntu apt 에는 없다. 스크립트가 소스에서 ~/.local 에 빌드한다",
        "실제로 쓰는 명령입니다. 우분투 apt 에는 LibreDWG 가 없어서 install_libredwg.sh 가 GNU 에서 0.14 "
        "소스를 받아 sha256 을 확인하고 sudo 없이 홈 폴더에 빌드합니다. 그다음 dwg2dxf 로 바꾸고, "
        "사람이 볼 PDF 나 PNG 가 필요하면 render_drawings.py 가 변환부터 그리기까지 합니다. 윈도우는 "
        "툴킷의 dwg2dxf.exe 를 씁니다. ODA File Converter 를 설치하면 마지막 명령으로도 바꿀 수 있습니다.",
    )
    code(
        s,
        X0,
        1.85,
        CW,
        4.75,
        [
            "# 1. LibreDWG 0.14 설치 (한 번, sudo 불필요)",
            "scripts/install_libredwg.sh            # → ~/.local/bin/dwg2dxf",
            "",
            "# 2. DWG → DXF",
            "dwg2dxf -y -o out/a.dxf in/a.dwg",
            "",
            "# 3. 사람이 볼 PDF · PNG 까지 한 번에",
            "uv run python scripts/render_drawings.py <DWG 폴더>",
            "",
            "# ODA File Converter 를 설치했다면",
            'ODAFileConverter in/ out/ ACAD2018 DXF 0 1 "*.DWG"',
        ],
        size=17,
    )


def limits_slide(d: Deck):
    s = d.content(
        "변환의 한계",
        "536장 중 87장 실패. 그중 77장은 '성공'으로 끝났다",
        "입력 도면 536장을 LibreDWG 0.14 로 바꾸면 87장, 약 16% 가 제대로 안 바뀝니다. 77장은 R2007 "
        "형식에서 오류를 내고도 종료 코드 0, 즉 성공으로 끝나면서 빈 DXF 를 씁니다. 10장은 ezdxf 가 "
        "열지 못하는 DXF 를 만듭니다. 오늘 11장을 다시 해 봐도 R2007 2장이 빈 DXF 였습니다. 그래서 "
        "변환이 됐는지는 종료 코드가 아니라 결과, 예를 들어 엔티티 수로 확인해야 합니다. 실패한 도면은 "
        "정확한 값을 잃습니다. 47장은 같은 이름의 PDF 가 있어 이미지 경로로는 읽을 수 있고, 나머지는 "
        "ODA File Converter 로 다시 시도할 후보입니다.",
    )
    doughnut_chart(
        s,
        X0,
        1.8,
        6.4,
        4.8,
        ["정상  449", "빈 DXF  77", "못 엶  10"],
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
        2.05,
        w,
        1.1,
        ["exit 0"],
        size=54,
        bold=True,
        color=ORANGE,
        font="Consolas",
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        x,
        3.25,
        w,
        0.8,
        ["77장: 빈 DXF 인데 '성공'"],
        size=20,
        bold=True,
        color=WHITE,
        align=PP_ALIGN.CENTER,
    )
    badge(s, x + 0.1, 4.75, 0.9, CHECK, TEAL, size=30)
    text(
        s,
        x + 1.2,
        4.6,
        w - 1.2,
        1.2,
        [
            {"text": "성공은 결과로 확인", "bold": True, "size": 20},
            {"text": "파일 크기 · 엔티티 수", "size": 16, "color": GRAY},
        ],
        anchor=MSO_ANCHOR.MIDDLE,
        after=2,
    )


def closing_slide(d: Deck):
    s = d.slide(
        "정리하겠습니다. DWG 는 AutoCAD 의 바이너리 저장 형식이고 DXF 는 공개된 텍스트 교환 형식입니다. "
        "DXF 를 쓰는 이유는 코드가 좌표와 치수와 글자를 추정 없이 정확히 읽을 수 있기 때문입니다. "
        "텍스트인 것은 맞지만 실제 도면은 LLM 에 통째로 넣기엔 너무 커서, 코드가 읽고 LLM 에는 필요한 "
        "부분만 줍니다. 변환은 LibreDWG 로 하고, 성공 여부는 결과로 확인합니다. 질문 받겠습니다.",
        dark=True,
    )
    text(s, X0, 0.8, CW, 0.8, ["정리"], size=36, bold=True, color=WHITE)
    points = [
        "DWG 는 바이너리 저장 형식, DXF 는 공개된 텍스트 교환 형식",
        "DXF 를 쓰는 이유: 코드가 정확히 읽는다",
        "LLM 에는 통째로 말고, 필요한 조각만",
        "변환은 LibreDWG. 성공은 결과로 확인",
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
    png = render_cone()
    d = Deck(OUT, TITLE, FOOTER)
    title_slide(d)
    compare_slide(d)
    inside_slide(d)
    inputs_slide(d)
    cone_slide(d, png)
    factcheck_slide(d)
    barriers_slide(d)
    pipeline_slide(d)
    tools_slide(d)
    howto_slide(d)
    limits_slide(d)
    closing_slide(d)
    print(f"{d.count} slides -> {d.save()}")


if __name__ == "__main__":
    main()
