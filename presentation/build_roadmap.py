"""Build presentation/roadmap.pptx: what comes next, for listeners who are new to AI.

PYTHONPATH=. uv run --with python-pptx python presentation/build_roadmap.py

Follows presentation/build_v2_v3.py (how the project got here and how v3 did on real
drawings); the two parts do not repeat each other. The story: the two jobs ahead (harness
engineering, real drawings); tool calling, the way Claude used the skills in v2; the agent
prototype where a local model instead of Claude picks the reader stages as tools, what it
recorded, and the two ways a model can call tools; how tools could fix the real-drawing
failures; next week's work; the steps to the final goal. Few words on the slides, the
narration is in the notes.

Where every number comes from: docs/presentation.md 6절.
"""

from pathlib import Path

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches

from presentation.slides import (
    CHECK,
    CW,
    GRAY,
    INK,
    LIGHT,
    MONO,
    ORANGE,
    ORANGE_TINT,
    PALE,
    PART,
    TEAL,
    TEAL_TINT,
    WHITE,
    X0,
    Deck,
    W,
    arrow,
    badge,
    band,
    card,
    chip,
    circle,
    connect,
    dashed,
    real_sheet,
    rgb,
    shape,
    table,
    text,
)
from presentation.slides import road as _road

OUT = Path(__file__).with_name("roadmap.pptx")
TITLE = "다음 단계: 로컬 AI 가 도구를 골라 쓰게"
FOOTER = "PBL cutplan_agent · 다음 단계 · 2026-10-24"
ROAD = ["할 일", "시제품", "다음 주", "최종"]


def road(s, here: int):
    _road(s, here, ROAD, w=0.95)


# ---------------------------------------------------------------------- slides
def title_slide(d: Deck):
    s = d.slide(
        "앞 파트에서 지금 어디까지 왔는지를 봤습니다. 이번 파트는 그래서 무엇을 하느냐입니다. 로컬 AI 가 "
        "도구를 골라 쓰는 에이전트 시제품을 만들어 돌려 봤고, 그걸 바탕으로 다음 주에 할 일과 최종 "
        "목표까지 가는 길을 말씀드리겠습니다.",
        dark=True,
    )
    text(
        s,
        X0,
        1.9,
        CW,
        1.6,
        ["다음 단계:", "로컬 AI 가 도구를 골라 쓰게"],
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
        ["에이전트 시제품 → 다음 주 → 최종 목표"],
        size=20,
        color=ORANGE,
    )
    w, gap = 2.4, 0.6
    for i, label in enumerate(ROAD):
        x = X0 + i * (w + gap)
        chip(s, x, 5.0, w, 0.55, label, fill="34444C", color=WHITE, size=16, bold=True)
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


def next_overview_slide(d: Deck):
    s = d.content(
        "다음 할 일 두 가지",
        "AI 를 제대로 쓰는 틀을 만들고, 실제 도면으로 간다",
        "그럼 이제 무엇을 할까요. 두 가지입니다. 첫째, 이 수업의 취지대로 AI 를 제대로 써야 합니다. 지금은 "
        "코드가 정해진 곳에서 AI 를 부르는 수준인데, 실제로 AI 를 쓰듯이 AI 가 일하고 그 주변을 받쳐 "
        "주는 틀, 하네스를 만드는 것입니다. 둘째, 연습 도면에서는 되지만 실제 도면에서는 성능이 "
        "떨어집니다. 이걸 끌어올려야 합니다. 그 열쇠가 tool calling 입니다. 그리고 이 둘은 결국 하나로 "
        "이어집니다.",
    )
    road(s, 0)
    items = [
        (
            "1",
            "AI 를 진짜 AI 처럼",
            "하네스 엔지니어링",
            "코드 속 부품 → AI 가 일하고, 하네스가 받친다",
        ),
        (
            "2",
            "실제 도면에서 성능 올리기",
            "tool calling 설계",
            "연습 도면 → 실제 회사 도면",
        ),
    ]
    w = (CW - 0.4) / 2
    for i, (num, head, kind, sub) in enumerate(items):
        x = X0 + i * (w + 0.4)
        card(
            s,
            x,
            1.95,
            w,
            3.45,
            [
                {"text": head, "bold": True, "size": 26},
                {"text": kind, "bold": True, "size": 20, "color": ORANGE},
                {"text": sub, "size": 16, "color": GRAY},
            ],
            margin=0.4,
            after=10,
        ).text_frame.margin_top = Inches(1.35)
        circle(s, x + 0.4, 2.3, 0.85, num, size=26)
    band(s, 5.7, "둘은 이어진다", "좋은 도구 + AI 가 골라 쓰기 + 받쳐 주는 하네스")


