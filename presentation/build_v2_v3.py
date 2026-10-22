"""Build presentation/v2_v3.pptx: how the project got here, for listeners who are new to AI.

PYTHONPATH=. uv run --with python-pptx python presentation/build_v2_v3.py

The story: v2 gave the whole job (drawings to purchase order) to Claude with 25 skills, and it
did not work well; v3 moved to local models on our own server and narrowed the job to reading
one drawing, tested on synthetic drawings (27/30); then the same v3 was run on five real
drawings, and the slides go through what worked and what failed, and why. What comes next is
the separate part presentation/build_roadmap.py. Few words on the slides, the narration is in
the notes.

Where every number comes from: docs/presentation.md 5절. The cone picture is drawn at build
time from data_v3/synthetic (presentation/build_dwg_dxf.py); real drawings appear only as
counts, quoted text and an abstract sketch.
"""

from pathlib import Path

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches

from presentation.build_dwg_dxf import render_cone
from presentation.slides import (
    CHECK,
    CROSS,
    CW,
    GRAY,
    INK,
    LIGHT,
    MONO,
    ORANGE,
    ORANGE_TINT,
    PALE,
    TEAL,
    TEAL_TINT,
    WHITE,
    X0,
    Deck,
    arrow,
    badge,
    band,
    bar_chart,
    bubble,
    card,
    chip,
    circle,
    code,
    dashed,
    page,
    picture,
    real_sheet,
    rgb,
    shape,
    table,
    text,
    write,
)
from presentation.slides import road as _road

OUT = Path(__file__).with_name("v2_v3.pptx")
TITLE = "도면 판독, 지금 어디까지 왔나: v2 → v3 → 실제 도면"
FOOTER = "PBL cutplan_agent · v2 → v3 → 실제 도면 · 2026-10-24"
ROAD = ["v2", "v3", "실제 도면"]

# runs/reader/deepseek_ocr_qwen_reasoning_skills/accuracy.md (colleague, 2026-10-18)
SHAPES = [("원뿔", 6), ("프레스 성형", 6), ("절곡판", 6), ("평판", 5), ("원통", 4)]

# The v3 stages, as in docs/reader/quickstart.md; True = a model answers there
STAGES = [
    ("01", "도면 읽기", False),
    ("02", "표제란 찾기", False),
    ("03", "표제란 받아쓰기", True),
    ("04", "표제란 정리", True),
    ("05", "뷰 나누기", False),
    ("06", "뷰 · 모양 판단", True),
    ("07", "합치기", False),
    ("08", "3D 용 정리", False),
    ("09", "전개 치수", True),
    ("10", "전개 계산", False),
    ("11", "3D 후보", False),
    ("12", "3D 후보 고르기", True),
    ("13", "저장", False),
]

# The five real drawings run through the 13 stages with the served models on 2026-10-23
# (runs/reader/real_drawings_vlm/<drawing>/stages, docs/presentation.md 5절):
# d = done, s = skipped, f = failed, per stage 01..13, and what came out.
REAL = [
    ("S-2120 DWG-001", "조립도", "ddddddddddddd", "원통 1개 (두께 18 → 틀림)"),
    ("S-2120 DWG-002", "본체 상세도", "dddddddfsssss", "멈춤: 뷰 0개"),
    ("S-2120 DWG-003", "맨홀 상세도", "ddddddddssddd", "'기타' → 전개 안 함"),
    ("S-2120 DWG-004", "노즐 상세도", "dddddddfsssss", "멈춤: 정면 · 평면 뷰 없음"),
    (
        "KD23009 E-31230-002",
        "본체 · 러그 상세도",
        "ddddddddddfss",
        "원통 1개 (두께 18 → 틀림)",
    ),
]
# Answer parts per S-2120 drawing (test_data/cases/S-2120/output_cutting_plan/parts.csv,
# distinct drawing/item pairs) and the parts v3 developed from it
SCORE = [
    ("조립도", 0, 1),
    ("본체 상세도", 13, 0),
    ("맨홀 상세도", 4, 0),
    ("노즐 상세도", 5, 0),
]


def road(s, here: int):
    _road(s, here, ROAD, w=1.05)


# ---------------------------------------------------------------------- slides


