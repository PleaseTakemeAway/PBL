"""회사 담당자에게 보내는 설명 자료: 도면 판독 → 전개도, 합성 도면 검증 결과 → company_brief.pptx

docs/company_brief.md 와 같은 내용을 슬라이드로 옮긴 것이다. 청중은 도면과 제작은 잘 알고
AI 는 잘 모르는 회사 엔지니어다. 합성 도면과 집계 숫자만 쓰고 고객 도면은 싣지 않는다.

숫자의 출처:
- 결과 표는 빌드할 때 SCORE (scripts/reader/score_synthetic.py 의 score.json) 를 읽어 채운다.
  없으면 결과 슬라이드에 "점수 파일 없음" 을 적는다.
- 이전 기준선 27/30, 11/30 은 동료의 2026-10-18 실행
  runs/reader/deepseek_ocr_qwen_reasoning_skills 의 accuracy.md, flat_patterns.md.
- 콘·경판 그림은 docs/data/synthetic/*.png (scripts/synthetic_figures.py).
- 예시 도면 그림은 SCORE 옆 실행 폴더의 EXAMPLE 작업 폴더에서 가져온다. cone_0023 은
  2026-10-27 실행에서 모든 항목을 맞힌 도면이다.

사용 (레포 루트에서):
  PYTHONPATH=. uv run --with python-pptx python presentation/build_company_brief.py [--score <score.json>]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

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
    band,
    card,
    chip,
    picture,
    table,
    text,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "company_brief.pptx"
SCORE = ROOT / "runs" / "reader" / "gen1027" / "local_new" / "score.json"
EXAMPLE = "cone_0023"
TITLE = "도면 자동 판독 → 전개도"
FOOTER = "PBL · 도면 판독 → 전개도 · 2026-10-27"

ITEMS = ["단계", "표제란", "뷰", "형상", "치수", "전개"]
ITEM_DESC = {
    "단계": "10단계가 오류 없이 끝남",
    "표제란": "도면 번호 · 축척 · 재질 · 두께",
    "뷰": "정면 · 평면 · 우측면 이름",
    "형상": "5형상 중 맞는 것",
    "치수": "전개에 쓴 치수",
    "전개": "전개 값 오차 1% 이내",
}
CLASSES = ["flat", "bent_sheet", "cylinder", "cone", "press_formed"]
CLASS_KR = {
    "flat": "평판",
    "bent_sheet": "굽힘판",
    "cylinder": "원통",
    "cone": "콘",
    "press_formed": "경판",
}
FIG = ROOT / "docs" / "data" / "synthetic"


def head_style(r, c):
    if r == 0:
        return TEAL, WHITE, True, 14, PP_ALIGN.CENTER
    return (
        (LIGHT if r % 2 else WHITE),
        INK,
        c == 0,
        14,
        (PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER),
    )


def title_slide(d):
    s = d.slide(
        "회사 담당자용 설명 자료. 합성 도면 30장으로 판독기를 검증한 결과.", dark=True
    )
    text(
        s,
        X0,
        1.9,
        CW,
        1.6,
        ["도면 자동 판독 → 전개도"],
        size=40,
        bold=True,
        color=WHITE,
    )
    text(s, X0, 3.0, CW, 0.5, ["합성 도면 30장 검증 결과"], size=24, color=ORANGE)
    text(s, X0, 5.6, CW, 0.5, ["2026-10-27 · PBL 팀"], size=16, color=WHITE)


def summary_slide(d, score):
    s = d.content(
        "요약",
        "도면을 넣으면 전개도가 나옵니다. AI 는 읽고 고르고, 계산은 회사 식으로 합니다.",
        "네 가지만 기억하시면 됩니다.",
    )
    points = [
        (
            "하는 일",
            "부품 도면(DXF) 1장 → 표제란 · 뷰 · 형상 · 치수 → 전개도(DXF · PNG). 3D 복원은 이번 범위에서 뺐습니다",
        ),
        (
            "사내 AI",
            "글자 인식(DeepSeek-OCR-2)과 판단(Qwen3.6-27B) 모델을 연구실 GPU 서버에서 돌립니다. 도면이 외부로 나가지 않습니다",
        ),
        (
            "회사 식",
            "전개 계산은 주신 계산 기준(평균지름, 콘 θ = 360°·sin α, 2:1 경판 1.2 × Dm)을 옮긴 코드가 합니다",
        ),
        ("결과", result_line(score)),
    ]
    for i, (head, body) in enumerate(points):
        y = 1.9 + i * 1.18
        chip(
            s,
            X0,
            y + 0.12,
            1.6,
            0.66,
            head,
            fill=TEAL if i < 3 else ORANGE,
            color=WHITE,
            size=16,
            bold=True,
        )
        text(
            s,
            X0 + 1.85,
            y + 0.08,
            CW - 1.85,
            1.0,
            [body],
            size=17,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def result_line(score):
    if not score:
        return "점수 파일 없음"
    n = len(score)
    ok = lambda k: sum(r["ok"][k] for r in score)  # noqa: E731
    return (
        f"합성 도면 {n}장 중 형상 {ok('형상')}장, 전개 치수(1% 이내) {ok('전개')}장을 맞혔습니다. "
        f"이전 기준선은 형상 27장, 전개 11장이었습니다"
    )


STEPS = [
    ("도면 읽기", "P"),
    ("표제란 규칙", "P"),
    ("표제란 글자 인식", "A"),
    ("표제란 정리", "A"),
    ("뷰 찾기", "P"),
    ("뷰 이름 · 형상", "A"),
    ("판독 정리", "P"),
    ("치수 연결", "P"),
    ("전개 치수 고르기", "A"),
    ("전개 계산 · 전개도", "P"),
]


def process_slide(d):
    s = d.content(
        "처리 과정: 10단계",
        "단계마다 결과를 파일로 남겨서, 틀리면 어느 단계에서 틀렸는지 바로 찾습니다.",
        "주황은 AI 가 판단하는 단계, 청록은 프로그램이 정해진 규칙으로 하는 단계. "
        "AI 단계에는 회사 계산 기준과 도면 관례 문서를 같이 넣어 준다.",
    )
    w, gap = 2.15, 0.33
    for i, (label, who) in enumerate(STEPS):
        row, col = divmod(i, 5)
        x = X0 + col * (w + gap)
        y = 2.0 + row * 1.9
        fill = ORANGE if who == "A" else TEAL
        card(
            s,
            x,
            y,
            w,
            1.15,
            [
                {"text": f"{i + 1:02d}", "bold": True, "size": 13},
                {"text": label, "bold": True},
            ],
            fill=fill,
            color=WHITE,
            size=16,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.08,
        )
        if col < 4:
            arrow(s, x + w + 0.03, y + 0.42, w=0.27, h=0.3, fill=GRAY)
    chip(
        s,
        X0,
        5.95,
        2.6,
        0.5,
        "프로그램 (규칙 · 계산)",
        fill=TEAL,
        color=WHITE,
        size=13,
        bold=True,
    )
    chip(
        s,
        X0 + 2.8,
        5.95,
        2.6,
        0.5,
        "AI (읽기 · 판단)",
        fill=ORANGE,
        color=WHITE,
        size=13,
        bold=True,
    )
    text(
        s,
        X0 + 5.7,
        5.95,
        6.4,
        0.5,
        ["전개 계산(10)은 AI 가 아니라 코드가 합니다"],
        size=15,
        color=GRAY,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def data_slide(d):
    s = d.content(
        "시험 데이터: 합성 도면 30장",
        "정답을 단계마다 정확히 아는 단순한 도면으로 먼저 끝까지 맞히는지 봅니다.",
        "실제 도면에는 단계별 정답(뷰가 몇 개, 형상, 전개 치수)이 없다. 여기서 못 맞히면 "
        "원인이 AI 인지 프로그램인지 데이터인지 가릴 수 없다. 치수 2~400 mm, 실제 부품보다 작고 단순하다.",
    )
    rows = [
        ["형상", "장수", "부품", "전개 결과"],
        ["평판", "6", "길이 × 폭 × 두께, 구멍", "판 그대로"],
        ["굽힘판", "6", "L 자 90° 굽힘", "펼친 길이, 굽힘선"],
        ["원통", "6", "외경, 길이, 두께", "원둘레 × 길이"],
        ["콘", "6", "대경, 소경, 높이, 두께", "부채꼴 (R₁, R₂, θ)"],
        ["경판", "6", "2:1 반타원 헤드", "원판 지름"],
    ]
    table(s, X0, 1.85, 8.2, 3.6, rows, [1.4, 0.9, 3.1, 2.8], head_style)
    card(
        s,
        X0 + 8.5,
        1.85,
        CW - 8.5,
        3.6,
        [
            {"text": "도면 형식", "bold": True, "color": TEAL},
            "A3, 3각법 3면도",
            "표제란: 부품명, 재질 · 두께, 축척, 도면 번호",
            "외형 치수 4개, 숨은선 · 중심선",
            {"text": "재질", "bold": True, "color": TEAL},
            "SS400, SPHC, SUS304, SPCC, SA516-70",
        ],
        size=14,
    )


def formula_slide(d):
    s = d.content(
        "정답은 회사 계산 기준으로 만들었습니다",
        "모두 평균지름 Dm = 외경 − 두께 기준 (두께 가운데 길이는 말거나 성형해도 변하지 않음)",
        "주신 계산 문서(쉘 · 콘 · 헤드 전개)와 전개 규칙을 그대로 따랐다. 정답을 만드는 코드와 "
        "판독기의 전개 코드는 따로 썼고, 같은 치수를 넣으면 30장 모두 0.01 mm 안에서 같다.",
    )
    rows = [
        ["형상", "식", "예"],
        ["원통", "L = π × Dm, 폭 = 원통 길이", "외경 100, t3 → π × 97 = 304.73"],
        [
            "콘",
            "S = √(H² + ((D₁−D₂)/2)²), sin α = (D₁−D₂)/2S\nR₁ = D₁/(2 sin α), R₂ = D₂/(2 sin α), θ = 360° × sin α",
            "150/100, H150, t4 → R₁ 444.04, R₂ 291.97, θ 59.18°",
        ],
        [
            "2:1 경판",
            "Db = 1.2 × Dm (직선부 없음, 트림 여유 제외)",
            "외경 200, t6 → 1.2 × 194 = 232.8",
        ],
        [
            "굽힘판",
            "L = (a−(R+t)) + (b−(R+t)) + (π/2)(R + K·t)\nK: R/t<1 → 0.33, 1~3 → 0.40, ≥3 → 0.50",
            "100 × 100, t2, R0 → 197.04",
        ],
        ["평판", "길이 × 폭 그대로", ""],
    ]

    def style(r, c):
        fill, color, bold, size, align = head_style(r, c)
        return fill, color, bold, size, PP_ALIGN.CENTER if r == 0 else PP_ALIGN.LEFT

    table(s, X0, 1.85, CW, 4.6, rows, [1.5, 6.3, 4.333], style)


def fixes_slide(d):
    s = d.content(
        "이전 정답에서 고친 것",
        "이전 세트의 콘 전개와 경판 모양은 실제로 만들 수 없는 값이었습니다.",
        "콘: 이전 부채꼴은 바깥 호 157 인데 감아야 할 원둘레는 471 이라 말아도 콘이 되지 않는다. "
        "회사 식은 458.6 대 458.7 로 닫힌다. 판독기는 이미 회사 식으로 맞게 계산했는데 정답이 틀려 "
        "콘 6장이 오차 114~246% 로 오답 처리되고 있었다. 경판: 원호와 직선부가 37° 꺾여 만나던 것을 "
        "2:1 반타원 하나로, 원판 계수 1.3415(근거 없음)를 회사 약산식 1.2 × Dm 으로 바꿨다. "
        "그 밖에 굽힘 K 계수 0.40 → 0.33 (R/t < 1), 굽힘선 위치, 중복 선, 깨진 Ø 표기를 고쳤다.",
    )
    picture(s, FIG / "cone_sector.png", X0, 1.75, w=6.0)
    picture(s, FIG / "press_profile.png", X0 + 6.15, 1.95, w=6.0)
    text(
        s,
        X0,
        4.75,
        6.0,
        0.4,
        ["콘 부채꼴: 이전(왼쪽)은 닫히지 않음"],
        size=14,
        bold=True,
        color=TEAL,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        X0 + 6.15,
        4.75,
        6.0,
        0.4,
        ["경판 단면: 이전(왼쪽)은 37° 꺾임"],
        size=14,
        bold=True,
        color=TEAL,
        align=PP_ALIGN.CENTER,
    )
    band(
        s,
        5.4,
        "그 밖에",
        "굽힘 K 계수 0.40 → 0.33 (R/t < 1) · 굽힘선은 굽힘부 가운데 · 중복 선 · 깨진 Ø 표기",
        h=0.75,
        size=15,
    )


def results_slide(d, score):
    s = d.content(
        "결과: 항목별로 몇 장 맞혔나",
        "로컬 AI 두 모델로 30장 전체를 돌리고 정답과 항목마다 대조했습니다.",
        "기준: 표제란은 도면 번호 · 축척 · 재질 · 두께가 모두 같을 때, 치수는 0.5 mm 또는 0.5% 안, "
        "전개는 전개 값 오차 1% 이내. 점수 파일: " + str(SCORE.relative_to(ROOT)),
    )
    if not score:
        text(s, X0, 2.5, CW, 1, ["점수 파일 없음"], size=20, color=GRAY)
        return
    by = defaultdict(list)
    for r in score:
        by[r["class"]].append(r)
    rows = [["항목", "뜻", "전체"] + [CLASS_KR[c] for c in CLASSES]]
    for item in ITEMS:
        rows.append(
            [item, ITEM_DESC[item], f"{sum(r['ok'][item] for r in score)}/{len(score)}"]
            + [f"{sum(r['ok'][item] for r in by[c])}/{len(by[c])}" for c in CLASSES]
        )
    rows.append(
        [
            "전부",
            "모든 항목 맞음",
            f"{sum(all(r['ok'].values()) for r in score)}/{len(score)}",
        ]
        + [f"{sum(all(r['ok'].values()) for r in by[c])}/{len(by[c])}" for c in CLASSES]
    )

    def style(r, c):
        fill, color, bold, size, align = head_style(r, c)
        if r > 0 and c >= 2:
            a, b = rows[r][c].split("/")
            if a == b:
                fill, color = TEAL_TINT, TEAL
            elif int(a) < int(b) / 2:
                fill, color = ORANGE_TINT, ORANGE
            bold = c == 2
        return fill, color, bold, size, align

    table(s, X0, 1.85, CW, 4.3, rows, [1.2, 3.3, 1.133, 1.3, 1.3, 1.3, 1.3, 1.3], style)
    text(
        s, X0, 6.3, CW, 0.4, ["청록: 전부 맞음 · 주황: 절반 미만"], size=12, color=GRAY
    )


def baseline_slide(d, score):
    s = d.content(
        "이전 기준선과 비교",
        "같은 30개 부품, 같은 두 모델. 바뀐 것은 정답(회사 식)과 판독기 코드입니다.",
        "이전: 동료의 2026-10-18 실행, 이전 정답 세트. 이전 정답은 콘 · 경판 식이 틀려 "
        "전개 점수가 낮게 나왔다. 두 숫자를 같은 저울로 잰 것은 아니라는 점을 같이 말한다.",
    )
    ok = (lambda k: sum(r["ok"][k] for r in score)) if score else (lambda k: None)
    rows = [
        ["", "이전 (10-18)", "지금 (10-27)"],
        ["형상 맞힘", "27 / 30", f"{ok('형상')} / 30" if score else "-"],
        ["전개 1% 이내", "11 / 30", f"{ok('전개')} / 30" if score else "-"],
        ["단계별 점수", "없음 (형상 · 전개만)", "표제란 · 뷰 · 형상 · 치수 · 전개"],
        ["정답", "이전 세트 (콘 · 경판 식 틀림)", "회사 계산 기준으로 다시 만듦"],
    ]
    table(s, X0 + 1.0, 1.9, CW - 2.0, 3.4, rows, [3.0, 3.566, 3.567], head_style)
    band(
        s,
        5.65,
        "읽는 법",
        "형상을 답한 26장은 모두 맞았습니다. 못 맞힌 4장은 AI 답이 잘린 경우입니다. "
        "전개는 이제 정답이 맞으므로, 남은 오차는 실제로 판독이 틀린 것입니다",
        h=0.95,
        size=15,
    )


def example_slide(d):
    run = SCORE.parent
    work = next(iter(sorted(run.glob(f"**/{EXAMPLE}/flat_pattern.png"))), None)
    s = d.content(
        f"예시: {EXAMPLE} (콘)",
        "도면에서 뷰와 형상을 읽고, 회사 식으로 부채꼴을 계산해 전개도를 그립니다.",
        "왼쪽: 판독기가 찾은 뷰에 번호를 붙인 도면 그림 (06 단계). 오른쪽: 10 단계가 그린 전개도. "
        "대경 150, 소경 80, 높이 150, 두께 4 (SPHC). 판독 결과와 정답 모두 R₁ 321.26, R₂ 167.23, θ 81.80°.",
    )
    sheet = work.parent / "analysis" / "sheet_labeled.png" if work else Path("없음")
    picture(s, sheet, X0, 1.8, w=5.6)
    picture(s, work or Path("없음"), X0 + 6.6, 2.0, w=5.5)
    band(
        s,
        6.0,
        "결과",
        "R₁ 321.26 · R₂ 167.23 · θ 81.80° — 정답과 같음 (바깥 호 = 평균 원둘레 π × 146)",
        h=0.7,
        size=15,
    )


def limits_slide(d, score):
    s = d.content(
        "틀린 곳과 원인",
        "전개 계산 코드는 맞습니다. 틀린 곳은 AI 가 치수를 고르는 단계와 뷰 찾기에 몰려 있습니다.",
        "2026-10-27 실행의 도면별 원인 (score.md). 형상 미정 4장: 06 단계 AI 응답이 공백을 반복하거나 "
        "설명을 길게 쓰다 길이 제한(1500 토큰)에 걸려 JSON 이 잘렸다. 형상을 답한 26장은 모두 맞았다. "
        "콘: 대경을 외경 그대로 안지름 칸에 넣음(4장, 오차 5.6~23.5%). 굽힘판: 폭과 다리 길이를 바꿔 읽음(2장), "
        "굽힘 반경 0 을 두께로 읽음(2장). 경판: 2:1 타원형을 반구형으로 판단(4장), 외경을 안지름으로(1장), "
        "그리고 프로그램이 타원 끝을 직선부 2~4 mm 로 잘못 잼(6장). 뷰: 원만 있는 뷰(원통 우측면도, "
        "경판 평면도)를 뷰 후보로 못 잡음(12장), 평판 1장은 평면도를 저면도로.",
    )
    fails = defaultdict(int)
    for r in score or []:
        for k in r["why"]:
            fails[k] += 1
    lines = [
        (
            "응답 잘림",
            "4장: AI 의 답이 길이 제한에 걸려 잘려서 형상을 정하지 못했습니다. 답을 한 26장은 형상을 모두 맞혔습니다",
        ),
        (
            "치수 고르기",
            "콘 대경을 외경 그대로 씀(4장) · 경판을 반구형으로 봄(4장) · 굽힘판 폭과 다리 혼동(2장), 굽힘 반경을 두께로(2장)",
        ),
        (
            "뷰 찾기",
            "원만 있는 뷰(원통의 우측면도, 경판의 평면도)를 뷰로 잡지 못합니다 (12장, 프로그램 쪽)",
        ),
        (
            "경판 직선부",
            "새 타원 도면에서 프로그램이 타원 끝을 직선부 2~4 mm 로 잘못 잽니다 (6장, 프로그램 쪽)",
        ),
    ]
    for i, (head, body) in enumerate(lines):
        y = 1.9 + i * 1.12
        chip(
            s,
            X0,
            y + 0.1,
            1.6,
            0.62,
            head,
            fill=ORANGE,
            color=WHITE,
            size=15,
            bold=True,
        )
        text(
            s,
            X0 + 1.85,
            y + 0.05,
            CW - 1.85,
            0.9,
            [body],
            size=17,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    if fails:
        summary = " · ".join(f"{k} {v}장" for k, v in fails.items())
        text(
            s,
            X0,
            6.4,
            CW,
            0.4,
            [f"이번 실행에서 틀린 항목: {summary}"],
            size=13,
            color=GRAY,
        )


def next_slide(d):
    s = d.content(
        "다음 계획",
        "합성 30장을 모두 맞힌 뒤 실제 도면으로 넘어갑니다.",
        "1~2 는 이번 주, 3 은 회사 답변을 받은 뒤. 검산 예: 콘 대경 − 2t 가 정면도 아래 폭 − 2t 와 "
        "같은지, 경판 높이/지름 = 1/4 이면 2:1 타원형인지를 코드가 확인한다.",
    )
    steps = [
        (
            "1",
            "AI 답을 코드로 검산",
            "AI 가 고른 치수를 도면 외형 치수와 대조 (외경 ↔ 안지름, 경판 높이/지름으로 형식 판정), 잘린 답은 다시 묻기",
        ),
        (
            "2",
            "프로그램 고치기 · 다시 재기",
            "원만 있는 뷰 찾기, 경판 직선부 측정을 고친 뒤 같은 30장을 다시 돌려 점수가 다시 나오는지 확인",
        ),
        (
            "3",
            "실제 도면",
            "받은 설비 도면 2건(S-2120, D-1203)의 부품을 같은 방법으로 판독해 커팅플랜과 대조",
        ),
    ]
    for i, (n, head, body) in enumerate(steps):
        y = 1.95 + i * 1.45
        chip(s, X0, y, 0.8, 0.8, n, fill=TEAL, color=WHITE, size=22, bold=True)
        text(s, X0 + 1.1, y - 0.05, CW - 1.1, 0.45, [head], size=19, bold=True)
        text(s, X0 + 1.1, y + 0.42, CW - 1.1, 0.6, [body], size=16, color=GRAY)


def questions_slide(d):
    s = d.content(
        "확인을 부탁드립니다",
        "답에 따라 정답과 계산 코드가 바로 바뀌는 것들입니다.",
        "자세한 근거는 같이 보내는 문서의 8절.",
    )
    qs = [
        (
            "계산 기준",
            "주신 계산 문서의 식(평균지름 원칙, 경판 1.2 × Dm, 트림 20~50 mm)이 회사 실제 기준이 맞나요?",
        ),
        (
            "콘 지름",
            "받은 커팅플랜(D-1203)의 콘은 안지름으로 전개돼 있었습니다. 콘은 안지름 기준인가요, 평균지름 기준인가요?",
        ),
        (
            "경판 원판",
            "원판 지름에 더하는 트림 여유는 몇 mm 인가요? 원판 치수는 회사가 정하나요, 성형업체가 정하나요?",
        ),
        (
            "굽힘 K",
            "굽힘판 K 계수 0.33 / 0.40 / 0.50 (R/t 구간별)이 회사 기준과 맞나요?",
        ),
    ]
    for i, (head, body) in enumerate(qs):
        y = 1.9 + i * 1.15
        chip(
            s, X0, y + 0.1, 1.7, 0.62, head, fill=TEAL, color=WHITE, size=15, bold=True
        )
        text(
            s,
            X0 + 1.95,
            y + 0.02,
            CW - 1.95,
            0.95,
            [body],
            size=17,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", type=Path, default=SCORE)
    args = ap.parse_args()
    score = (
        json.loads(args.score.read_text(encoding="utf-8"))
        if args.score.is_file()
        else None
    )
    d = Deck(OUT, TITLE, FOOTER)
    title_slide(d)
    summary_slide(d, score)
    process_slide(d)
    data_slide(d)
    formula_slide(d)
    fixes_slide(d)
    results_slide(d, score)
    baseline_slide(d, score)
    example_slide(d)
    limits_slide(d, score)
    next_slide(d)
    questions_slide(d)
    print(d.save())


if __name__ == "__main__":
    main()