def harness_slide(d: Deck):
    s = d.content(
        "할 일 1: 하네스 엔지니어링",
        "AI 를 코드 속 부품으로 부르는 대신, AI 가 일하고 하네스가 받친다",
        "하네스는 원래 말에 채우는 마구를 말합니다. 힘센 말이 원하는 방향으로 일하게 해 주는 장치죠. AI "
        "도 마찬가지입니다. 작은 로컬 AI 라도 일을 잘게 나눠 주고, 답하는 양식을 정해 주고, 답을 검사하고, "
        "모든 걸 기록하고, 점수를 매기면 쓸 만한 결과를 낼 수 있다는 것, 이것이 이 프로젝트가 보이려는 "
        "가설입니다. 아직 증명된 것은 아니고, 연습 도면 27/30 이 첫 근거입니다. 지금 "
        "상태를 표시했습니다. 일 나누기, 답 양식, 기록은 됐습니다. 판독을 13단계로 나눠 단계마다 파일을 "
        "남기고, 단계별로 돌리고 표와 그림으로 보는 도구도 만들었습니다. 평가와 검사는 일부만 있고, AI 가 "
        "순서를 직접 정하는 것은 시제품을 만들었습니다. 다음 장에서 보여 드리겠습니다.",
    )
    road(s, 0)
    card(
        s,
        X0,
        1.85,
        4.0,
        2.0,
        [
            {"text": "하네스 (harness)", "bold": True, "size": 20, "color": TEAL},
            {"text": "말에 채우는 마구.", "size": 16},
            {"text": "원하는 쪽으로 일하게 한다", "size": 16},
        ],
        fill=TEAL_TINT,
        margin=0.3,
        after=4,
    )
    card(
        s,
        X0,
        4.05,
        4.0,
        2.5,
        [
            {"text": "보이려는 것 (가설)", "bold": True, "size": 20, "color": ORANGE},
            {"text": "작은 로컬 AI 라도", "size": 17},
            {"text": "하네스를 잘 만들면", "size": 17},
            {"text": "쓸 만한 결과를 낸다", "size": 17, "bold": True},
        ],
        fill=ORANGE_TINT,
        margin=0.3,
        after=4,
    )
    parts = [
        ("일 나누기", "13단계, 단계마다 파일", CHECK),
        ("답 양식", "정해진 양식으로만 답", CHECK),
        ("기록", "모든 질문과 답을 저장", CHECK),
        ("평가", "연습 30장, 최종 결과만", PART),
        ("검사 · 다시 묻기", "다시 묻기는 아직", PART),
        ("AI 가 순서 정하기", "시제품", PART),
    ]
    bw, bh = 3.0, 1.02
    lx, rx = X0 + 4.35, W - X0 - bw
    dd = 1.5
    cx = (lx + bw + rx) / 2 - dd / 2
    cy = 1.95 + 1.55 + bh / 2 - dd / 2
    for i, (head, sub, mark) in enumerate(parts):
        c, r = divmod(i, 3)
        x = lx if c == 0 else rx
        y = 1.95 + r * 1.55
        connect(s, x + (bw if c == 0 else 0), y + bh / 2, cx + dd / 2, cy + dd / 2)
        done = mark == CHECK
        card(
            s,
            x,
            y,
            bw,
            bh,
            [
                {"text": head, "bold": True, "size": 16},
                {"text": sub, "size": 12, "color": GRAY},
            ],
            fill=TEAL_TINT if done else ORANGE_TINT,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.15,
            after=1,
        ).text_frame.margin_left = Inches(0.65)
        badge(
            s,
            x + 0.12,
            y + bh / 2 - 0.22,
            0.44,
            mark,
            TEAL if done else ORANGE,
            size=15,
        )
    circle(s, cx, cy, dd, "AI", fill=INK, size=28)
    text(
        s,
        lx,
        6.5,
        W - X0 - lx,
        0.35,
        [f"{CHECK} 됨   {PART} 일부 · 시제품"],
        size=12,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )


def toolcall_slide(d: Deck):
    s = d.content(
        "tool calling: v2 에서 본 그 방식",
        "AI 는 도구 목록을 보고 '이걸 이렇게 불러 줘'라고 요청만 한다. 실행은 프로그램",
        "열쇠는 tool calling 입니다. 사실 이미 보셨습니다. v2 에서 Claude 가 메뉴판을 보고 skill 을 "
        "주문하던 방식, 그게 tool calling 입니다. 프로그램이 도구 목록을 주고, AI 가 하나를 골라 요청하고, "
        "프로그램이 실행해서 결과를 돌려주고, AI 가 다음 도구를 고릅니다. 중요한 점은 AI 는 고르기만 "
        "하고 실행은 늘 프로그램이 한다는 것입니다. 그래서 계산은 언제나 정확합니다. v3 에서는 이걸 "
        "쓰지 않고 순서를 코드에 고정했는데, 이제 로컬 AI 로 이 방식을 다시 가져옵니다. 시제품에서 로컬 "
        "AI 가 도구를 골라 부르는 것까지 확인했습니다. 다만 시제품은 AI 의 답을 '도구 이름과 값' 양식으로만 "
        "나오게 강제하는 방식이었고, 서버의 표준 tool calling 기능은 서버 설정을 바꾼 뒤 확인할 "
        "예정입니다. 두 방식 중 어느 쪽이 작은 AI 에게 나은지도 재 볼 거리입니다.",
    )
    road(s, 1)
    loop = [
        ("1", "도구 목록을 준다", "이름 · 설명 · 입력 양식", TEAL),
        ("2", "AI 가 고른다", "“이 도구를 이 값으로”", INK),
        ("3", "프로그램이 실행", "계산은 언제나 정확하게", TEAL),
        ("4", "결과를 돌려준다", "→ 다시 2 로", TEAL),
    ]
    bw, bh, bg = 3.3, 1.45, 0.7
    pos = [(X0, 1.9), (X0 + bw + bg, 1.9), (X0 + bw + bg, 4.0), (X0, 4.0)]
    for (num, head, sub, color), (x, y) in zip(loop, pos):
        card(
            s,
            x,
            y,
            bw,
            bh,
            [
                {"text": head, "bold": True, "size": 18},
                {"text": sub, "size": 14, "color": GRAY},
            ],
            fill=LIGHT if color == TEAL else ORANGE_TINT,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
            after=3,
        ).text_frame.margin_left = Inches(0.95)
        circle(s, x + 0.2, y + bh / 2 - 0.3, 0.6, num, fill=color, size=16)
    arrow(s, X0 + bw + 0.17, 2.45, 0.36, 0.36)
    arrow(s, X0 + bw + bg + bw / 2 - 0.18, 3.43, 0.36, 0.5, kind=MSO_SHAPE.DOWN_ARROW)
    arrow(s, X0 + bw + 0.17, 4.55, 0.36, 0.36, kind=MSO_SHAPE.LEFT_ARROW)
    arrow(s, X0 + bw / 2 - 0.18, 3.43, 0.36, 0.5, kind=MSO_SHAPE.UP_ARROW)
    rx = X0 + 2 * bw + bg + 0.35
    rw = CW - (rx - X0)
    history = [
        ("v2", "Claude 가 skill 25개를 tool calling 으로", LIGHT, GRAY),
        ("v3", "순서를 코드에 고정 — tool calling 없음", LIGHT, GRAY),
        (
            "다음",
            "로컬 AI 가 도구를 고른다 (시제품)",
            ORANGE_TINT,
            ORANGE,
        ),
    ]
    for i, (name, body, fill, color) in enumerate(history):
        card(
            s,
            rx,
            1.9 + i * 1.22,
            rw,
            1.05,
            [
                {"text": name, "bold": True, "size": 18, "color": color},
                {"text": body, "size": 15},
            ],
            fill=fill,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
            after=2,
        )
    text(
        s,
        rx,
        5.6,
        rw,
        0.8,
        [
            {"text": "AI 는 실행하지 않는다. 고르기만 한다", "bold": True},
            {
                "text": "시제품은 답 양식을 강제하는 방식 (structured outputs). "
                "표준 tool calling 은 서버 설정 후 확인",
                "size": 12,
                "color": GRAY,
            },
        ],
        size=17,
        after=4,
    )