def v2_slide(d: Deck):
    s = d.content(
        "v2: AI 에게 일 전체를 맡겼다",
        "가장 강한 Claude 가 도구 25개를 골라 쓰며 도면부터 구매의뢰까지",
        "v2 는 이렇게 생겼습니다. 왼쪽의 도면 세트를 Claude 에게 줍니다. Claude 는 Anthropic 이라는 회사의 "
        "AI 이고, 그중에서도 가장 강한 모델(Opus)을 썼습니다. Claude 옆에는 도구 25개가 있습니다. 도면을 "
        "열고 글자를 읽는 도구, 도면 종류나 부품 모양을 판단하는 도구, 전개와 네스팅과 구매의뢰를 "
        "계산하는 도구, 무게나 겹침을 검사하고 사람에게 묻는 도구입니다. 이 도구를 skill 이라고 "
        "불렀습니다. Claude 는 이 도구를 스스로 골라 쓰면서 도면에서 구매의뢰서까지 가야 했습니다. "
        "도면을 보는 것도 Claude, 순서를 정하는 것도 Claude 였습니다. 대상은 연습용 도면이 아니라 실제 "
        "회사 도면(압력용기, 판금 부품)이었습니다.",
    )
    road(s, 0)
    for k in range(3):
        page(s, X0 + 0.18 * k, 2.3 + 0.18 * k, 1.3, 1.75)
    text(
        s,
        X0 - 0.1,
        4.45,
        1.9,
        0.7,
        [
            {"text": "도면 세트", "bold": True, "size": 16},
            {"text": "실제 회사 도면", "size": 13, "color": GRAY},
        ],
        align=PP_ALIGN.CENTER,
        after=0,
    )
    arrow(s, 2.5, 3.35, 0.35, 0.36)
    circle(s, 3.0, 2.45, 2.0, "Claude", fill=INK, size=24)
    text(
        s,
        2.6,
        4.6,
        2.8,
        0.7,
        ["보는 것도, 순서를 정하는 것도"],
        size=13,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, 5.15, 3.3, 0.5, 0.42, kind=MSO_SHAPE.LEFT_RIGHT_ARROW)
    groups = [
        ("4", "보기 · 읽기", "도면 열기, 글자 읽기"),
        ("7", "판단", "도면 종류, 부품 모양"),
        ("6", "계산", "전개, 네스팅, 구매의뢰"),
        ("6", "검사", "무게 · 겹침, 사람 확인"),
    ]
    gx, gw, gh = 5.8, 2.45, 1.3
    for i, (n, head, sub) in enumerate(groups):
        r, c = divmod(i, 2)
        card(
            s,
            gx + c * (gw + 0.15),
            2.05 + r * (gh + 0.15),
            gw,
            gh,
            [
                [
                    {"text": n, "bold": True, "size": 30, "color": ORANGE},
                    {"text": "  " + head, "bold": True, "size": 18},
                ],
                {"text": sub, "size": 13, "color": GRAY},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
            after=2,
        )
    text(
        s,
        gx,
        4.85,
        2 * gw + 0.15,
        0.4,
        ["+ 상태 확인 2개 = 도구(skill) 25개"],
        size=14,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, 10.95, 3.35, 0.35, 0.36)
    page(s, 11.4, 2.4, 1.33, 1.75, fill=ORANGE_TINT, line_color=ORANGE)
    text(
        s,
        11.1,
        4.25,
        1.9,
        0.7,
        [
            {"text": "커팅플랜", "bold": True, "size": 15},
            {"text": "구매의뢰서", "bold": True, "size": 15},
        ],
        align=PP_ALIGN.CENTER,
        after=0,
    )
    band(
        s,
        5.55,
        "v2",
        "Claude Opus (클라우드 AI) 하나가 ① 도면 읽기부터 ④ 구매의뢰까지 전부",
        fill=LIGHT,
        color=INK,
    )


def skill_slide(d: Deck):
    s = d.content(
        "skill 은 무엇인가",
        "프로그램이 할 줄 아는 일 하나 + AI 가 읽는 이름과 설명",
        "skill 이 무엇인지 식당에 비유해 보겠습니다. AI 는 손님이고, 프로그램은 주방입니다. 손님은 "
        "메뉴판을 봅니다. 메뉴판에는 요리 이름과 설명, 주문할 때 적을 것이 있습니다. skill 도 똑같이 "
        "이름, 설명, 입력 양식이 있습니다. AI 가 'unfold_part 를 부품 3번으로'라고 주문하면, 실제 계산은 "
        "주방, 즉 우리가 미리 짜 둔 프로그램이 합니다. AI 가 직접 원주율을 곱하는 게 아닙니다. 그리고 "
        "skill 에는 참고서도 있습니다. 전개 규칙, 도면 읽는 법 같은 도메인 지식 문서 7권인데, AI 가 "
        "필요할 때 펼쳐 봅니다.",
    )
    road(s, 0)
    card(
        s,
        X0,
        1.85,
        5.0,
        3.65,
        [{"text": "메뉴판 — AI 가 보는 것", "bold": True, "size": 18, "color": TEAL}],
        fill=TEAL_TINT,
        margin=0.25,
    )
    menu = [
        ("unfold_part", "부품을 펼친 크기를 계산한다", "부품 번호"),
        ("nest_all", "조각을 철판 위에 배치한다", "자르는 방식"),
        ("ask_human", "사람에게 확인을 받는다", "질문"),
    ]
    for i, (name, desc, form) in enumerate(menu):
        card(
            s,
            X0 + 0.2,
            2.62 + i * 0.93,
            4.6,
            0.8,
            [
                [
                    {"text": name, "bold": True, "font": MONO, "size": 15},
                    {"text": "   입력: " + form, "size": 12, "color": GRAY},
                ],
                {"text": desc, "size": 14},
            ],
            fill=WHITE,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.15,
            after=1,
        )
    circle(s, 6.05, 2.2, 1.1, "AI", fill=INK, size=22)
    card(
        s,
        5.75,
        3.5,
        1.7,
        0.95,
        [
            {"text": "주문", "bold": True, "size": 13, "color": ORANGE},
            {"text": "unfold_part(3)", "size": 12, "font": MONO, "bold": True},
        ],
        fill=ORANGE_TINT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0.05,
        after=0,
    )
    arrow(s, 7.5, 3.78, 0.32, 0.36)
    kx = 7.95
    kw = CW - (kx - X0)
    text(
        s,
        kx,
        1.85,
        kw,
        0.5,
        [{"text": "주방 — 프로그램이 하는 일", "bold": True}],
        size=18,
        color=ORANGE,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    code(
        s,
        kx,
        2.45,
        kw,
        3.05,
        [
            "def unfold_part(part_index):",
            '    """부품을 펼친 크기를 계산한다"""',
            "    p = 부품[part_index]",
            "    if p.모양 == '원통':",
            "        길이 = π × (지름 + 두께)",
            "    ...",
            "    return {'전개 길이': 길이, ...}",
        ],
        size=14,
    )
    band(
        s,
        5.75,
        "skill 문서 = 참고서 7권",
        "전개 규칙, 도면 읽는 법, 네스팅 규칙 … — AI 가 필요할 때 펼쳐 본다",
        fill=LIGHT,
        color=TEAL,
    )


def claude_loop_slide(d: Deck):
    s = d.content(
        "Claude 는 skill 을 이렇게 썼다",
        "Claude 는 주문만 하고 일은 프로그램이 한다. 이것을 수십 번 되풀이",
        "Claude 가 skill 을 쓰는 모습을 대화로 옮겨 봤습니다. 프로그램이 먼저 도면 목록과 메뉴판 25개를 "
        "줍니다. Claude 는 '도면 1번을 열어 줘'라고 주문하고, 프로그램이 실행해서 결과를 돌려줍니다. "
        "Claude 가 그 결과를 보고 다음 주문을 합니다. 도면 종류를 판단하고, 자재표를 읽고, 전개하고, "
        "배치하고, 구매의뢰서를 쓸 때까지 이걸 수십 번 반복합니다. 오른쪽이 그 반복을 그림으로 그린 "
        "것입니다. 이 방식에는 이름이 있는데, 뒤에서 다시 나옵니다.",
    )
    road(s, 0)
    lines = [
        ("프로그램", "도면 12장과 메뉴판(skill 25개)을 줄게", False),
        ("Claude", "ingest_drawing(도면 1)", True),
        ("프로그램", "준비 끝: 그림 3쪽", False),
        ("Claude", "classify_drawing(도면 1)", True),
        ("프로그램", "본체 상세도, 자재표 있음", False),
        ("Claude", "… nest_all() → build_por()", True),
        ("프로그램", "커팅플랜 · 구매의뢰서 완성", False),
    ]
    bw = 6.3
    for i, (who, said, ai) in enumerate(lines):
        bubble(s, X0 + (1.2 if ai else 0), 1.85 + i * 0.68, bw, 0.56, who, said, ai=ai)
    lx = X0 + 7.95
    lw = CW - 7.95
    loop = [
        ("1", "메뉴판을 보고 고른다", "Claude"),
        ("2", "주문한다 — 이름 + 입력값", "Claude"),
        ("3", "실행한다", "프로그램"),
        ("4", "결과를 돌려준다", "프로그램"),
    ]
    for i, (num, head, who) in enumerate(loop):
        y = 1.95 + i * 1.0
        circle(s, lx, y, 0.62, num, fill=INK if who == "Claude" else TEAL, size=16)
        text(
            s,
            lx + 0.8,
            y - 0.05,
            lw - 0.8,
            0.72,
            [
                {"text": head, "bold": True, "size": 16},
                {"text": who, "size": 13, "color": GRAY},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            after=0,
        )
    arrow(s, lx + 0.16, 5.95, 0.3, 0.36, kind=MSO_SHAPE.UP_ARROW)
    text(
        s,
        lx + 0.6,
        5.9,
        lw - 0.6,
        0.5,
        ["다시 1 로 — 끝날 때까지"],
        size=15,
        color=ORANGE,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def v2_result_slide(d: Deck):
    s = d.content(
        "v2 결과: 잘 안 됐다",
        "일이 너무 컸다. 첫 단추(도면 읽기)가 어긋나면 뒤가 전부 틀린다",
        "결과는 잘 안 됐습니다. 이유는 일이 너무 컸다는 데 있습니다. 네 단계가 줄줄이 이어져 있어서, 첫 "
        "단계인 도면 읽기에서 숫자 하나가 틀리면 그 뒤의 전개도, 커팅플랜, 구매의뢰가 전부 틀립니다. 예를 "
        "들어 원통의 지름을 10 mm 잘못 읽으면 펼친 길이는 31 mm 가 달라지고, v2 의 AI 지침서에 적어 둔 "
        "현장 기준으로 그렇게 자른 철판은 못 씁니다. 그리고 단계마다 맞았는지 재지 않으면 어디서 "
        "틀렸는지 찾기 어렵습니다. 그래서 배운 것은, "
        "첫 단추인 도면 읽기부터 제대로 해야 한다는 것이었습니다.",
    )
    road(s, 0)
    steps = ["① 도면 읽기", "② 전개도", "③ 커팅플랜", "④ 구매의뢰"]
    w, gap = 2.6, 0.58
    for i, name in enumerate(steps):
        x = X0 + i * (w + gap)
        first = i == 0
        card(
            s,
            x,
            1.95,
            w,
            1.15,
            [{"text": name, "bold": True, "size": 20}],
            fill=ORANGE_TINT if first else LIGHT,
            color=INK if first else GRAY,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        badge(
            s, x + w - 0.45, 1.75, 0.55, CROSS, ORANGE if first else "AAB6BB", size=18
        )
        if i < 3:
            arrow(s, x + w + 0.13, 2.36, 0.32, 0.34, fill=ORANGE if first else PALE)
    text(
        s,
        X0,
        3.2,
        w,
        0.4,
        ["숫자 하나가 어긋나면"],
        size=14,
        color=ORANGE,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        X0 + w + gap,
        3.2,
        3 * w + 2 * gap,
        0.4,
        ["뒤는 전부 틀린다"],
        size=14,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    chain = [
        ("10 mm", "예: 지름을 잘못 읽으면"),
        ("31 mm", "펼친 길이가 달라지고"),
        ("폐기", "그렇게 자른 철판은"),
    ]
    cw2 = 3.5
    gap2 = (CW - 3 * cw2) / 2
    for i, (big, small) in enumerate(chain):
        x = X0 + i * (cw2 + gap2)
        box = card(
            s,
            x,
            3.8,
            cw2,
            1.35,
            [
                {"text": small, "size": 15, "color": GRAY},
                {"text": big, "bold": True, "size": 36, "color": ORANGE},
            ],
            fill=WHITE,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=0,
        )
        box.line.color.rgb = rgb(PALE)
        if i < 2:
            arrow(s, x + cw2 + gap2 / 2 - 0.18, 4.3, 0.36, 0.36)
    band(
        s,
        5.65,
        "배운 것",
        "단계마다 맞았는지 재지 않으면 어디서 틀렸는지 찾기 어렵다 → 첫 단추부터 제대로",
    )
    text(
        s,
        X0,
        5.22,
        CW,
        0.3,
        [
            "예시의 기준: v2 의 AI 지침서에 적힌 현장 기준 (지름 10 mm 오차 = 둘레 31 mm, 그 판은 폐기)"
        ],
        size=11,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )


def why_move_slide(d: Deck):
    s = d.content(
        "왜 옮겼나",
        "수업의 목표, v2 의 교훈, 비용과 보안",
        "v3 로 넘어간 이유는 세 가지입니다. 첫째, 이 수업의 목표입니다. 비싼 AI 하나가 아니라 값싼 로컬 "
        "AI 로도, 주변 장치인 하네스를 잘 만들면 쓸 만한 결과를 낼 수 있다는 걸 보이는 것이 목표입니다. "
        "Claude 는 처음에 무엇이 필요한지 찾는 시행착오용이었습니다. 둘째, v2 의 교훈입니다. 일이 너무 "
        "컸습니다. 더 작은 로컬 AI 에게는 더더욱 그렇습니다. 그래서 첫 단추인 도면 읽기부터, 좁은 질문으로 "
        "시작했습니다. 셋째, 비용과 보안입니다. 클라우드 AI 는 부를 때마다 돈이 들고, 회사 도면이 바깥 "
        "서버로 나갑니다. 로컬 AI 는 우리 서버 안에서 돕니다.",
    )
    road(s, 1)
    reasons = [
        (
            "1",
            "수업의 목표",
            "값싼 로컬 AI + 하네스로도 된다는 것을 보인다",
            "Claude 는 무엇이 필요한지 찾는 시행착오용",
        ),
        (
            "2",
            "v2 의 교훈",
            "일이 너무 컸다. 작은 AI 에게는 더더욱",
            "→ 첫 단추(도면 읽기)부터, 좁은 질문으로",
        ),
        (
            "3",
            "비용과 보안",
            "클라우드 AI 는 부를 때마다 비용, 도면이 바깥 서버로",
            "→ 로컬 AI 는 우리 서버 안에서",
        ),
    ]
    w, gap = 3.85, 0.29
    for i, (num, head, body, sub) in enumerate(reasons):
        x = X0 + i * (w + gap)
        card(
            s,
            x,
            1.95,
            w,
            3.5,
            [
                {"text": head, "bold": True, "size": 24, "color": TEAL},
                {"text": body, "bold": True, "size": 17},
                {"text": sub, "size": 15, "color": GRAY},
            ],
            margin=0.3,
            after=10,
        ).text_frame.margin_top = Inches(1.3)
        circle(s, x + 0.3, 2.25, 0.8, num, size=24)
    band(s, 5.7, "그래서 v3", "누가 → 우리 서버의 로컬 AI,  무엇을 → 도면 읽기 하나")


def v3_shift_slide(d: Deck):
    s = d.content(
        "v3: 무게중심을 옮겼다",
        "누가 → 우리 서버의 로컬 AI, 무엇을 → 도면 읽기 하나",
        "그래서 무엇을 옮겼는지 정리하면 이렇습니다. 첫째, 누가 하느냐입니다. Claude 는 회사 밖 클라우드에 "
        "있어서 부를 때마다 돈이 들고 도면이 밖으로 나갑니다. v3 는 우리 서버에 직접 띄운 로컬 AI 를 "
        "씁니다. 둘째, 무엇을 하느냐입니다. 네 단계 전부가 아니라 첫 단추인 도면 읽기 하나에 "
        "집중했습니다. 전개도는 읽은 치수로 프로그램이 계산합니다. 셋째, 순서는 AI 가 정하지 않고 코드에 "
        "고정했습니다. AI 는 정해진 다섯 곳에서 질문에 답만 합니다.",
    )
    road(s, 1)
    rows = [
        (
            "누가",
            ("Claude — 회사 밖 클라우드", "부를 때마다 비용 · 도면이 밖으로"),
            ("로컬 AI — 우리 서버", "추가 비용 없음 · 도면이 안 나간다"),
        ),
        (
            "무엇을",
            ("① → ④ 전부", "도면부터 구매의뢰서까지"),
            ("① 도면 읽기에 집중", "② 전개도는 읽은 치수로 프로그램이 계산"),
        ),
        (
            "어떻게",
            ("AI 가 순서까지 정한다", "도구 25개 중 골라 쓰기"),
            ("순서는 코드가 정한다", "AI 는 정해진 다섯 곳에서 답만"),
        ),
    ]
    lw, bw, aw, agap = 1.5, 4.4, 0.55, 0.2
    bx = X0 + lw + 0.2
    ax = bx + bw + agap
    afx = ax + aw + agap
    afw = CW - (afx - X0)
    for i, (label, before, after) in enumerate(rows):
        y = 1.95 + i * 1.5
        chip(s, X0, y + 0.3, lw, 0.65, label, fill=INK, color=WHITE, size=18, bold=True)
        for x, w, (head, sub), fill, color in (
            (bx, bw, before, LIGHT, GRAY),
            (afx, afw, after, TEAL_TINT, TEAL),
        ):
            card(
                s,
                x,
                y,
                w,
                1.25,
                [
                    {"text": head, "bold": True, "size": 19, "color": color},
                    {"text": sub, "size": 14, "color": GRAY},
                ],
                fill=fill,
                anchor=MSO_ANCHOR.MIDDLE,
                margin=0.25,
                after=3,
            )
        arrow(s, ax, y + 0.43, aw, 0.4)
    text(s, bx, 6.45, bw, 0.35, ["v2"], size=13, color=GRAY, bold=True)
    text(s, afx, 6.45, afw, 0.35, ["v3"], size=13, color=TEAL, bold=True)


def server_slide(d: Deck):
    s = d.content(
        "로컬 AI 는 이렇게 띄웠다",
        "GPU 4장짜리 서버 한 대에 AI 두 개: 글자 받아쓰기 + 그림 보고 판단",
        "로컬 AI 를 어떻게 띄웠는지 보겠습니다. AI 모델은 숫자가 가득 든 큰 파일이라고 생각하시면 됩니다. "
        "이 파일을 GPU 라는 계산 장치의 메모리에 올려야 돌아갑니다. 서버에는 메모리 24 GB 짜리 GPU 가 "
        "4장 있습니다. 첫 번째 장에는 글자 받아쓰기 전문인 OCR 모델을 올렸습니다. 6 GB 로 작습니다. "
        "나머지 세 장에는 그림과 글자를 같이 보고 판단하는 추론 모델 Qwen 을 올렸습니다. 52 GB 라서 한 "
        "장에 안 들어가, 세 장에 나눠 올렸습니다. 클수록 똑똑하지만 그만큼 GPU 가 더 필요합니다. 참고로 "
        "동료는 90 GB 급 GPU 두 장으로 같은 실험을 했습니다.",
    )
    road(s, 1)
    sw = 7.25
    card(
        s,
        X0,
        1.85,
        sw,
        3.55,
        [{"text": "작업 서버 1대", "bold": True, "size": 17}],
        fill=LIGHT,
        margin=0.25,
    )
    gw, gg = 1.58, 0.13
    gx0 = X0 + 0.3
    for i in range(4):
        card(
            s,
            gx0 + i * (gw + gg),
            2.5,
            gw,
            1.55,
            [
                {"text": f"GPU {i}", "bold": True, "size": 17},
                {"text": "24 GB", "size": 14},
            ],
            fill=TEAL if i == 0 else ORANGE,
            color=WHITE,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
    shape(s, MSO_SHAPE.RECTANGLE, gx0, 4.18, gw, 0.07, TEAL)
    shape(s, MSO_SHAPE.RECTANGLE, gx0 + gw + gg, 4.18, 3 * gw + 2 * gg, 0.07, ORANGE)
    text(
        s,
        gx0,
        4.3,
        gw,
        0.9,
        [{"text": "OCR 모델", "bold": True}, {"text": "6 GB", "color": GRAY}],
        size=15,
        align=PP_ALIGN.CENTER,
        after=0,
    )
    text(
        s,
        gx0 + gw + gg,
        4.3,
        3 * gw + 2 * gg,
        0.9,
        [
            {"text": "추론 모델 — 3장에 나눠 올림", "bold": True},
            {"text": "52 GB (한 장 24 GB 에 안 들어간다)", "color": GRAY},
        ],
        size=15,
        align=PP_ALIGN.CENTER,
        after=0,
    )
    x = X0
    for spec, w in zip(
        ["GPU  RTX A5000 24 GB × 4", "CPU  Xeon 48코어", "메모리  128 GB"],
        [3.1, 2.0, 1.85],
    ):
        chip(
            s, x, 5.6, w, 0.5, spec, fill=WHITE, size=13, bold=True
        ).line.color.rgb = rgb(PALE)
        x += w + 0.15
    rx = X0 + sw + 0.3
    rw = CW - sw - 0.3
    roles = [
        (
            "글자 받아쓰기",
            "OCR 모델 · DeepSeek-OCR-2",
            "표제란 그림 → 글자",
            TEAL,
            TEAL_TINT,
        ),
        (
            "그림 보고 판단",
            "추론 모델 (VLM) · Qwen3.6-27B",
            "그림 + 글자 → 정해진 양식의 답",
            ORANGE,
            ORANGE_TINT,
        ),
    ]
    for i, (head, model, job, color, fill) in enumerate(roles):
        card(
            s,
            rx,
            1.85 + i * 1.9,
            rw,
            1.7,
            [
                {"text": head, "bold": True, "size": 21, "color": color},
                {"text": model, "size": 14, "bold": True},
                {"text": job, "size": 14, "color": GRAY},
            ],
            fill=fill,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.25,
            after=4,
        )
    text(
        s,
        rx,
        5.6,
        rw,
        0.8,
        ["AI 모델 = 숫자가 가득 든 큰 파일. 클수록 똑똑하지만 GPU 가 더 든다"],
        size=14,
        color=GRAY,
    )


def stages_slide(d: Deck):
    s = d.content(
        "v3 판독: 13단계 중 AI 는 5곳",
        "나머지 8곳은 프로그램이 읽고 계산한다",
        "v3 가 도면 한 장을 읽는 과정입니다. 13단계로 나뉘어 있고, 주황색 다섯 곳에서만 AI 에게 묻습니다. "
        "표제란 그림을 글자로 받아쓰고, 그 글자를 정리하고, 도면의 뷰와 부품 모양을 판단하고, 전개에 "
        "필요한 치수를 고르고, 3D 후보를 고릅니다. 나머지, 도면 파일을 읽고 계산하는 일은 전부 "
        "프로그램이 합니다. 앞의 DXF 이야기와 같은 분업입니다. 순서는 코드에 고정돼 있어서 01 부터 13 "
        "까지 늘 같은 순서로 돕니다.",
    )
    road(s, 1)
    w, h, gap = 1.62, 1.05, 0.12
    for i, (num, name, model) in enumerate(STAGES):
        row, col = divmod(i, 7)
        card(
            s,
            X0 + col * (w + gap) + (0 if row == 0 else (w + gap) / 2),
            1.95 + row * (h + 0.25),
            w,
            h,
            [
                {"text": num, "size": 12, "bold": True},
                {"text": name, "size": 14, "bold": model},
            ],
            fill=ORANGE if model else LIGHT,
            color=WHITE if model else INK,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=0,
            margin=0.04,
        )
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, X0, 4.55, 0.32, 0.32, ORANGE, radius=0.15)
    text(s, X0 + 0.45, 4.5, 3.4, 0.4, ["AI 에게 묻는 곳 (5)"], size=15)
    shape(
        s, MSO_SHAPE.ROUNDED_RECTANGLE, X0 + 4.0, 4.55, 0.32, 0.32, LIGHT, radius=0.15
    )
    text(s, X0 + 4.45, 4.5, 4.5, 0.4, ["프로그램이 하는 곳 (8)"], size=15)
    band(
        s,
        5.35,
        "순서는 고정",
        "01 → 13 을 코드가 늘 같은 순서로 돌린다. AI 는 부품처럼 정해진 곳에서 답만 한다",
        fill=LIGHT,
        color=INK,
        h=1.1,
    )


def synthetic_slide(d: Deck, cone: Path):
    s = d.content(
        "왜 연습용(합성) 도면부터?",
        "로컬 AI 는 Claude 보다 작고, 도면을 보는 눈이 특히 약하다 → 쉬운 시험지부터",
        "그런데 시험은 실제 회사 도면이 아니라 우리가 만든 연습용 도면, 합성 도면으로 했습니다. 이유는 "
        "로컬 AI 가 Claude 보다 작고 약해서입니다. 특히 도면 그림을 보고 알아보는 능력이 더 떨어졌습니다. "
        "실제 회사 도면은 오른쪽처럼 한 장에 부품이 여러 개 있고, 표와 주석이 빽빽합니다. 선과 글자가 "
        "2천에서 6천 개입니다. 연습용 도면은 왼쪽처럼 부품 하나에 뷰 세 개, 선과 글자 66개뿐이고, "
        "정답지도 같이 있습니다. 그래서 쉬운 시험지에서 먼저 되는지 확인하기로 했습니다. 다섯 가지 모양을 "
        "여섯 장씩, 모두 30장입니다.",
    )
    road(s, 1)
    pw, pg = 5.8, 0.533
    for i, (head, fill) in enumerate(
        [("연습용 (합성) 도면", TEAL), ("실제 회사 도면", ORANGE)]
    ):
        chip(
            s,
            X0 + i * (pw + pg),
            1.85,
            pw,
            0.5,
            head,
            fill=fill,
            color=WHITE,
            size=17,
            bold=True,
        )
    pic_w, pic_h = 3.9, 2.7
    picture(s, cone, X0 + (pw - pic_w) / 2, 2.5, pic_w, pic_h)
    real_sheet(s, X0 + pw + pg + (pw - pic_w) / 2, 2.5, pic_w, pic_h)
    facts = [
        [
            ("부품 1개", CHECK),
            ("뷰 3개", CHECK),
            ("선 · 글자 66개", CHECK),
            ("정답지 있음", CHECK),
        ],
        [
            ("부품 여러 개", CROSS),
            ("뷰 후보 최대 13개", CROSS),
            ("선 · 글자 2,000–5,900개", CROSS),
            ("정답지 없음", CROSS),
        ],
    ]
    cw2 = (pw - 0.15) / 2
    for i, rows in enumerate(facts):
        x0 = X0 + i * (pw + pg)
        for j, (label, mark) in enumerate(rows):
            r, c = divmod(j, 2)
            chip(
                s,
                x0 + c * (cw2 + 0.15),
                5.4 + r * 0.6,
                cw2,
                0.5,
                label,
                fill=TEAL_TINT if mark == CHECK else ORANGE_TINT,
                size=14,
                bold=True,
            )


def result_slide(d: Deck):
    s = d.content(
        "결과: 연습 도면 30장 중 27장",
        "도면을 보고 어떤 모양의 부품인지 맞혔다 — 여기까지가 지금",
        "결과입니다. 로컬 AI 가 연습 도면 30장 중 27장에서 부품 모양을 맞혔습니다. 90 % 입니다. 원뿔, "
        "프레스 성형, 절곡판은 여섯 장 모두 맞혔고, 평판은 다섯 장, 원통은 네 장을 맞혔습니다. 동료가 "
        "10월 18일에 돌린 결과입니다. 여기까지가 지금 우리 위치입니다. 쉬운 시험지에서는 로컬 AI 로도 "
        "꽤 된다는 것을 확인했습니다.",
    )
    road(s, 1)
    card(
        s,
        X0,
        1.85,
        3.5,
        4.65,
        [
            {"text": "27", "bold": True, "size": 96, "color": ORANGE},
            {"text": "/ 30 장", "bold": True, "size": 26},
            {"text": "부품 모양 맞힘 · 90 %", "size": 16, "color": GRAY},
        ],
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=2,
    )
    bar_chart(
        s,
        X0 + 3.8,
        1.85,
        CW - 3.8,
        4.1,
        [name for name, _ in SHAPES],
        [n for _, n in SHAPES],
        [TEAL if n == 6 else ORANGE for _, n in SHAPES],
        number_format='0" / 6"',
        label_size=16,
        gap=45,
    )
    text(
        s,
        X0 + 3.8,
        6.05,
        CW - 3.8,
        0.4,
        ["모양마다 6장 · 로컬 AI (DeepSeek-OCR-2 + Qwen3.6-27B) · 2026-10-18"],
        size=13,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )


def title_slide(d: Deck):
    s = d.slide(
        "이번 파트에서는 이 프로젝트가 지금 어디까지 와 있는지를 말씀드리겠습니다. 처음에는 Claude 라는 "
        "AI 에게 일을 통째로 맡겨 봤고(v2), 그다음에는 우리 서버의 AI 로 도면 읽기에만 집중했습니다(v3). "
        "그리고 그 v3 를 실제 회사 도면에 돌려 보니 무엇이 되고 무엇이 안 됐는지 자세히 보겠습니다.",
        dark=True,
    )
    text(
        s,
        X0,
        1.9,
        CW,
        1.6,
        ["도면 판독,", "지금 어디까지 왔나"],
        size=40,
        bold=True,
        color=WHITE,
        after=4,
    )
    text(
        s,
        X0,
        3.75,
        CW,
        0.5,
        ["v2 → v3 → 실제 도면에 돌려 보니"],
        size=20,
        color=ORANGE,
    )
    w, gap = 3.3, 0.6
    for i, label in enumerate(ROAD):
        x = X0 + i * (w + gap)
        chip(
            s,
            x,
            5.0,
            w,
            0.55,
            label,
            fill=ORANGE if i == len(ROAD) - 1 else "34444C",
            color=WHITE,
            size=16,
            bold=True,
        )
        if i < len(ROAD) - 1:
            arrow(s, x + w + 0.15, 5.12, 0.3, 0.3, fill="5F6B73")
    text(
        s,
        X0,
        6.4,
        CW,
        0.4,
        ["PBL cutplan_agent · 2026-10-24"],
        size=14,
        color="B8C4C9",
    )


def map_slide(d: Deck):
    s = d.content(
        "전체 지도: 도면에서 구매의뢰까지",
        "회사 일 네 단계 중 AI 가 어디까지 맡았나",
        "먼저 전체 지도입니다. 회사에서 하는 일은 네 단계입니다. 도면을 읽어 부품의 모양과 치수, 재질을 "
        "알아내고, 부품을 평평하게 펼친 전개도를 그리고, 전개도 조각들을 철판 위에 배치하는 커팅플랜을 "
        "짜고, 필요한 철판을 주문하는 구매의뢰서를 씁니다. v2 에서는 이 네 단계를 전부 AI 에게 맡겼는데 "
        "잘 안 됐습니다. v3 에서는 앞의 두 단계, 그중에서도 도면 읽기에 집중했고, 연습용 도면에서는 꽤 "
        "좋은 결과를 얻었습니다. 그런데 같은 v3 를 실제 회사 도면에 돌려 보니 결과가 많이 달랐습니다. "
        "지금 우리는 여기에 있습니다.",
    )
    road(s, 2)
    lw, gap = 1.55, 0.3
    cx = X0 + lw + 0.15
    cw = (CW - lw - 0.15 - 3 * gap) / 4
    steps = [
        ("① 도면 읽기", "모양 · 치수 · 재질"),
        ("② 전개도", "펼친 모양 계산"),
        ("③ 커팅플랜", "철판 위에 배치"),
        ("④ 구매의뢰", "철판 주문서"),
    ]
    for i, (head, sub) in enumerate(steps):
        x = cx + i * (cw + gap)
        box = card(
            s,
            x,
            1.85,
            cw,
            1.0,
            [
                {"text": head, "bold": True, "size": 19},
                {"text": sub, "size": 14, "color": GRAY},
            ],
            fill=WHITE,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
        box.line.color.rgb = rgb(PALE)
        if i < 3:
            arrow(s, x + cw + 0.04, 2.2, 0.22, 0.3)
    rows = [
        ("v2", "Claude", 4, LIGHT, GRAY, "AI 에게 전부 맡김 → 잘 안 됨", CROSS),
        ("v3", "연습 도면", 2, TEAL, WHITE, "도면 읽기 → 27 / 30", CHECK),
        ("v3", "실제 도면", 2, ORANGE_TINT, ORANGE, "부품 22종 중 1개", CROSS),
    ]
    for r, (name, who, span, fill, color, label, mark) in enumerate(rows):
        y = 3.15 + r * 1.12
        text(
            s,
            X0,
            y,
            lw,
            0.85,
            [
                {"text": name, "bold": True, "size": 20},
                {"text": who, "size": 13, "color": GRAY},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            after=0,
        )
        bw = span * cw + (span - 1) * gap
        card(
            s,
            cx,
            y + 0.08,
            bw,
            0.7,
            [{"text": label, "bold": True}],
            fill=fill,
            color=color,
            size=17,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.25,
        )
        badge(
            s,
            cx + bw - 0.62,
            y + 0.16,
            0.54,
            mark,
            WHITE if mark == CHECK else ("AAB6BB" if r == 0 else ORANGE),
            color=TEAL if mark == CHECK else WHITE,
            size=18,
        )
        if r == 2:
            chip(
                s,
                cx + bw + 0.25,
                y + 0.16,
                1.75,
                0.54,
                "◀ 지금 여기",
                fill=ORANGE,
                color=WHITE,
                size=16,
                bold=True,
            )


def real_overview_slide(d: Deck):
    s = d.content(
        "실제 도면 5장을 넣어 봤다",
        "같은 v3, 같은 로컬 AI 로 회사 설비 두 개의 도면을 읽혔다 (2026-10-23)",
        "이제 같은 v3 를 실제 회사 도면에 돌려 본 결과입니다. 회사에서 받은 설비 S-2120 의 도면 4장과, "
        "다른 워크오더 KD23009 의 본체 상세도 1장입니다. 서버도, AI 도, 13단계도 연습 도면 때와 "
        "똑같습니다. 같은 도면을 두 번 돌려 단계별 결과가 같은 것도 확인했습니다. 한 줄이 도면 한 장이고, 칸이 "
        "13단계입니다. 청록은 그 단계가 끝까지 돌았다는 뜻, "
        "회색은 앞 단계 때문에 건너뛰었다는 뜻, 주황은 오류로 멈췄다는 뜻입니다. 끝까지 돈 것은 조립도 "
        "한 장뿐이고, 두 장은 중간에 멈췄습니다. 그리고 끝까지 돌았다고 맞았다는 뜻은 아닙니다. "
        "오른쪽이 실제로 나온 결과인데, 다음 장부터 하나씩 보겠습니다.",
    )
    road(s, 2)
    lx, lw = X0, 3.15
    gx = X0 + 3.3
    cw, cg = 0.42, 0.06
    rx = gx + 13 * (cw + cg) + 0.15
    rw = X0 + CW - rx
    for i, (num, _, model) in enumerate(STAGES):
        x = gx + i * (cw + cg)
        text(
            s,
            x - 0.05,
            1.85,
            cw + 0.1,
            0.3,
            [num],
            size=11,
            bold=model,
            color=ORANGE if model else GRAY,
            align=PP_ALIGN.CENTER,
        )
    text(s, rx, 1.85, rw, 0.3, ["나온 결과"], size=12, bold=True, color=GRAY)
    fills = {"d": TEAL, "s": PALE, "f": ORANGE}
    for r, (name, kind, marks, result) in enumerate(REAL):
        y = 2.3 + r * 0.8
        text(
            s,
            lx,
            y,
            lw,
            0.62,
            [
                {"text": kind, "bold": True, "size": 15},
                {"text": name, "size": 11, "color": GRAY},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            after=0,
        )
        for i, m in enumerate(marks):
            box = shape(
                s,
                MSO_SHAPE.ROUNDED_RECTANGLE,
                gx + i * (cw + cg),
                y + 0.08,
                cw,
                0.46,
                fills[m],
                radius=0.15,
            )
            if m == "f":
                write(
                    box.text_frame,
                    [{"text": CROSS, "bold": True}],
                    size=13,
                    color=WHITE,
                    align=PP_ALIGN.CENTER,
                    anchor=MSO_ANCHOR.MIDDLE,
                    margin=0,
                )
        text(
            s,
            rx,
            y,
            rw,
            0.62,
            [result],
            size=13,
            bold=True,
            color=ORANGE if "틀림" in result or "멈춤" in result else INK,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    legend = [(TEAL, "끝까지 돌았다"), (PALE, "건너뜀"), (ORANGE, "오류로 멈춤")]
    x = gx
    for fill, label in legend:
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 6.4, 0.3, 0.3, fill, radius=0.15)
        text(s, x + 0.38, 6.36, 1.6, 0.36, [label], size=12, color=GRAY)
        x += 1.9
    text(
        s,
        X0,
        6.36,
        3.1,
        0.36,
        ["주황 번호 = AI 에게 묻는 단계"],
        size=12,
        color=ORANGE,
    )


def real_score_slide(d: Deck):
    s = d.content(
        "정답과 비교: 부품 22종 중 1개",
        "v3 는 도면 한 장에 답을 하나만 낸다. 상세도 한 장에는 부품이 4~13종",
        "S-2120 은 회사가 짠 커팅플랜이 있어서 정답과 비교할 수 있습니다. 정답 커팅플랜에는 서로 다른 "
        "부품이 22종 나옵니다. 본체 상세도에 13종, 맨홀 상세도에 4종, 노즐 상세도에 5종입니다. 조립도는 "
        "전체 모습을 보여 주는 도면이라 부품 치수는 상세도에 있습니다. 그런데 v3 는 도면 한 장에 부품 "
        "하나가 있다고 가정하고 만들어져서, 한 장에 답을 하나만 냅니다. 그래서 상세도 세 장에서는 부품을 "
        "하나도 내지 못했고, 조립도에서 몸통 원통 하나를 냈습니다. 22종 중 1개이고, 그 1개도 다음에 "
        "보겠지만 두께가 틀렸습니다.",
    )
    road(s, 2)
    card(
        s,
        X0,
        1.85,
        3.6,
        4.7,
        [
            {"text": "정답 부품", "size": 16, "color": GRAY},
            {"text": "22 종", "bold": True, "size": 54, "color": INK},
            {"text": "v3 가 낸 부품", "size": 16, "color": GRAY},
            {"text": "1 개", "bold": True, "size": 54, "color": ORANGE},
            {"text": "설비 S-2120", "size": 13, "color": GRAY},
        ],
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=4,
    )
    lx = X0 + 4.0
    labw = 2.0
    bx = lx + labw + 0.2
    unit = (X0 + CW - bx - 0.9) / 13
    for i, (kind, answer, ours) in enumerate(SCORE):
        y = 2.0 + i * 1.12
        text(
            s,
            lx,
            y,
            labw,
            0.85,
            [kind],
            size=17,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
            align=PP_ALIGN.RIGHT,
        )
        for j, (n, fill, label) in enumerate(
            [(answer, PALE, "정답"), (ours, ORANGE, "v3")]
        ):
            yy = y + 0.05 + j * 0.42
            w = max(n * unit, 0.04)
            shape(s, MSO_SHAPE.RECTANGLE, bx, yy, w, 0.34, fill)
            text(
                s,
                bx + w + 0.1,
                yy - 0.03,
                1.6,
                0.4,
                [f"{label} {n}"],
                size=13,
                bold=j == 1,
                color=ORANGE if j else GRAY,
            )
    text(
        s,
        lx,
        6.45,
        X0 + CW - lx,
        0.35,
        [
            "조립도에는 부품 치수가 없다 (상세도에 있다). v3 는 조립도에서 몸통 원통을 읽었다"
        ],
        size=12,
        color=GRAY,
    )


def real_success_slide(d: Deck):
    s = d.content(
        "잘 된 것",
        "AI 와 프로그램이 각자 맞게 한 일도 많았다",
        "실패만 있었던 건 아닙니다. 잘 된 것부터 보겠습니다. 첫째, S-2120 네 장 모두 AI 가 도면 번호와 "
        "도면 이름을 맞게 읽었습니다. 둘째, 노즐 상세도를 보고 AI 가 '여러 노즐의 "
        "상세 뷰와 부품표가 있는 도면이라, 3D 로 복원할 부품 하나가 없다'고 판단했습니다. 맞는 판단입니다. "
        "셋째, 조립도의 몸통을 원통으로 보고 안지름 1500 을 정답대로 읽었습니다. 넷째, 글자 받아쓰기 "
        "AI 는 KD23009 의 부품표에서 'SHELL A240-304 t8' 을 그대로 받아썼습니다. 다섯째, 프로그램은 "
        "표제란에서 재질 글자를 다섯 장 모두, 축척을 네 장에서 찾았습니다.",
    )
    road(s, 2)
    items = [
        (
            "AI",
            "도면 번호 · 이름",
            "S-2120 4장 모두 맞게 읽음 (조립도 · 본체 · 맨홀 · 노즐 상세도)",
        ),
        (
            "AI",
            "“부품 하나짜리 도면이 아니다”",
            "노즐 상세도: 여러 노즐의 상세 뷰와 부품표 → 부품 하나로 복원할 수 없다",
        ),
        (
            "AI",
            "원통 모양 · 안지름 1500",
            "조립도의 몸통을 원통으로, 안지름은 정답대로",
        ),
        ("OCR", "부품표 받아쓰기", "KD23009 부품표의 ‘SHELL  A240-304  t8’ 을 그대로"),
        (
            "프로그램",
            "재질 · 축척 글자",
            "표제란에서 재질 5장, 축척 4장을 규칙(정규식)으로 찾음",
        ),
    ]
    for i, (who, head, body) in enumerate(items):
        y = 1.85 + i * 0.95
        box = card(
            s,
            X0,
            y,
            CW,
            0.82,
            [
                [
                    {"text": head + "   ", "bold": True, "size": 18},
                    {"text": body, "size": 15, "color": GRAY},
                ]
            ],
            fill=TEAL_TINT if who != "프로그램" else LIGHT,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
        )
        box.text_frame.margin_left = Inches(2.15)
        badge(s, X0 + 0.15, y + 0.15, 0.52, CHECK, TEAL, size=17)
        chip(
            s,
            X0 + 0.8,
            y + 0.2,
            1.15,
            0.42,
            who,
            fill=INK if who != "프로그램" else WHITE,
            color=WHITE if who != "프로그램" else INK,
            size=12,
            bold=True,
        )


def real_fail_ai_slide(d: Deck):
    s = d.content(
        "실패 1: t8 을 18 로 — 두 설비에서 똑같이",
        "글자는 도면 파일에 정확히 있었다. AI 는 줄인 그림을 보고 읽었다",
        "가장 아픈 실패입니다. 두 설비 모두 몸통 두께를 18 로 읽었는데, 정답은 둘 다 8 입니다. S-2120 "
        "조립도 파일 안에는 'USED TH'K : t8' 이라는 글자가 그대로 있고, KD23009 는 부품표에 't8' 이 있고 "
        "글자 받아쓰기 AI 도 t8 로 받아썼습니다. 그런데 치수를 고르는 AI 는 '정면도에 t=18', '부품표에 "
        "t18' 이라고 근거까지 대며 틀렸습니다. 이유를 보니, 이 단계는 AI 에게 도면 전체를 가로 2160 픽셀로 "
        "줄인 그림과 뷰마다 치수 스무 개만 줍니다. 't8' 같은 표 안의 글자는 넘겨주지 않습니다. 큰 도면을 "
        "줄인 그림에서 작은 글자를 읽다가 t 와 8 을 18 로 본 것입니다. 두께가 틀리면 다른 철판을 사게 되고, "
        "펼친 크기도 틀립니다. 그리고 KD23009 에서는 같은 AI 가 앞 단계 표제란에서 두께를 8 로 맞게 읽었는데, "
        "그 답은 검사에서 버려졌습니다. 다음 장에서 보겠습니다.",
    )
    road(s, 2)
    rows = [
        ["", "AI 가 읽은 두께", "도면 파일 안의 글자", "AI 가 댄 근거"],
        ["S-2120 조립도", "18", "USED TH'K : t8", "“정면도에 t=18”"],
        ["KD23009 상세도", "18", "SHELL  A240-304  t8", "“부품표에 t18”"],
    ]

    def style(r, c):
        if r == 0:
            return INK, WHITE, True, 14, PP_ALIGN.CENTER
        return (
            LIGHT if r % 2 else WHITE,
            ORANGE if c == 1 else INK,
            c in (0, 1),
            22 if c == 1 else 15,
            PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER,
        )

    table(s, X0, 1.85, CW, 1.65, rows, [2.6, 2.2, 3.8, CW - 8.6], style)
    # what the model was given
    y = 3.85
    real_sheet(s, X0, y, 2.6, 1.8)
    text(
        s,
        X0,
        y + 1.85,
        2.6,
        0.35,
        ["도면 파일: ‘t8’ 이 글자 그대로"],
        size=11,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, X0 + 2.75, y + 0.72, 0.45, 0.36)
    text(
        s,
        X0 + 2.5,
        y + 1.1,
        1.0,
        0.5,
        ["줄여서"],
        size=11,
        color=ORANGE,
        align=PP_ALIGN.CENTER,
    )
    real_sheet(s, X0 + 3.4, y + 0.45, 1.3, 0.9)
    text(
        s,
        X0 + 3.1,
        y + 1.45,
        1.9,
        0.6,
        ["AI 가 받은 것: 줄인 그림 + 치수 20개"],
        size=11,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, X0 + 4.9, y + 0.72, 0.45, 0.36)
    circle(s, X0 + 5.5, y + 0.3, 1.2, "“18”", fill=ORANGE, size=22)
    dashed(
        card(
            s,
            X0 + 7.0,
            y,
            CW - 7.0,
            2.2,
            [
                {
                    "text": "펼친 크기도 틀렸다",
                    "bold": True,
                    "size": 17,
                    "color": ORANGE,
                },
                {"text": "S-2120: 4,769 mm  (정답 4,738, t8)", "size": 15},
                {"text": "KD23009: 1,910 × 2,300", "size": 15},
                {
                    "text": "    (정답 조각 1,500 + 620 × 1,880, t8)",
                    "size": 13,
                    "color": GRAY,
                },
                {
                    "text": "두께가 틀리면 다른 철판을 사게 된다",
                    "size": 15,
                    "bold": True,
                },
            ],
            fill=ORANGE_TINT,
            margin=0.25,
            after=3,
        )
    )


def real_fail_program_slide(d: Deck):
    s = d.content(
        "실패 2: 연습 도면에 맞춘 규칙이 깨졌다",
        "프로그램 쪽 실패 — 실제 도면의 배치를 예상하지 못했다",
        "두 번째 종류는 프로그램 쪽 실패입니다. 연습 도면은 한가운데 뷰 세 개, 오른쪽 아래 표제란 하나로 "
        "깔끔합니다. 실제 도면은 다릅니다. 본체 상세도에서는 뷰 나누기 단계가 도면 전체를 표로 보고 지워 "
        "버려서 뷰가 0개가 됐습니다. 노즐 상세도는 AI 가 상세 뷰뿐이라고 맞게 봤는데, 다음 단계가 정면, "
        "평면, 측면 뷰가 꼭 있어야 하는 코드라 거기서 멈췄습니다. KD23009 에서는 AI 가 표제란에서 도면 "
        "번호, 재질에 두께 8 까지 맞게 읽었는데, 축척 칸에 'NONE' 이라고 써서 형식 검사에 걸렸고, 검사가 "
        "그 칸만이 아니라 답 전체를 버렸습니다. 맞게 읽은 두께 8 도 함께 버려진 것입니다. 3D 복원은 돌아간 "
        "세 장 모두 쓸 만한 후보가 없었습니다.",
    )
    road(s, 2)
    rows = [
        (
            "05 뷰 나누기",
            "도면 전체를 ‘표’ 로 보고 지웠다 → 뷰 0개",
            "본체 상세도",
        ),
        (
            "08 3D 용 정리",
            "정면 · 평면 · 측면 뷰가 없으면 멈춘다. 상세도에는 상세 뷰뿐 (AI 는 맞게 봤다)",
            "노즐 · 본체 상세도",
        ),
        (
            "04 답 검사",
            "축척 칸 하나(‘NONE’)가 형식에 안 맞아 답 전체를 버렸다 — 맞게 읽은 두께 8 까지",
            "KD23009",
        ),
        (
            "11 3D 후보",
            "쓸 만한 후보 0개, 또는 뷰가 하나뿐이라 실패",
            "돌아간 3장 모두",
        ),
    ]
    for i, (stage, what, where) in enumerate(rows):
        y = 1.9 + i * 1.12
        chip(
            s, X0, y + 0.12, 2.3, 0.7, stage, fill=INK, color=WHITE, size=15, bold=True
        )
        card(
            s,
            X0 + 2.5,
            y,
            CW - 2.5,
            0.95,
            [
                [
                    {"text": what, "size": 16},
                ],
                {"text": where, "size": 13, "color": ORANGE, "bold": True},
            ],
            fill=LIGHT,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.25,
            after=2,
        )
    text(
        s,
        X0,
        6.45,
        CW,
        0.35,
        [
            "연습 도면: 가운데 뷰 3개, 오른쪽 아래 표제란 하나 — 규칙이 이 모양에 맞춰져 있다"
        ],
        size=12,
        color=GRAY,
    )


def real_lessons_slide(d: Deck):
    s = d.content(
        "실제 도면이 드러낸 것",
        "연습 도면에서는 보이지 않던 세 종류의 문제",
        "정리하면 실제 도면은 세 종류의 문제를 드러냈습니다. 첫째, AI 의 읽기입니다. 작은 글자를 줄인 "
        "그림에서 읽다가 t8 을 18 로 봤습니다. 둘째, 프로그램의 규칙입니다. 뷰 나누기, 정면과 평면이 꼭 "
        "있다는 전제, 한 칸만 틀려도 답 전체를 버리는 검사, 3D 복원이 실제 도면에서 깨졌습니다. 셋째, 설계 전제입니다. 도면 "
        "한 장에 부품 하나라는 가정 때문에 상세도의 부품 22종 중 1개만 나왔습니다. 그리고 하나 더, AI "
        "가 노즐 상세도를 맞게 판단하고 KD23009 의 두께를 8 로 맞게 읽었는데도, 고정된 다음 단계와 검사가 "
        "그것을 받아 주지 못했습니다. 연습 "
        "도면 30장에서는 이 셋이 하나도 보이지 않았습니다.",
    )
    road(s, 2)
    cols = [
        ("AI 의 읽기", "t8 → 18", "2번", "작은 글자를 줄인 그림에서 읽었다"),
        (
            "프로그램 규칙",
            "4곳",
            "단계",
            "뷰 나누기 · 정면/평면 전제 · 답 전체를 버리는 검사 · 3D 복원",
        ),
        ("설계 전제", "22 → 1", "부품", "‘도면 한 장 = 부품 하나’"),
    ]
    w, gap = 3.85, 0.29
    for i, (head, big, unit, body) in enumerate(cols):
        x = X0 + i * (w + gap)
        card(
            s,
            x,
            1.95,
            w,
            2.95,
            [
                {"text": head, "bold": True, "size": 22, "color": TEAL},
                [
                    {"text": big, "bold": True, "size": 40, "color": ORANGE},
                    {"text": "  " + unit, "size": 15, "color": GRAY},
                ],
                {"text": body, "size": 16},
            ],
            margin=0.3,
            after=10,
        )
    band(
        s,
        5.25,
        "그리고",
        "AI 가 맞게 판단하고 읽어도 (노즐 상세도, KD23009 두께 8) 다음 단계와 검사가 받아 주지 못했다",
    )


def closing_slide(d: Deck):
    s = d.slide(
        "정리하겠습니다. v2 에서는 Claude 에게 도면부터 구매의뢰까지 전부 맡겼는데, 일이 너무 커서 잘 "
        "안 됐습니다. v3 에서는 우리 서버의 로컬 AI 로 도면 읽기에 집중했고, 연습 도면 30장 중 27장을 "
        "맞혔습니다. 그런데 실제 도면에서는 부품 22종 중 1개, 그것도 두께가 틀렸습니다. 원인은 AI 의 "
        "읽기, 프로그램의 규칙, 설계 전제 세 가지였습니다. 그래서 무엇을 할지는 다음 파트에서 "
        "말씀드리겠습니다. 질문 받겠습니다.",
        dark=True,
    )
    text(s, X0, 0.8, CW, 0.8, ["정리"], size=36, bold=True, color=WHITE)
    points = [
        ("v2", "Claude 에게 전부 맡겼다 → 일이 너무 컸다"),
        ("v3", "로컬 AI, 도면 읽기에 집중 → 연습 도면 27 / 30"),
        ("실제 도면", "부품 22종 중 1개, 두께 t8 → 18"),
        ("원인", "AI 의 읽기 · 프로그램 규칙 · ‘한 장 = 부품 하나’"),
    ]
    for i, (label, point) in enumerate(points):
        y = 1.9 + i * 1.05
        chip(
            s,
            X0,
            y + 0.05,
            1.7,
            0.6,
            label,
            fill=ORANGE if label == "실제 도면" else "34444C",
            color=WHITE,
            size=17,
            bold=True,
        )
        text(
            s,
            X0 + 2.0,
            y,
            CW - 2.0,
            0.7,
            [point],
            size=22,
            color=WHITE,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    text(
        s,
        X0,
        6.3,
        CW,
        0.6,
        ["다음 파트: 그래서 무엇을 하나 · 질문"],
        size=24,
        bold=True,
        color=ORANGE,
    )


def main() -> None:
    cone = render_cone()
    d = Deck(OUT, TITLE, FOOTER)
    title_slide(d)
    map_slide(d)
    v2_slide(d)
    skill_slide(d)
    claude_loop_slide(d)
    v2_result_slide(d)
    why_move_slide(d)
    v3_shift_slide(d)
    server_slide(d)
    stages_slide(d)
    synthetic_slide(d, cone)
    result_slide(d)
    real_overview_slide(d)
    real_score_slide(d)
    real_success_slide(d)
    real_fail_ai_slide(d)
    real_fail_program_slide(d)
    real_lessons_slide(d)
    closing_slide(d)
    print(f"{d.count} slides -> {d.save()}")


if __name__ == "__main__":
    main()