def prototype_slide(d: Deck):
    s = d.content(
        "시제품: AI 가 판독 단계를 골라 부른다",
        "명령 한 줄 → 로컬 AI 가 어떤 단계를 돌릴지 정하고 보고했다 (2026-10-23)",
        "하네스의 마지막 조각, AI 가 순서를 정하는 부분의 시제품입니다. v3 의 판독 단계를 AI 가 고를 수 "
        "있는 도구로 만들었습니다. 연습 도면 cone_0019 를 전개도까지 판독해 달라고 한 줄로 명령했더니, "
        "로컬 Qwen 이 먼저 도면을 찾고, 아직 돌린 단계가 없으니 읽기부터 전개까지 돌리고, 결과를 "
        "보고했습니다. AI 가 판단한 건 세 번, 전체 133초였고, 보고한 숫자는 모두 도구 결과에 있던 "
        "값이었습니다. 지어낸 숫자는 없었습니다. 다만 처음부터 끝까지 그대로 돌리는 일에서는 고정 순서와 "
        "차이가 없습니다. 이 방식의 진가는 중간에 막히거나 다시 해야 할 때, 즉 실제 도면에서 나옵니다. "
        "한 가지 덧붙이면, 이 시제품은 AI 의 답을 정해진 양식(어떤 도구, 어떤 값)으로만 나오게 강제하는 "
        "방식으로 만들었습니다. 우리 서버가 표준 tool calling 기능을 켜지 않은 채 떠 있어서입니다. "
        "AI 가 도구를 고르고 프로그램이 실행하는 구조는 같고, 표준 기능은 서버 설정을 바꿔 확인할 "
        "예정입니다.",
    )
    road(s, 1)
    card(
        s,
        X0,
        1.9,
        CW,
        0.8,
        [
            [
                {"text": "명령  ", "bold": True, "color": ORANGE},
                {"text": "“cone_0019 도면을 전개도까지 판독하고 결과를 알려줘”"},
            ]
        ],
        fill=ORANGE_TINT,
        size=19,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0.3,
    )
    flow = [
        ("도면 찾기", "list_drawings"),
        ("01 → 10 실행", "run_stages"),
        ("결과 보고", "finish"),
    ]
    w, gap = 3.6, 0.666
    for i, (head, tool) in enumerate(flow):
        x = X0 + i * (w + gap)
        card(
            s,
            x,
            2.95,
            w,
            1.1,
            [
                {"text": head, "bold": True, "size": 18},
                {"text": tool, "size": 13, "color": GRAY, "font": MONO},
            ],
            fill=LIGHT,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        ).text_frame.margin_left = Inches(0.95)
        circle(s, x + 0.2, 3.2, 0.6, str(i + 1), fill=INK, size=16)
        if i < 2:
            arrow(s, x + w + 0.17, 3.33, 0.32, 0.34)
    stats = [("3 번", "AI 판단"), ("133 초", "전체 시간"), ("0 개", "지어낸 숫자")]
    sw = (CW - 2 * 0.3) / 3
    for i, (value, label) in enumerate(stats):
        box = card(
            s,
            X0 + i * (sw + 0.3),
            4.35,
            sw,
            1.25,
            [
                {"text": value, "bold": True, "size": 34, "color": ORANGE},
                {"text": label, "size": 14, "color": GRAY},
            ],
            fill=WHITE,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=0,
        )
        box.line.color.rgb = rgb(PALE)
    text(
        s,
        X0,
        5.85,
        CW,
        0.6,
        [
            "AI: Qwen3.6-27B (로컬) · 답 양식을 강제하는 방식(structured outputs)으로 구현, "
            "표준 tool calling 은 서버 설정 후 확인 예정",
            "처음부터 끝까지 그대로 돌리는 일은 고정 순서와 같다 — 진가는 막히거나 다시 해야 할 때",
        ],
        size=14,
        color=GRAY,
    )


def toolcall_real_slide(d: Deck):
    s = d.content(
        "tool calling 으로 실제 도면 풀기",
        "작고 확실한 도구를 만들어 두면, AI 가 도면에 맞게 골라 쓰고 결과를 모은다",
        "tool calling 으로 실제 도면을 어떻게 풀 수 있는지 그려 봤습니다. 실제 상세도에는 부품표가 "
        "있습니다. 부품표 읽기 도구가 이 표를 코드로 읽어 부품 목록과 재질, 두께를 돌려줍니다. 'SHELL ... "
        "t8' 처럼 글자 그대로라서 두께를 18 로 볼 일이 없습니다. AI 는 그 목록에서 판재만 골라 "
        "하나씩 보자고 판단하고, 부품마다 모양을 판단하고, 뷰에서 크기를 읽고, 전개를 계산하고, 마지막에 "
        "자기가 읽은 값을 부품표와 대조합니다. 청록색은 이미 있는 도구, 주황색 테두리는 새로 만들 "
        "도구입니다. AI 는 좁은 창으로 도구의 결과만 보니까, 결과를 작고 정확하게 돌려주는 게 핵심입니다. "
        "대조에서 어긋나면 다시 읽거나 사람에게 묻는 것도 AI 가 고릅니다. 고정 순서로는 이런 대응을 할 수 "
        "없습니다.",
    )
    road(s, 2)
    real_sheet(s, X0, 1.95, 2.3, 1.6)
    arrow(s, X0 + 2.45, 2.57, 0.35, 0.36)
    card(
        s,
        X0 + 2.95,
        1.95,
        5.0,
        1.6,
        [
            {"text": "AI 의 판단", "bold": True, "size": 14, "color": ORANGE},
            {
                "text": "“부품표에서 판재만 골라 하나씩 읽자”",
                "size": 18,
                "bold": True,
            },
        ],
        fill=INK,
        color=WHITE,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0.3,
        after=4,
    )
    arrow(s, X0 + 8.1, 2.57, 0.35, 0.36)
    tx = X0 + 8.6
    tw = CW - 8.6
    rows = [
        ["부품", "모양", "두께 (부품표)"],
        ["SHELL", "원통", "t8"],
        ["TOP HEAD", "헤드", "t10"],
        ["…", "…", "…"],
    ]

    def style(r, c):
        if r == 0:
            return TEAL, WHITE, True, 12, PP_ALIGN.CENTER
        return LIGHT if r % 2 else WHITE, INK, False, 12, PP_ALIGN.CENTER

    table(s, tx, 1.95, tw, 1.6, rows, [1.25, 0.8, tw - 2.05], style)
    text(s, tx, 3.6, tw, 0.35, ["부품별 결과를 모아 보고"], size=12, color=GRAY)
    card(s, X0, 4.1, CW, 1.65, [""], fill=LIGHT)
    text(
        s,
        X0 + 0.2,
        4.15,
        4.0,
        0.35,
        [{"text": "AI 가 고르는 도구", "bold": True}],
        size=13,
        color=GRAY,
    )
    tools = [
        ("부품표 읽기", False),
        ("부품 목록", False),
        ("모양 판단", True),
        ("크기 읽기", False),
        ("전개 계산", True),
        ("대조 검사", False),
    ]
    n, gap = len(tools), 0.32
    tw2 = (CW - 0.4 - (n - 1) * gap) / n
    for i, (name, have) in enumerate(tools):
        x = X0 + 0.2 + i * (tw2 + gap)
        c = chip(
            s,
            x,
            4.6,
            tw2,
            0.85,
            name,
            fill=TEAL if have else WHITE,
            color=WHITE if have else ORANGE,
            size=14,
            bold=True,
        )
        if not have:
            dashed(c, width=2)
        if i < n - 1:
            arrow(s, x + tw2 + 0.05, 4.87, 0.22, 0.3)
    chip(s, X0, 6.0, 2.0, 0.42, "있는 도구 (v2 · v3)", fill=TEAL, color=WHITE, size=12)
    dashed(
        chip(
            s,
            X0 + 2.15,
            6.0,
            1.8,
            0.42,
            "새로 만들 도구",
            fill=WHITE,
            color=ORANGE,
            size=12,
        )
    )
    text(
        s,
        X0 + 4.2,
        5.97,
        CW - 4.2,
        0.5,
        [
            [
                {"text": "이상하면  ", "bold": True, "color": ORANGE},
                {
                    "text": "확대해서 다시 보기 · 다른 도구로 · 사람에게 묻기 — 이것도 AI 가 고른다"
                },
            ]
        ],
        size=15,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def outlook_slide(d: Deck):
    s = d.content(
        "전망: 함수로 만들 수 있으면, AI 가 쓴다",
        "필요한 기능을 파이썬 함수로 만들고 AI 가 적재적소에 부르면 → 최종 목표까지",
        "마지막으로 전망입니다. 우리에게 필요한 기능을 파이썬 함수로 만들 수만 있다면, 그건 AI 가 쓸 수 "
        "있는 도구가 됩니다. AI 가 그 도구를 적재적소에 부르고 결과를 모으고, 하네스가 검사하고 기록하고 "
        "점수를 매기면, 도면에서 커팅플랜과 구매의뢰까지 갈 수 있다고 봅니다. 그리고 재료는 이미 꽤 "
        "있습니다. 도면 읽기 도구는 v3 의 13단계가 있고, 전개·분할·네스팅·구매의뢰를 계산하는 도구는 v2 "
        "에서 만들어 둔 것이 사람이 넣은 부품으로 끝까지 돌아갑니다. 로컬 AI 가 도구를 골라 쓰는 것도 "
        "시제품으로 확인했습니다. 남은 일은 실제 도면에 필요한 도구를 더하고, 단계마다 점수를 매기는 "
        "것입니다.",
    )
    road(s, 3)
    eq = [
        ("파이썬 함수", "필요한 기능 하나씩", LIGHT, INK),
        ("AI 가 골라 부른다", "tool calling", ORANGE_TINT, ORANGE),
        ("하네스", "검사 · 기록 · 평가", TEAL_TINT, TEAL),
        ("도면 → 구매의뢰", "최종 목표", INK, WHITE),
    ]
    w, gap = 2.55, 0.64
    for i, (head, sub, fill, color) in enumerate(eq):
        x = X0 + i * (w + gap)
        card(
            s,
            x,
            1.95,
            w,
            1.5,
            [
                {"text": head, "bold": True, "size": 19, "color": color},
                {"text": sub, "size": 14, "color": "B8C4C9" if fill == INK else GRAY},
            ],
            fill=fill,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=3,
        )
        if i < 3:
            text(
                s,
                x + w,
                1.95,
                gap,
                1.5,
                ["=" if i == 2 else "+"],
                size=36,
                bold=True,
                color=GRAY,
                align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.MIDDLE,
            )
    have = [
        ("도면 읽기 도구", "v3 판독 13단계"),
        ("계산 도구", "v2 전개 · 분할 · 네스팅 · 구매의뢰 — 끝까지 돈다"),
        ("AI 가 고르기", "로컬 AI 시제품"),
    ]
    todo = [
        ("실제 도면용 도구", "부품표 읽기 · 부품 목록 · 크기 읽기"),
        ("단계별 점수", "실제 도면 정답으로, 어디서 틀리는지"),
    ]
    hw = 7.2
    text(
        s,
        X0,
        3.75,
        hw,
        0.4,
        [{"text": "이미 있는 것", "bold": True}],
        size=15,
        color=TEAL,
    )
    for i, (head, sub) in enumerate(have):
        y = 4.2 + i * 0.78
        badge(s, X0, y + 0.05, 0.52, CHECK, TEAL, size=18)
        text(
            s,
            X0 + 0.7,
            y,
            hw - 0.7,
            0.65,
            [[{"text": head + "  ", "bold": True}, {"text": sub, "color": GRAY}]],
            size=16,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    tx = X0 + hw + 0.4
    tw = CW - hw - 0.4
    text(
        s, tx, 3.75, tw, 0.4, [{"text": "남은 것", "bold": True}], size=15, color=ORANGE
    )
    for i, (head, sub) in enumerate(todo):
        card(
            s,
            tx,
            4.2 + i * 1.17,
            tw,
            1.0,
            [
                {"text": head, "bold": True, "size": 17},
                {"text": sub, "size": 14, "color": GRAY},
            ],
            fill=ORANGE_TINT,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.25,
            after=2,
        )


def agent_slide(d: Deck):
    s = d.content(
        "Claude 대신 로컬 AI 로: 에이전트 시제품",
        "v2 의 반복 구조는 그대로, AI 만 우리 서버의 Qwen 으로 바꿨다",
        "그래서 시제품을 만들었습니다. v2 에서 Claude 가 skill 25개를 골라 쓰던 구조를 그대로 가져오되, "
        "AI 를 우리 서버의 로컬 모델 Qwen 으로 바꿨습니다. 도구는 v3 의 판독 13단계를 하나씩 도구로 감싼 "
        "것에, 도면 찾기와 상태 보기 같은 도구 네 개를 더해 17개입니다. 명령을 한 줄 주면 AI 가 다음에 "
        "부를 도구를 고르고, 프로그램이 실행하고, 결과를 돌려주는 걸 반복합니다. 판독 단계는 v3 그대로라 "
        "결과 파일도 같습니다. 달라진 건 순서를 누가 정하느냐 하나뿐이라, 고정 순서와 공정하게 비교할 수 "
        "있습니다. 모든 판단은 기록으로 남습니다.",
    )
    road(s, 1)
    rows = [
        ("v2", "Claude Opus", "클라우드", "skill 25개", "도면 → 구매의뢰", LIGHT, GRAY),
        (
            "시제품",
            "Qwen3.6-27B",
            "우리 서버",
            "도구 17개",
            "도면 읽기 (v3 13단계)",
            TEAL_TINT,
            TEAL,
        ),
    ]
    for i, (name, model, where, tools, job, fill, color) in enumerate(rows):
        y = 1.9 + i * 1.0
        chip(s, X0, y + 0.1, 1.5, 0.62, name, fill=INK, color=WHITE, size=16, bold=True)
        card(
            s,
            X0 + 1.7,
            y,
            3.3,
            0.82,
            [
                {"text": model, "bold": True, "size": 17, "color": color},
                {"text": where, "size": 12, "color": GRAY},
            ],
            fill=fill,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
            after=0,
        )
        arrow(s, X0 + 5.1, y + 0.23, 0.45, 0.36, kind=MSO_SHAPE.LEFT_RIGHT_ARROW)
        card(
            s,
            X0 + 5.65,
            y,
            2.6,
            0.82,
            [{"text": tools, "bold": True, "size": 17}],
            fill=fill,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
        )
        text(
            s,
            X0 + 8.45,
            y,
            CW - 8.45,
            0.82,
            [job],
            size=16,
            color=GRAY,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    y = 4.15
    boxes = [
        ("명령 한 줄", "자연어로", ORANGE_TINT, 2.0),
        ("AI 가 고른다", "다음에 부를 도구", INK, 2.3),
        ("도구 17개", "tools.py", LIGHT, 2.1),
        ("판독 13단계", "v3 그대로", LIGHT, 2.1),
        ("작업 폴더", "단계마다 결과 파일", LIGHT, 2.3),
    ]
    gap = (CW - sum(b[3] for b in boxes)) / 4
    x = X0
    for i, (head, sub, fill, w) in enumerate(boxes):
        card(
            s,
            x,
            y,
            w,
            1.15,
            [
                {"text": head, "bold": True, "size": 16},
                {"text": sub, "size": 12, "color": "B8C4C9" if fill == INK else GRAY},
            ],
            fill=fill,
            color=WHITE if fill == INK else INK,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
        if i < 4:
            kind = MSO_SHAPE.LEFT_RIGHT_ARROW if i == 1 else MSO_SHAPE.RIGHT_ARROW
            arrow(s, x + w + gap / 2 - 0.17, y + 0.4, 0.34, 0.34, kind=kind)
        x += w + gap
    band(
        s,
        5.65,
        "달라진 것 하나",
        "순서를 누가 정하나 — 판독 단계는 v3 그대로라 고정 순서와 공정하게 비교할 수 있다",
        fill=LIGHT,
        color=TEAL,
    )


def trajectory_slide(d: Deck):
    s = d.content(
        "AI 는 이렇게 판단했다",
        "기록(trajectory)에 남은 AI 의 판단 세 번 — 글자 그대로",
        "시제품이 남긴 기록에서 AI 가 무슨 생각으로 어떤 도구를 불렀는지 그대로 옮겼습니다. 첫 번째 판단에서 "
        "도면이 어디 있는지 확인하려고 도면 찾기 도구를 불렀습니다. 두 번째에서는 아직 돌린 단계가 없으니 "
        "전개도까지 한 번에 돌리겠다고 판단했고, 이 실행에 92초가 걸렸습니다. 세 번째에서는 도구를 더 "
        "부르지 않고 결과를 보고했습니다. 보고에 나온 숫자는 모두 도구 결과에 있던 값이었습니다. 작은 "
        "지름 92 는 정답 100 과 다른데, 이건 판독 단계의 오차이고 AI 가 지어낸 숫자가 아닙니다.",
    )
    road(s, 1)
    turns = [
        (
            "1",
            "6 초",
            "“작업 폴더와 경로를 확인하기 위해 list_drawings 를 호출합니다.”",
            "list_drawings(cone_0019)",
            "도면 1개, 돌린 단계 없음",
        ),
        (
            "2",
            "17 초",
            "“아직 실행된 단계가 없으므로 … read 부터 develop 까지 run_stages 로 한 번에 실행합니다.”",
            "run_stages(01 → 10)",
            "10단계 모두 done (92 초)",
        ),
        (
            "3",
            "133 초",
            "“판독이 완료되었습니다. 형상 원추대, SPCC 4mm, 지름 150 / 92, 전개 반지름 405.65 / 252.87, 68.33°”",
            "finish (보고)",
            "숫자는 모두 도구 결과에 있던 값",
        ),
    ]
    for i, (num, t, said, tool, result) in enumerate(turns):
        y = 1.9 + i * 1.5
        circle(s, X0, y + 0.2, 0.75, num, fill=INK, size=20)
        text(
            s,
            X0 - 0.1,
            y + 0.98,
            0.95,
            0.3,
            [t],
            size=11,
            color=GRAY,
            align=PP_ALIGN.CENTER,
        )
        card(
            s,
            X0 + 1.0,
            y,
            6.6,
            1.25,
            [{"text": said, "size": 14, "italic": True}],
            fill=INK,
            color=WHITE,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.22,
        )
        arrow(s, X0 + 7.7, y + 0.45, 0.35, 0.34)
        card(
            s,
            X0 + 8.15,
            y,
            CW - 8.15,
            1.25,
            [
                {"text": tool, "bold": True, "size": 14, "font": MONO},
                {"text": result, "size": 13, "color": GRAY},
            ],
            fill=LIGHT,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.2,
            after=3,
        )
    text(
        s,
        X0,
        6.45,
        CW,
        0.35,
        ["작은 지름 92 는 판독 단계(09)의 오차 — 정답 100. AI 가 지어낸 숫자는 아니다"],
        size=12,
        color=GRAY,
    )


def modes_slide(d: Deck):
    s = d.content(
        "AI 가 도구를 부르는 두 방식",
        "시제품은 ‘답 양식 강제’. 표준 기능은 서버 설정을 바꾼 뒤 비교한다",
        "AI 가 도구를 부르는 방식은 크게 두 가지입니다. 시제품은 왼쪽 방식, AI 의 답을 '생각, 도구 이름, "
        "값' 양식으로만 나오게 강제하는 방식을 썼습니다. 작은 AI 도 형식을 틀릴 수 없다는 게 장점이고, 한 "
        "번에 도구 하나만 고를 수 있다는 게 대가입니다. 오른쪽은 서버의 표준 tool calling 기능입니다. AI 가 "
        "학습한 호출 형식 그대로라 더 자연스럽고, 여러 도구를 한 번에 부를 수도 있습니다. 그런데 지금 우리 "
        "서버는 이 기능을 켜지 않은 채 떠 있어서 요청을 보내 보니 거절했습니다. 서버 설정을 바꿔 두 방식을 "
        "같은 명령으로 비교하는 것 자체가 하네스 실험입니다.",
    )
    road(s, 1)
    cols = [
        (
            "답 양식 강제",
            "structured outputs",
            TEAL,
            TEAL_TINT,
            "지금 서버: 된다 · 시제품이 쓴 방식",
            [
                "답이 {생각, 도구, 값} 양식 밖으로 못 나간다",
                "작은 AI 도 형식을 틀릴 수 없다",
                "대신 한 번에 도구 하나",
            ],
        ),
        (
            "표준 tool calling",
            "서버의 기능",
            ORANGE,
            ORANGE_TINT,
            "지금 서버: 거절 (설정 필요)",
            [
                "AI 가 학습한 호출 형식 그대로",
                "글과 호출을 같이, 여러 도구를 한 번에",
                "서버를 tool parser 옵션으로 다시 띄워야",
            ],
        ),
    ]
    w = (CW - 0.4) / 2
    for i, (head, sub, color, fill, state, items) in enumerate(cols):
        x = X0 + i * (w + 0.4)
        card(
            s,
            x,
            1.9,
            w,
            3.5,
            [
                [
                    {"text": head, "bold": True, "size": 24, "color": color},
                    {"text": "  " + sub, "size": 14, "color": GRAY},
                ]
            ]
            + [{"text": item, "bullet": True} for item in items],
            fill=fill,
            size=17,
            margin=0.3,
            after=10,
        )
        chip(
            s,
            x + 0.3,
            4.65,
            w - 0.6,
            0.5,
            state,
            fill=WHITE,
            color=color,
            size=14,
            bold=True,
        )
    band(
        s,
        5.7,
        "재 볼 것",
        "같은 명령, 같은 도면으로 두 방식 비교 — 작은 AI 에게 어느 쪽이 나은가",
    )


def next_week_slide(d: Deck):
    s = d.content(
        "다음 주에 할 일: 부품표부터 읽는다",
        "도면마다 있는 부품표를 코드로 읽어 설비 하나의 부품 목록을 만든다 (docs/v4.md 8절)",
        "다음 주에는 부품표 단계를 만듭니다. 실제 상세도에는 부품표가 있고, DXF 안에 글자로 들어 있어서 "
        "코드로 읽을 수 있습니다. 첫째, 도면 한 장의 부품표를 읽습니다. 글자 위치로 표의 칸을 나눠 행마다 "
        "품번, 이름, 재질, 수량, 두께를 뽑습니다. 둘째, 도면별 부품표를 합쳐 설비 하나의 부품 목록을 "
        "만들고, 판재인지, 어떻게 펼칠지를 판정합니다. 셋째, 정답 커팅플랜과 맞춰 채점합니다. 넷째, 이 새 "
        "단계를 도구로 등록해서 AI 가 고를 수 있게 합니다. 손으로 미리 맞춰 보니 S-2120 의 정답 부품 22종이 "
        "부품표에 모두 있었고, 재질과 두께는 22종 중 21종이 맞았습니다. 몸통 두께도 부품표의 't8' 을 "
        "코드가 그대로 읽습니다. 판재 크기는 부품표에 없어서 그다음 일입니다.",
    )
    road(s, 2)
    items = [
        (
            "1",
            "부품표 읽기 (도면 한 장)",
            "DXF 글자 위치로 표의 칸을 나눠 품번 · 이름 · 재질 · 수량 · 두께. 코드만",
        ),
        (
            "2",
            "부품 목록 (설비 하나)",
            "도면별 부품표를 합치고, 판재인지 · 어떻게 펼칠지 판정. 근거를 남긴다",
        ),
        (
            "3",
            "채점",
            "정답 커팅플랜과 (도면, 품번)으로 맞춰: 찾은 비율 · 판재 판정 · 재질 · 두께 · 수량",
        ),
        (
            "4",
            "도구로 등록",
            "새 단계를 시제품의 도구 목록에 넣는다 → AI 가 고를 수 있다",
        ),
    ]
    w, h = (CW - 0.3) / 2, 1.65
    for i, (num, head, body) in enumerate(items):
        r, c = divmod(i, 2)
        x = X0 + c * (w + 0.3)
        y = 1.9 + r * (h + 0.25)
        card(
            s,
            x,
            y,
            w,
            h,
            [
                {"text": head, "bold": True, "size": 20},
                {"text": body, "size": 15, "color": GRAY},
            ],
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.25,
            after=6,
        ).text_frame.margin_left = Inches(1.15)
        circle(s, x + 0.25, y + h / 2 - 0.35, 0.7, num, size=20)
    band(
        s,
        5.75,
        "손으로 본 기댓값",
        "S-2120 정답 부품 22종 중 22종이 부품표에, 재질 · 두께 21종 일치 — 몸통 두께도 ‘t8’ 그대로",
        size=16,
    )


def final_path_slide(d: Deck):
    s = d.content(
        "최종 목표까지",
        "실제 도면 → 커팅플랜 → 구매의뢰, 로컬 AI 만으로",
        "최종 목표까지의 길입니다. 판독을 단계로 나누는 일은 끝났고, AI 가 도구를 고르는 시제품도 "
        "돌았습니다. 다음 주에는 부품표 단계로 설비의 부품 목록과 재질, 두께를 만들고 정답과 채점합니다. "
        "그다음은 부품표에 없는 판재 크기를 뷰의 치수와 품번 풍선에서 읽는 일입니다. 그리고 다시 묻기나 "
        "여러 번 물어 다수결 같은 하네스 장치를 켜고 끄며 효과를 잽니다. 같은 조건에서 Claude 와 로컬 AI "
        "도, 답 양식 강제와 표준 tool calling 도 비교합니다. 그리고 v2 에서 만들어 둔 전개, 분할, "
        "네스팅, 구매의뢰 도구를 이어 붙여, 마지막에는 실제 도면에서 구매의뢰서까지 로컬 AI 만으로 가는 "
        "것이 목표입니다.",
    )
    road(s, 3)
    steps = [
        ("판독을 단계로", "13단계, 단계마다 파일", "완료", TEAL),
        ("AI 가 도구 고르기", "로컬 Qwen 시제품", "시제품", TEAL),
        ("부품표 단계", "부품 목록 · 재질 · 두께 · 채점", "다음 주", ORANGE),
        ("판재 크기", "뷰 치수 · 품번 풍선 읽기", "", GRAY),
        (
            "하네스 장치 비교",
            "다시 묻기 · 다수결 · Claude 대 로컬 · 표준 tool calling",
            "",
            GRAY,
        ),
        ("뒷단 연결", "전개 → 분할 → 네스팅 → 구매의뢰 (v2 도구)", "", GRAY),
        ("최종", "실제 도면 → 구매의뢰, 로컬 AI 만으로", "", INK),
    ]
    n = len(steps)
    w = (CW - (n - 1) * 0.12) / n
    shape(s, MSO_SHAPE.RECTANGLE, X0 + w / 2, 2.32, CW - w, 0.06, PALE)
    for i, (head, sub, state, color) in enumerate(steps):
        x = X0 + i * (w + 0.12)
        done = state in ("완료", "시제품")
        circle(
            s,
            x + w / 2 - 0.35,
            2.0,
            0.7,
            CHECK if done else str(i + 1),
            fill=color,
            size=20 if done else 18,
        )
        card(
            s,
            x,
            3.0,
            w,
            2.4,
            [
                {"text": head, "bold": True, "size": 15},
                {"text": sub, "size": 12, "color": GRAY},
            ],
            fill=TEAL_TINT if done else (ORANGE_TINT if state else LIGHT),
            margin=0.15,
            after=6,
        )
        if state:
            chip(
                s,
                x + 0.15,
                4.85,
                w - 0.3,
                0.4,
                state,
                fill=color,
                color=WHITE,
                size=12,
                bold=True,
            )
    band(
        s,
        5.75,
        "기준",
        "바꿀 때마다 같은 도면으로 전후를 잰다. 숫자로 보인 것만 됐다고 말한다",
        fill=LIGHT,
        color=INK,
    )


def closing_slide(d: Deck):
    s = d.slide(
        "정리하겠습니다. Claude 대신 우리 서버의 로컬 AI 가 도구를 골라 v3 판독 단계를 돌리는 시제품을 "
        "만들었고, 연습 도면 한 장을 끝까지 돌렸습니다. 다음 주에는 부품표 단계를 만듭니다. 도면의 "
        "부품표를 코드로 읽어 설비 하나의 부품 목록과 재질, 두께를 만들고, 정답과 채점하고, 도구로 "
        "등록합니다. 최종 목표는 필요한 기능을 도구로 만들고, AI 가 골라 쓰고, 하네스가 받쳐서, "
        "실제 도면에서 구매의뢰서까지 로컬 AI 만으로 가는 것입니다. 질문 받겠습니다.",
        dark=True,
    )
    text(s, X0, 0.8, CW, 0.8, ["정리"], size=36, bold=True, color=WHITE)
    points = [
        ("시제품", "로컬 AI 가 도구를 골라 v3 판독 단계를 돌렸다"),
        ("다음 주", "부품표 단계 → 부품 목록 · 재질 · 두께 · 채점"),
        ("최종", "도구 + AI 의 선택 + 하네스 → 실제 도면에서 구매의뢰까지"),
    ]
    for i, (label, point) in enumerate(points):
        y = 2.0 + i * 1.2
        chip(
            s,
            X0,
            y + 0.05,
            1.6,
            0.6,
            label,
            fill=ORANGE if label == "다음 주" else "34444C",
            color=WHITE,
            size=17,
            bold=True,
        )
        text(
            s,
            X0 + 1.9,
            y,
            CW - 1.9,
            0.7,
            [point],
            size=22,
            color=WHITE,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    text(s, X0, 6.2, CW, 0.6, ["질문"], size=26, bold=True, color=ORANGE)


def main() -> None:
    d = Deck(OUT, TITLE, FOOTER)
    title_slide(d)
    next_overview_slide(d)
    harness_slide(d)
    toolcall_slide(d)
    agent_slide(d)
    prototype_slide(d)
    trajectory_slide(d)
    modes_slide(d)
    toolcall_real_slide(d)
    next_week_slide(d)
    final_path_slide(d)
    outlook_slide(d)
    closing_slide(d)
    print(f"{d.count} slides -> {d.save()}")


if __name__ == "__main__":
    main()
