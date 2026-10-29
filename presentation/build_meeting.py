"""PBL 미팅 (2026-10-30): 합성 도면 고도화 전 → 후, 하네스 동작, 다음 단계 v4 → meeting.pptx

계획과 숫자의 출처는 docs/pbl_meeting.md 와 docs/presentation.md 8절. 청중은 교수님과 PBL
회사 사람들이다. 합성 도면과 집계 숫자만 쓰고 고객 도면은 싣지 않는다.

변천사 세 단계 (docs/pbl_meeting.md 2절):
  ① synthetic / cutplan_v3 : 동료 v3 253020c, 옛 합성 30장. RUN1 (동료 2026-10-18 실행)
  ② synthetic / reader     : c71cca0. 이 서버에 실행 기록이 없어 다시 돌릴 때까지 자리만 둔다
  ③ generated / reader+    : RUN3 (2026-10-28 04:23, 다시 묻기 3cf2274 뒤, 현업자 기준 식
                             2807e44 · 경판 직선부 f111ea8 전). RUN3_PRE 는 다시 묻기 전 (10-27)

그림은 빌드할 때 실행 폴더에서 읽는다 (scripts/reader/show_stages.py 가 그린 figures/,
analysis/*.png, flat_pattern.png). 없으면 회색 상자가 들어간다.

사용 (레포 루트에서):
  PYTHONPATH=. uv run --with python-pptx python presentation/build_meeting.py
"""

import json
from pathlib import Path

from PIL import Image
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from presentation.slides import (
    CW,
    GRAY,
    INK,
    LIGHT,
    ORANGE,
    ORANGE_TINT,
    PALE,
    TEAL,
    TEAL_TINT,
    WHITE,
    X0,
    Deck,
    arrow,
    band,
    card,
    code,
    connect,
    dashed,
    outline,
    page,
    picture,
    real_sheet,
    road,
    shape,
    table,
    text,
    write,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "meeting.pptx"
RUNS = ROOT / "runs" / "reader"
RUN1 = RUNS / "deepseek_ocr_qwen_reasoning_skills"
RUN3 = RUNS / "company_synthetic_20261028_042351"
RUN3_PRE = RUNS / "gen1027" / "local_new"
FIG = ROOT / "docs" / "data" / "synthetic"
ASSETS = ROOT / "presentation" / "build" / "assets"
TITLE = "도면 판독 하네스: 합성 도면 고도화 전 → 후"
FOOTER = "PBL · 도면 판독 → 전개도 · 2026-10-30"

PARTS = ["용어", "판독 과정", "지난주", "하네스", "전 → 후", "실험", "v4"]
ITEMS = ["단계", "표제란", "뷰", "형상", "치수", "전개", "전부"]
ITEM_DESC = {
    "단계": "01~10 이 오류 없이 끝남",
    "표제란": "도면 번호 · 축척 · 재질 · 두께",
    "뷰": "정면 · 평면 · 우측면 이름",
    "형상": "5형상 중 맞는 것",
    "치수": "전개에 쓴 치수",
    "전개": "전개 값 오차 1% 이내",
    "전부": "위 여섯이 모두 맞음",
}
CLASSES = ["flat", "bent_sheet", "cylinder", "cone", "press_formed"]
CLASS_KR = {
    "flat": "평판",
    "bent_sheet": "굽힘판",
    "cylinder": "원통",
    "cone": "콘",
    "press_formed": "경판",
}
# 형상마다 전 → 후 를 보일 도면. ③ 에서 모든 항목을 맞힌 도면을 우선 골랐다 (cylinder ·
# press_formed 는 그런 도면이 없어 뷰만 틀린 것)
SHOWCASE = {
    "flat": "flat_0001",
    "bent_sheet": "bent_sheet_0012",
    "cylinder": "cylinder_0014",
    "cone": "cone_0023",
    "press_formed": "press_formed_0028",
}
EXAMPLE = "cone_0023"  # 하네스 파트에서 단계를 따라갈 도면 (③ 에서 모두 맞음)

# ① 동료 실행의 숫자 (RUN1 의 accuracy.md, flat_patterns.md)
RUN1_SHAPE = {"flat": 5, "bent_sheet": 6, "cylinder": 4, "cone": 6, "press_formed": 6}
RUN1_FLAT = {"flat": 5, "bent_sheet": 2, "cylinder": 4, "cone": 0, "press_formed": 0}


def chip(s, x, y, w, h, label, *, fill=LIGHT, color=INK, size=13, bold=False):
    """Like slides.chip, but each line of a multi-line label is its own centered paragraph
    (a line break inside one run renders off-center in LibreOffice)."""
    sp = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill, radius=0.15)
    write(
        sp.text_frame,
        [{"text": line, "bold": bold} for line in label.split("\n")],
        size=size,
        color=color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=0,
        margin=0.05,
    )
    return sp


# ---------------------------------------------------------------------- data
def workdir(run: Path, drawing: str) -> Path:
    """The work folder of one drawing in a batch run (batch_parallel.sh splits into shards)."""
    found = sorted(run.glob(f"**/{drawing}/prediction.json"))
    return found[0].parent if found else run / drawing


def load_score(run: Path):
    path = run / "score.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def count(score, item, cls=None):
    if score is None:
        return None
    rows = [r for r in score if cls is None or r["class"] == cls]
    if item == "전부":
        return sum(all(r["ok"].values()) for r in rows)
    return sum(r["ok"][item] for r in rows)


def frac(n, total=30):
    return "–" if n is None else f"{n}/{total}"


def stage_json(run: Path, drawing: str, name: str):
    path = workdir(run, drawing) / "stages" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def develop_plot(run: Path, drawing: str) -> Path:
    """The left half of figures/10_develop.png (calculated outline over the label), so it
    can be shown large. Written to presentation/build/assets/."""
    src = workdir(run, drawing) / "figures" / "10_develop.png"
    out = ASSETS / f"{run.name}_{drawing}_develop.png"
    if src.is_file() and not out.is_file():
        ASSETS.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im.crop((0, int(im.height * 0.2), int(im.width * 0.47), im.height)).save(
                out
            )
    return out if out.is_file() else src


def params_table(s, run, drawing, x, y, w):
    """The parameters stage 09 handed to stage 10, and who filled each (AI or code)."""
    record = stage_json(run, drawing, "09_unfold_params").get("record", {})
    rows = [["치수", "값", "누가"]]
    for key, value in (record.get("params") or {}).items():
        if isinstance(value, float):
            value = f"{value:.1f}"
        elif isinstance(value, list):
            value = ", ".join(f"{v:g}" for v in value)
        source = (record.get("sources") or {}).get(key, "")
        rows.append([key, str(value), "AI" if source.startswith("vlm") else "코드"])

    def style(r, c):
        if r == 0:
            return TEAL, WHITE, True, 14, PP_ALIGN.CENTER
        ai = rows[r][2] == "AI"
        fill = (
            (ORANGE_TINT if ai else TEAL_TINT)
            if c == 2
            else (LIGHT if r % 2 else WHITE)
        )
        return fill, INK, c == 2, 14, PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER

    table(s, x, y, w, 0.45 * len(rows), rows, [w * 0.45, w * 0.33, w * 0.22], style)
    return record


# ---------------------------------------------------------------------- layout helpers
def fit(s, path, x, y, w, h):
    """A picture fitted inside the box, centered, keeping its aspect ratio."""
    path = Path(path)
    if not path.is_file():
        return picture(s, path, x, y, w, h)
    with Image.open(path) as im:
        ratio = im.width / im.height
    pw, ph = (w, w / ratio) if w / ratio <= h else (h * ratio, h)
    return picture(s, path, x + (w - pw) / 2, y + (h - ph) / 2, pw, ph)


def caption(s, x, y, w, label, *, fill=LIGHT, color=INK, h=0.4, size=14):
    chip(s, x, y, w, h, label, fill=fill, color=color, size=size, bold=True)


def head_style(r, c):
    if r == 0:
        return TEAL, WHITE, True, 14, PP_ALIGN.CENTER
    return (
        LIGHT if r % 2 else WHITE,
        INK,
        c == 0,
        14,
        PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER,
    )


def bullets(s, x, y, w, h, items, size=18):
    text(
        s, x, y, w, h, [{"text": t, "bullet": True} for t in items], size=size, after=10
    )


def section(d, number, title, sub, notes):
    s = d.slide(notes, dark=True)
    text(s, X0, 2.4, CW, 0.8, [number], size=22, color=ORANGE, bold=True)
    text(s, X0, 3.0, CW, 1.0, [title], size=40, bold=True, color=WHITE)
    text(s, X0, 4.1, CW, 0.6, [sub], size=20, color=PALE)
    return s


def slide(d, part, title, message, notes):
    s = d.content(title, message, notes)
    road(s, part, PARTS)
    return s


def before_after(s, left, right, *, y=1.85, h=4.2, labels=("전", "후")):
    """Two pictures side by side with a 전/후 chip on each and an arrow between."""
    w = 5.75
    for i, (path, sub) in enumerate((left, right)):
        x = X0 + i * (w + 0.63)
        fill, color = (LIGHT, GRAY) if i == 0 else (ORANGE, WHITE)
        caption(s, x, y, 0.8, labels[i], fill=fill, color=color)
        text(s, x + 0.95, y + 0.02, w - 0.95, 0.4, [sub], size=14, color=GRAY)
        fit(s, path, x, y + 0.5, w, h)
    arrow(s, X0 + w + 0.15, y + 0.5 + h / 2 - 0.16, w=0.33, h=0.32)


# ---------------------------------------------------------------------- A. 도입
def title_slide(d):
    s = d.slide(
        "PBL 미팅. 중간보고 뒤 합성 도면을 고친 것, 판독 하네스가 어떻게 도는지, 다음 단계(v4).",
        dark=True,
    )
    text(s, X0, 1.9, CW, 1.2, ["도면 판독 하네스"], size=44, bold=True, color=WHITE)
    text(
        s,
        X0,
        3.0,
        CW,
        0.6,
        ["합성 도면 고도화: 전 → 후, 그리고 v4"],
        size=26,
        color=ORANGE,
    )
    text(s, X0, 5.6, CW, 0.5, ["2026-10-30 · PBL"], size=16, color=WHITE)


def agenda_slide(d):
    s = slide(
        d,
        0,
        "오늘 이야기",
        "처음 오신 분도 따라오실 수 있게, 용어와 예시부터 시작합니다",
        "여섯 부분. 앞의 용어 · 판독 과정은 처음 오신 분을 위한 것이다.",
    )
    rows = [
        ("용어", "설계 도면, 형상, 전개, 정답, reader, 하네스가 무엇인지"),
        ("판독 과정", "예시 도면 한 장을 reader 에 넣으면 단계마다 무엇이 나오나"),
        ("지난주", "지난주까지의 범위와 성능, 성공 · 실패 사례, 드러난 문제"),
        ("하네스", "AI 를 감싸는 장치: 답 양식, 다시 묻기, 기록"),
        ("전 → 후", "데이터와 코드를 어떻게 고쳤고 결과가 어떻게 달라졌나"),
        ("실험 · v4", "진행 중인 실험 두 가지, 그리고 실제 도면을 읽는 다음 단계"),
    ]
    for i, (head, body) in enumerate(rows):
        y = 1.85 + i * 0.8
        chip(
            s,
            X0,
            y,
            0.6,
            0.62,
            str(i + 1),
            fill=ORANGE,
            color=WHITE,
            size=18,
            bold=True,
        )
        chip(
            s, X0 + 0.75, y, 2.2, 0.62, head, fill=TEAL, color=WHITE, size=17, bold=True
        )
        text(s, X0 + 3.2, y, 8.9, 0.62, [body], size=18, anchor=MSO_ANCHOR.MIDDLE)


def summary_slide(d, s3):
    s = slide(
        d,
        4,
        "이번 결과 한 장 요약",
        "정답 데이터를 고친 뒤 다시 쟀습니다. 형상(부품 종류)은 30/30, 전개(펼친 크기)는 18/30",
        "① 은 옛 정답, ③ 은 새 정답으로 잰 숫자라 같은 기준이 아니다. 같은 정답으로 나눈 비교(2×2)는"
        " 다시 돌린 뒤 넣는다 (docs/pbl_meeting.md 3절). ③ 은 2026-10-28 04:23 실행.",
    )
    cols = [
        (
            "① 지난주",
            "옛 합성 / 동료 v3",
            TEAL_TINT,
            [("형상", "27/30"), ("전개", "11/30")],
            "단계별 기록 없음",
        ),
        (
            "② 단계로 나눔",
            "옛 합성 / reader",
            LIGHT,
            [("형상", "다시 잼"), ("전개", "다시 잼")],
            "13단계, 단계마다 파일",
        ),
        (
            "③ 지금",
            "새 합성 / reader+",
            ORANGE_TINT,
            [("형상", frac(count(s3, "형상"))), ("전개", frac(count(s3, "전개")))],
            f"단계 {frac(count(s3, '단계'))} · 전부 {frac(count(s3, '전부'))}",
        ),
    ]
    for i, (head, sub, fill, nums, foot) in enumerate(cols):
        x = X0 + i * 4.15
        card(s, x, 1.85, 3.75, 4.3, [], fill=fill)
        text(s, x + 0.25, 2.0, 3.3, 0.5, [head], size=22, bold=True)
        text(s, x + 0.25, 2.55, 3.3, 0.4, [sub], size=15, color=GRAY)
        for j, (k, v) in enumerate(nums):
            text(
                s,
                x + 0.25,
                3.15 + j * 1.0,
                1.2,
                0.8,
                [k],
                size=18,
                anchor=MSO_ANCHOR.MIDDLE,
            )
            text(
                s,
                x + 1.3,
                3.15 + j * 1.0,
                2.2,
                0.8,
                [v],
                size=32,
                bold=True,
                color=TEAL if i < 2 else ORANGE,
                anchor=MSO_ANCHOR.MIDDLE,
            )
        text(s, x + 0.25, 5.4, 3.3, 0.6, [foot], size=14, color=GRAY)
        if i < 2:
            arrow(s, x + 3.8, 3.85, w=0.3, h=0.3)
    text(
        s,
        X0,
        6.3,
        CW,
        0.5,
        ["①과 ③은 채점에 쓴 정답이 다릅니다. 같은 정답으로 다시 잰 비교는 뒤에서"],
        size=14,
        color=GRAY,
    )


def goal_change_slide(d):
    s = slide(
        d,
        2,
        "그래서 목표를 바꿨습니다: v3 고도화",
        "실제 도면으로 가기 전에, 쉬운 합성 도면에서 모든 단계를 정답과 맞게 끝까지 돌립니다",
        "docs/v3_upgrade.md 1절. 지난 미팅 뒤 교수님 피드백으로 목표를 v3 고도화로 바꿨다.",
    )
    card(
        s,
        X0,
        1.9,
        5.7,
        3.6,
        [
            {"text": "지난주까지", "bold": True, "color": GRAY, "size": 20},
            {"text": "합성 30장: 형상 27/30, 전개 11/30", "bullet": True},
            {"text": "다음 일은 실제 도면 (v4)", "bullet": True},
            {"text": "단계별로 맞았는지 숫자가 없음", "bullet": True},
        ],
        size=18,
        after=10,
    )
    card(
        s,
        X0 + 6.4,
        1.9,
        5.73,
        3.6,
        [
            {
                "text": "이번 주부터 (v3 고도화)",
                "bold": True,
                "color": ORANGE,
                "size": 20,
            },
            {"text": "합성 30장을 모든 단계에서 정답과 맞게 완주", "bullet": True},
            {
                "text": "단계마다 채점 (표제란 · 뷰 · 형상 · 치수 · 전개)",
                "bullet": True,
            },
            {"text": "v4 는 그 다음으로 미룸", "bullet": True},
        ],
        fill=ORANGE_TINT,
        size=18,
        after=10,
    )
    arrow(s, X0 + 5.82, 3.55, w=0.45, h=0.4)
    band(
        s,
        5.8,
        "왜",
        "정답이 다 있는 쉬운 세트에서 끝까지 못 맞히면, 틀린 원인이 모델인지 하네스인지 코드인지 데이터인지 가릴 수 없습니다",
    )


def scope_slide(d):
    s = slide(
        d,
        2,
        "범위: 도면 → 전개도",
        "3D 복원(11~13)은 뺐습니다. 코드는 남기고 실행에서만 끕니다 (--with-3d 로 다시 켬)",
        "docs/v3_upgrade.md 1.1절. 2026-10-27 결정, 커밋 2b09587. 08 document 가 3D 쪽 모델 클래스를 같이 써서 코드는 지우지 않았다.",
    )
    names = [
        "읽기",
        "표제란\n정규식",
        "표제란\nOCR",
        "표제란\n정리",
        "뷰\n찾기",
        "뷰 이름\n· 형상",
        "합치기",
        "구조화",
        "치수",
        "전개",
        "3D\n후보",
        "후보\n고르기",
        "내보내기",
    ]
    w, gap = 0.86, 0.06
    for i, name in enumerate(names):
        x = X0 + i * (w + gap)
        on = i < 10
        chip(
            s,
            x,
            2.3,
            w,
            0.45,
            f"{i + 1:02d}",
            fill=TEAL if on else LIGHT,
            color=WHITE if on else GRAY,
            size=14,
            bold=True,
        )
        card(
            s,
            x,
            2.85,
            w,
            1.2,
            [name],
            fill=TEAL_TINT if on else LIGHT,
            color=INK if on else GRAY,
            size=12,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.03,
        )
    text(
        s,
        X0,
        4.25,
        9.2,
        0.5,
        ["이번 범위: 01~10, 결과는 전개도 (flat_pattern.dxf · png)"],
        size=17,
        color=TEAL,
        bold=True,
    )
    text(s, X0 + 9.3, 4.25, 3.0, 0.5, ["뺌: 11~13"], size=17, color=GRAY, bold=True)
    band(
        s,
        5.3,
        "이유",
        "커팅플랜에 필요한 것은 판의 전개 모양과 크기입니다. 3D 모양은 그 다음 일이라, 전개도까지 먼저 정확히 맞힙니다",
    )


# ---------------------------------------------------------------------- B. 배경
# ---------------------------------------------------------------------- C. 하네스
STAGES = [
    ("01", "읽기", "DXF → 선 · 글자 목록", False),
    ("02", "표제란 정규식", "글자 → 표제란 칸", False),
    ("03", "표제란 OCR", "표제란 그림 → 글자", True),
    ("04", "표제란 정리", "글자 → 빈칸 채움", True),
    ("05", "뷰 찾기", "선 → 뷰 후보", False),
    ("06", "뷰 이름 · 형상", "그림 → 이름 · 형상", True),
    ("07", "합치기", "결과들 → 한 파일", False),
    ("08", "구조화", "뷰 → 정면 · 평면 · 측면", False),
    ("09", "치수", "그림 → 전개 치수", True),
    ("10", "전개", "치수 → 전개도", False),
]


def harness_section(d):
    section(
        d,
        "2",
        "판독 과정",
        "예시 도면 한 장(cone_0023)을 reader 에 넣으면",
        "코드 대신 그림으로 판독기의 동작을 보인다. 예시 도면은 cone_0023 (③ 에서 모두 맞힌 도면).",
    )


def flow_slide(d):
    s = slide(
        d,
        1,
        "전체 흐름: 10단계",
        "cone_0023 을 넣으면 10단계를 거쳐 전개도가 나옵니다. AI 는 네 곳(주황)에서만 읽고 고릅니다",
        "docs/reader/stages.md 2절. 모델 단계는 03 (OCR), 04 · 06 · 09 (판단). 11~13 은 꺼져 있다.",
    )
    w, h = 2.25, 1.55
    for i, (num, name, desc, ai) in enumerate(STAGES):
        row, col = divmod(i, 5)
        x = X0 + col * (w + 0.22)
        y = 1.95 + row * 2.2
        fill = ORANGE if ai else TEAL
        card(
            s,
            x,
            y,
            w,
            h,
            [
                {"text": f"{num}  {name}", "bold": True, "size": 16, "color": WHITE},
                {"text": desc, "size": 13, "color": WHITE},
            ],
            fill=fill,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.14,
        )
        if col < 4:
            arrow(s, x + w + 0.01, y + h / 2 - 0.1, w=0.2, h=0.2, fill=PALE)
    chip(
        s, X0, 6.4, 1.5, 0.38, "AI (모델)", fill=ORANGE, color=WHITE, size=13, bold=True
    )
    chip(
        s, X0 + 1.65, 6.4, 1.5, 0.38, "코드", fill=TEAL, color=WHITE, size=13, bold=True
    )
    text(
        s,
        X0 + 3.35,
        6.38,
        8.5,
        0.4,
        ["입력 DXF 한 장 → 전개도 (flat_pattern.dxf · png)"],
        size=14,
        color=GRAY,
    )


def rules_slide(d):
    s = slide(
        d,
        3,
        "규칙 셋",
        "단계마다 결과를 파일로 남기고, 다음 단계는 그 파일만 읽습니다",
        "docs/reader/stages.md 머리말. main.py --batch 도 같은 단계들을 차례로 부른다. tests/test_stages.py 가 한 번에 돌린 결과와 단계별로 돌린 결과가 같음을 확인한다.",
    )
    for i, n in enumerate(["05", "06", "07"]):
        x = X0 + 0.3 + i * 3.0
        chip(
            s,
            x,
            2.1,
            1.3,
            0.8,
            n,
            fill=ORANGE if n == "06" else TEAL,
            color=WHITE,
            size=20,
            bold=True,
        )
        page(s, x + 1.55, 2.0, 0.75, 1.0)
        text(
            s,
            x + 1.3,
            3.05,
            1.3,
            0.3,
            [f"{n}_*.json"],
            size=11,
            color=GRAY,
            align=PP_ALIGN.CENTER,
        )
        if i < 2:
            arrow(s, x + 2.45, 2.35, w=0.4, h=0.3, fill=PALE)
    rows = [
        (
            "단계마다 파일 하나",
            "stages/NN_<단계>.json 에 결과, 읽은 파일, 모델 호출 기록",
        ),
        (
            "앞 단계 파일만 읽는다",
            "단계 사이의 약속은 파일뿐. 코드끼리 엉키지 않습니다",
        ),
        (
            "한 단계만 다시",
            "06 만 다른 모델로 다시 돌려 비교할 수 있습니다. 모델 실험의 바탕",
        ),
    ]
    for i, (head, body) in enumerate(rows):
        y = 3.75 + i * 0.95
        chip(s, X0, y, 3.2, 0.75, head, fill=TEAL_TINT, color=TEAL, size=16, bold=True)
        text(s, X0 + 3.4, y, 8.7, 0.75, [body], size=17, anchor=MSO_ANCHOR.MIDDLE)


def stage_file_slide(d):
    s = slide(
        d,
        3,
        "단계 파일 속",
        "모델 단계는 무엇을 보여 줬고 무엇을 답했는지가 그대로 남습니다",
        "06_view_labels.json 의 모양을 줄여 보인 것. 필드 뜻은 docs/reader/stages.md 1절.",
    )
    code(
        s,
        X0,
        1.85,
        6.6,
        4.9,
        [
            "{",
            '  "stage": "view_labels",  "step": 6,',
            '  "status": "done",',
            '  "inputs": ["stages/01_read.json",',
            '             "stages/05_views.json"],',
            '  "views": [{"id": 1, "label": "front"}, ...],',
            '  "trace": {"reason": [{',
            '    "model": "Qwen/Qwen3.6-27B",',
            '    "images": ["analysis/sheet_labeled.png"],',
            '    "skills": [{"name": "unfold_rules",',
            '                "sha256": "…"}],',
            '    "raw": "{\\"part_class\\": \\"cone\\", …}",',
            '    "finish_reason": "stop",  "ok": true',
            "  }]}",
            "}",
        ],
        size=13,
    )
    rows = [
        ("status", "done · skipped · failed"),
        ("inputs", "읽은 앞 단계 파일"),
        ("model · images", "누구에게 무엇을 보였나"),
        ("skills · sha256", "붙인 참고 문서와 그 판"),
        ("raw · ok", "모델 원문과 검사 통과 여부"),
        ("finish_reason", "끝까지 답했나, 잘렸나"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.95 + i * 0.78
        chip(s, X0 + 6.9, y, 2.2, 0.6, k, fill=LIGHT, color=TEAL, size=13, bold=True)
        text(s, X0 + 9.25, y, 2.9, 0.6, [v], size=14, anchor=MSO_ANCHOR.MIDDLE)


def guard_retry_slide(d, pre, s3):
    s = slide(
        d,
        3,
        "하네스 장치 2: 잘리면 짧게 다시 묻기",
        "답이 길이 제한(1,500 토큰)에서 잘리면, 이유를 한 문장으로 줄여 한 번 더 묻습니다",
        "커밋 3cf2274 (2026-10-28), reader/vlm.py SHORTER_RETRY. 숫자는 두 실행의 단계 파일 trace 에서 셌다 (docs/pbl_meeting.md 4.1절): "
        "10-27 runs/reader/gen1027/local_new 는 06 4건 · 09 3건 JSONDecodeError, 10-28 company_synthetic_20261028_042351 은 4건 잘림 모두 다시 물어 성공. "
        "판단 서버에는 JSON 사이 공백 반복을 막는 disable_any_whitespace 도 넣었다.",
    )
    for i, (head, body, fill) in enumerate(
        [
            ("묻기", "", LIGHT),
            ("잘림?", "finish_reason\n= length", ORANGE_TINT),
            ("다시 묻기", '"이유는 한 문장"', TEAL_TINT),
        ]
    ):
        x = X0 + i * 2.6
        card(
            s,
            x,
            1.95,
            2.2,
            1.4,
            [{"text": head, "bold": True, "size": 18}, {"text": body, "size": 13}],
            fill=fill,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if i < 2:
            arrow(s, x + 2.25, 2.5, w=0.3, h=0.3)
    rows = [
        ["", "다시 묻기 전 (10-27)", "다시 묻기 뒤 (10-28)"],
        ["판단 호출 (06 · 09)", "60", "60"],
        ["잘려서 실패", "7", "0"],
        ["잘렸지만 다시 물어 성공", "–", "4"],
        ["단계 01~10 완주", frac(count(pre, "단계")), frac(count(s3, "단계"))],
        ["형상", frac(count(pre, "형상")), frac(count(s3, "형상"))],
    ]
    table(
        s,
        X0 + 7.9,
        1.95,
        4.23,
        3.6,
        rows,
        [1.85, 1.19, 1.19],
        lambda r, c: (
            (TEAL, WHITE, True, 12, PP_ALIGN.CENTER)
            if r == 0
            else (
                LIGHT if r % 2 else WHITE,
                ORANGE if (c == 2 and r in (2, 4, 5)) else INK,
                c != 1 and r in (2, 4, 5),
                13,
                PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER,
            )
        ),
    )
    band(
        s,
        5.85,
        "아직",
        "잘림 자체는 그대로입니다 (30장에 4번). 근본 처리는 따로 진행 중 → 실험 파트",
        h=0.8,
        size=16,
    )
    code(
        s,
        X0,
        3.6,
        7.6,
        1.6,
        [
            "잘린 답의 끝 (press_formed_0027, 09):",
            '"… If ID=200, OD=212. Depth of 2:1 ellip = 50.',
            " Total = 56. Still not 59. Let's",
        ],
        size=13,
    )


def guard_trace_slide(d):
    s = slide(
        d,
        3,
        "하네스 장치 3: 기록",
        "단계마다 남긴 파일로, 틀린 원인을 단계 하나로 짚습니다",
        "예: cone_0019 의 전개 15.7% 오차는 09 에서 모델이 대경 150 (바깥지름)을 안지름 칸에 넣은 것 (v3_upgrade.md 4절 #14). 기록이 없으면 '전개가 틀렸다' 까지만 안다.",
    )
    chain = [
        ("10 전개", "오차 15.7%", GRAY),
        ("09 치수", "안지름 = 150 ← AI", ORANGE),
        ("도면", "바깥지름 150", TEAL),
    ]
    for i, (head, body, c) in enumerate(chain):
        x = X0 + i * 4.15
        card(
            s,
            x,
            2.0,
            3.6,
            1.6,
            [
                {"text": head, "bold": True, "size": 20, "color": WHITE},
                {"text": body, "size": 16, "color": WHITE},
            ],
            fill=c,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if i < 2:
            arrow(
                s, x + 3.68, 2.62, w=0.4, h=0.35, kind=MSO_SHAPE.LEFT_ARROW, fill=PALE
            )
    text(
        s,
        X0,
        3.7,
        CW,
        0.4,
        ["거꾸로 따라가기: 결과 → 그 값을 낸 단계 → 그 단계가 본 것 (cone_0019)"],
        size=14,
        color=GRAY,
    )
    rows = [
        ("무엇을 보여 줬나", "입력 그림 경로, 참고 문서 이름과 sha256"),
        ("무엇이라 답했나", "모델 원문, 검사한 답, 잘렸는지"),
        ("누가 채웠나", "칸마다 모델 / 코드 / 정규식"),
        ("얼마나 걸렸나", "호출마다 시간"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 4.3 + i * 0.6
        chip(s, X0, y, 2.6, 0.48, k, fill=TEAL_TINT, color=TEAL, size=14, bold=True)
        text(s, X0 + 2.8, y, 9.3, 0.48, [v], size=15, anchor=MSO_ANCHOR.MIDDLE)


# ---------------------------------------------------------------------- D. 전 → 후
def change_section(d):
    section(
        d,
        "5",
        "전 → 후",
        "합성 데이터와 판독 코드가 어떻게 바뀌었나",
        "변천사 세 단계와 결과.",
    )


def history_slide(d):
    s = slide(
        d,
        4,
        "변천사 세 단계",
        "①→② 는 코드만, ②→③ 은 코드와 데이터(정답)가 같이 바뀌었습니다",
        "docs/pbl_meeting.md 2절. ① 동료 v3 253020c, ② c71cca0 (2026-10-23 main), ③ main (3D 끔, 새 생성기, 현업자 기준 식, 다시 묻기).",
    )
    cols = [
        (
            "①",
            "synthetic / cutplan_v3",
            "동료 v3 (253020c)",
            ["옛 합성 30장", "한 번에 도는 판독기", "단계별 기록 없음"],
            LIGHT,
        ),
        (
            "②",
            "synthetic / reader",
            "2026-10-23",
            [
                "판독을 13단계로 (단계마다 파일)",
                "DWG → DXF 단계 00",
                "AI 가 단계를 고르는 시제품",
            ],
            TEAL_TINT,
        ),
        (
            "③",
            "generated / reader+",
            "지금",
            [
                "3D 끔 (01~10)",
                "생성기를 새로 쓰고 정답을 고침",
                "현업자 기준 식, 잘리면 다시 묻기",
            ],
            ORANGE_TINT,
        ),
    ]
    for i, (n, head, sub, items, fill) in enumerate(cols):
        x = X0 + i * 4.15
        card(s, x, 1.85, 3.75, 4.5, [], fill=fill)
        chip(
            s,
            x + 0.2,
            2.0,
            0.7,
            0.7,
            n,
            fill=ORANGE if i == 2 else TEAL,
            color=WHITE,
            size=22,
            bold=True,
        )
        text(s, x + 1.05, 2.0, 2.6, 0.4, [head], size=16, bold=True)
        text(s, x + 1.05, 2.4, 2.6, 0.4, [sub], size=13, color=GRAY)
        bullets(s, x + 0.2, 3.0, 3.4, 3.2, items, size=16)
        if i < 2:
            arrow(s, x + 3.8, 3.9, w=0.3, h=0.3)


def stages_split_slide(d):
    s = slide(
        d,
        4,
        "① → ②: 단계로 나눈 것",
        "점수는 그대로여도, 어디서 틀렸는지 보이게 됐습니다 (지난 발표와 겹침)",
        "docs/reader/stages.md. 2026-10-22 reader-stages. 결과가 바뀌지 않게 나눴고, 전후 출력을 비교해 커밋 메시지에 적었다.",
    )
    card(
        s,
        X0,
        1.9,
        5.6,
        3.3,
        [
            {"text": "①", "bold": True, "size": 20},
            {"text": "도면 → [판독기] → 결과", "size": 18},
            {"text": "틀리면 처음부터 다시 돌려 봐야 함", "size": 16, "color": GRAY},
        ],
        fill=LIGHT,
        anchor=MSO_ANCHOR.MIDDLE,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, X0 + 5.75, 3.35, w=0.45, h=0.4)
    card(
        s,
        X0 + 6.4,
        1.9,
        5.73,
        3.3,
        [
            {"text": "②", "bold": True, "size": 20},
            {"text": "01 → 02 → … → 13, 단계마다 파일", "size": 18},
            {
                "text": "한 단계만 다시 · 단계별 채점 · 모델 기록",
                "size": 16,
                "color": GRAY,
            },
        ],
        fill=TEAL_TINT,
        anchor=MSO_ANCHOR.MIDDLE,
        align=PP_ALIGN.CENTER,
    )
    band(
        s,
        5.5,
        "덕분에",
        "아래 '정답이 틀려 있었다' 를 찾았습니다. 단계별 채점이 정답의 오류를 드러냈습니다",
    )


def wrong_ruler_slide(d):
    s = slide(
        d,
        4,
        "정답이 틀려 있었다",
        "옛 합성 도면의 정답 일부가 회사 계산 방식과 달랐습니다. 그래서 정답부터 고쳤습니다",
        "docs/v3_upgrade.md 4절 #2~#5. 옛 생성기(make_data_v3.py)는 남아 있지 않아 scripts/build_synthetic.py 를 새로 썼다 (docs/data/synthetic.md). ① 의 콘 · 경판 전개 0/6 은 판독기만의 잘못이 아니다.",
    )
    rows = [
        ["형상", "옛 정답", "고친 정답"],
        [
            "콘",
            "반경을 바깥지름으로, 각도 식이 다름",
            "두께 가운데 지름, θ = 360° · sin α",
        ],
        ["경판", "원판 지름 계수 1.3415", "두께 가운데 반타원 길이 + 직선부 × 2"],
        ["굽힘판", "K 계수 0.40, 굽힘선이 시작점", "K 0.33 (회사 규칙), 굽힘부 가운데"],
    ]
    table(s, X0, 1.9, CW, 2.4, rows, [1.6, 5.0, 5.533], head_style)
    rows = [
        ["① 전개 맞음 (옛 정답 기준)"] + [CLASS_KR[c] for c in CLASSES],
        [""] + [f"{RUN1_FLAT[c]}/6" for c in CLASSES],
    ]
    table(
        s,
        X0,
        4.6,
        CW,
        0.9,
        rows,
        [3.633] + [1.7] * 5,
        lambda r, c: (
            (TEAL, WHITE, True, 13, PP_ALIGN.CENTER)
            if r == 0
            else (
                WHITE,
                ORANGE if c in (4, 5) else INK,
                c in (4, 5),
                16,
                PP_ALIGN.CENTER,
            )
        ),
    )
    band(
        s,
        5.8,
        "뜻",
        "콘 · 경판 0/6 은 판독기만의 잘못이 아니었습니다. 정답이 틀리면 고쳐도 점수가 오르지 않습니다",
        h=0.8,
        size=16,
    )


def data_figure_slide(d, title, message, files, caption_text, notes):
    s = slide(d, 4, title, message, notes)
    w = CW / len(files) - 0.15 * (len(files) - 1) / len(files)
    for i, f in enumerate(files):
        fit(s, FIG / f, X0 + i * (w + 0.15), 1.8, w, 3.9)
    band(s, 5.85, "", caption_text, fill=LIGHT, color=TEAL, h=0.8, size=16)


def drafting_slide(d):
    s = slide(
        d,
        4,
        "도면 자체도 고쳤습니다",
        "판독기가 아니라 그리는 쪽의 실수. 사람이 그린 도면이라면 나오지 않을 것들",
        "docs/v3_upgrade.md 4절 #1, #6~#10, docs/data/synthetic.md 5.2절.",
    )
    rows = [
        ["#", "이상한 점", "어디서"],
        [
            "1",
            "경판 윤곽이 직선과 만나는 곳에서 꺾임 → 2:1 반타원 + 짧은 직선부",
            "경판 6장",
        ],
        ["6", "같은 숨은선이 두 번씩", "10장"],
        ["7", "구멍 기호 Ø 가 깨짐 (2-Ã˜13)", "11장"],
        ["8", "콘 안쪽 면이 바깥 면과 평행하지 않음", "콘 6장"],
        ["9", "굽힘판 바깥 모서리가 각짐 (R + t 로 둥글어야)", "굽힘판 6장"],
        ["10", "옆에서 본 구멍에 중심선 없음", "11장"],
    ]
    table(s, X0, 1.9, CW, 4.2, rows, [0.8, 8.9, 2.433], head_style)


def practitioner_slide(d):
    s = slide(
        d,
        4,
        "기준: 현업자가 그린 정답",
        "회사 계산 문서와 현업자 정답 전개도가 다르면, 검토 전까지 현업자 정답을 따릅니다",
        "docs/v3_upgrade.md 5.2 · 5.4절. 2026-10-28 결정. 세 부품 모두 안지름 1000, 두께 20, A516-70. 정답 전개도에는 '철판두께의 가운데를 기준으로 산출됨'.",
    )
    rows = [
        ["부품", "현업자 정답", "회사 계산 문서 식", "차이"],
        ["원통 SHELL", "3204.4 × 1500", "π × (1000 + 20) = 3204.4", "0"],
        ["콘 CONE", "R1 1023.09, θ 180°", "평균지름 = 안지름 + t → 1020.0", "−0.3%"],
        ["경판 HEAD", "원판 1301.6", "1.2 × Dm + 2SF = 1284.0", "−1.35%"],
    ]
    table(s, X0, 1.9, CW, 2.2, rows, [2.2, 3.2, 4.933, 1.8], head_style)
    bullets(
        s,
        X0,
        4.4,
        CW,
        2.2,
        [
            "콘: 평균지름을 끝면에서 가로로 잼 (안지름 + t / cos α)",
            "경판: 두께 가운데 반타원의 길이 + 직선부 × 2 (1.2 × Dm 은 면적이 같은 원판의 근사식)",
            "생성기와 판독기를 이 기준으로 바꿨습니다. 회사 검토를 부탁드립니다",
        ],
        size=17,
    )


def grid_slide(d):
    s = slide(
        d,
        4,
        "코드 효과와 데이터 효과를 나누려면",
        "②→③ 은 둘이 같이 바뀌어서, 같은 데이터로 코드만 바꿔 다시 잽니다 (2×2)",
        "docs/pbl_meeting.md 3절. R1~R4 는 아직 돌리지 않았다. 돌리면 이 칸을 채운다.",
    )
    rows = [
        ["", "옛 합성 (synthetic)", "새 합성 (generated)"],
        ["옛 코드 ② c71cca0", "R2: ②", "R3: 데이터만 바뀐 효과"],
        ["지금 코드 ③ main", "R1: 코드만 바뀐 효과", "R4: ③"],
    ]
    table(
        s,
        X0 + 1.0,
        2.0,
        10.1,
        2.4,
        rows,
        [3.0, 3.55, 3.55],
        lambda r, c: (
            (TEAL, WHITE, True, 16, PP_ALIGN.CENTER)
            if r == 0 or c == 0
            else (
                ORANGE_TINT if (r, c) == (2, 2) else LIGHT,
                INK,
                False,
                17,
                PP_ALIGN.CENTER,
            )
        ),
    )
    band(
        s,
        4.8,
        "상태",
        "같은 모델 · 같은 채점기로 네 번 돌립니다. 결과는 실행 뒤 채웁니다 (지금 슬라이드의 ③ 은 10-28 실행)",
        fill=LIGHT,
        color=GRAY,
        h=0.9,
        size=16,
    )


def score_compare_slide(d, pre, s3):
    s = slide(
        d,
        4,
        "단계별 점수",
        "새 정답으로 잰 ③. 형상 · 표제란 · 완주는 30/30, 뷰 · 치수 · 전개가 남았습니다",
        "① 은 RUN1 의 accuracy.md (형상 27/30), flat_patterns.md (전개 11/30, 옛 정답 기준). 나머지 항목은 단계 기록이 없어 잴 수 없다. "
        "③ 다시 묻기 전 = runs/reader/gen1027/local_new, 뒤 = company_synthetic_20261028_042351 의 score.json (scripts/reader/score_synthetic.py).",
    )
    rows = [["항목", "기준", "① 옛 정답", "③ 다시 묻기 전 (10-27)", "③ (10-28)"]]
    for it in ITEMS:
        one = {"형상": "27/30", "전개": "11/30"}.get(it, "기록 없음")
        rows.append([it, ITEM_DESC[it], one, frac(count(pre, it)), frac(count(s3, it))])

    def style(r, c):
        if r == 0:
            return TEAL, WHITE, True, 14, PP_ALIGN.CENTER
        return (
            LIGHT if r % 2 else WHITE,
            ORANGE
            if c == 4
            else (GRAY if c == 2 and rows[r][2] == "기록 없음" else INK),
            c in (0, 4),
            15,
            PP_ALIGN.LEFT if c < 2 else PP_ALIGN.CENTER,
        )

    table(s, X0, 1.85, CW, 4.3, rows, [1.4, 3.733, 2.2, 2.6, 2.2], style)
    text(
        s,
        X0,
        6.3,
        CW,
        0.5,
        [
            "①과 ③은 채점에 쓴 정답이 다릅니다. ③ 두 열은 같은 정답이고, 차이는 '잘리면 다시 묻기' 등"
        ],
        size=13,
        color=GRAY,
    )


def class_score_slide(d, s3):
    s = slide(
        d,
        4,
        "형상별 점수 (③)",
        "평판은 거의 끝까지 맞고, 원통 · 경판은 뷰를, 콘 · 굽힘판은 치수를 놓칩니다",
        "company_synthetic_20261028_042351/score.json 을 형상별로 셌다.",
    )
    rows = [["항목"] + [CLASS_KR[c] for c in CLASSES] + ["전체"]]
    for it in ITEMS:
        rows.append(
            [it]
            + [f"{count(s3, it, c)}/6" if s3 else "–" for c in CLASSES]
            + [frac(count(s3, it))]
        )

    def style(r, c):
        if r == 0:
            return TEAL, WHITE, True, 15, PP_ALIGN.CENTER
        low = s3 and 0 < c < 6 and int(rows[r][c].split("/")[0]) <= 2
        return (
            LIGHT if r % 2 else WHITE,
            ORANGE if low else INK,
            c == 0 or low,
            16,
            PP_ALIGN.CENTER,
        )

    table(s, X0, 1.85, CW, 4.4, rows, [2.033] + [1.7] * 5 + [1.6], style)
    text(s, X0, 6.4, CW, 0.4, ["주황 = 6장 중 2장 이하"], size=13, color=GRAY)


def load_flat1():
    """Per drawing: the colleague's flat-pattern error against the old label (flat_patterns.md)."""
    path = RUN1 / "flat_patterns.md"
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 6 and cells[0][:1].islower() and cells[0] != "id":
            err = cells[5]
            if err.endswith("%"):
                out[cells[0]] = "맞음" if float(err[:-1]) <= 1 else f"오차 {err}"
            else:
                out[cells[0]] = "전개 안 함"
    return out


def class_pair_slides(d, s3):
    flat1 = load_flat1()
    for cls in CLASSES:
        dr = SHOWCASE[cls]
        w1, w3 = workdir(RUN1, dr), workdir(RUN3, dr)
        s = slide(
            d,
            4,
            f"{CLASS_KR[cls]} ({dr}): 판독",
            "왼쪽 ① 옛 도면을 동료 v3 가, 오른쪽 ③ 새 도면을 reader+ 가 읽은 결과",
            f"① {w1.relative_to(ROOT)}/analysis/sheet_labeled.png, ③ {w3.relative_to(ROOT)}/analysis/sheet.png. 도면 자체도 바뀌었다 (새 생성기).",
        )
        before_after(
            s,
            (w1 / "analysis" / "sheet_labeled.png", "옛 도면 · 동료 v3"),
            (w3 / "analysis" / "sheet.png", "새 도면 · reader+ (뷰 이름)"),
        )
        row = next((r for r in s3 or [] if r["id"] == dr), None)
        after = "–"
        if row:
            after = "맞음" if row["ok"]["전개"] else row["why"].get("전개", "틀림")
        s = slide(
            d,
            4,
            f"{CLASS_KR[cls]} ({dr}): 전개",
            f"① 동료 v3: 옛 정답과 {flat1.get(dr, '–')}  →  ③ reader+: 새 정답과 {after}",
            f"① {w1.relative_to(ROOT)}/flat_pattern.png (RUN1 flat_patterns.md 의 오차), "
            f"③ {w3.relative_to(ROOT)}/figures/10_develop.png 왼쪽 절반 (검정 = 계산, 초록 점선 = 정답).",
        )
        before_after(
            s,
            (w1 / "flat_pattern.png", "동료 v3 의 전개도"),
            (develop_plot(RUN3, dr), "reader+ (검정 = 계산, 초록 점선 = 정답)"),
        )


def fixed_slide(d):
    s = slide(
        d,
        4,
        "고친 것",
        "데이터 10건, 하네스 1건, 코드 1건. 남은 것은 다음 장",
        "docs/v3_upgrade.md 4절 표. 상태가 '고침' 인 것.",
    )
    rows = [
        ["어디를", "무엇을", "#"],
        [
            "데이터 (생성기 · 정답)",
            "콘 · 경판 · 굽힘판 정답 식, 경판 윤곽, 숨은선, Ø 기호, 콘 안쪽 면, 굽힘 모서리, 중심선",
            "1~10",
        ],
        ["하네스", "잘리면 짧게 다시 묻기, 판단 서버의 공백 반복 막기", "13"],
        ["코드 (reader)", "경판 직선부를 타원 끝으로 잘못 재던 것", "16"],
        [
            "기준",
            "현업자 정답 식을 생성기 · reader 에 (콘 평균지름, 경판 원판)",
            "5.4절",
        ],
    ]
    table(s, X0, 1.9, CW, 3.6, rows, [2.8, 8.0, 1.333], head_style)


def failure_slide(d, title, message, notes, drawing, point, *, views=False):
    """Views: the 05 figure. Otherwise the 09 parameters with who filled them, and the
    developed outline over the label."""
    s = slide(d, 4, title, message, notes)
    if views:
        fit(s, workdir(RUN3, drawing) / "figures" / "05_views.png", X0, 1.8, CW, 4.1)
    else:
        params_table(s, RUN3, drawing, X0, 1.9, 5.6)
        text(s, X0, 1.5, 5.6, 0.4, [f"09 치수 ({drawing})"], size=13, color=GRAY)
        fit(s, develop_plot(RUN3, drawing), X0 + 6.0, 1.8, 6.13, 4.1)
    band(s, 6.05, "고칠 곳", point, h=0.75, size=16)


def remaining_slides(d, s3):
    why = {r["id"]: r["why"] for r in s3} if s3 else {}
    failure_slide(
        d,
        "남은 실패 1: 원만 있는 뷰를 놓침 (#11)",
        "원통의 우측면, 경판의 평면은 원만 있는 뷰라 뷰 후보로 잡히지 않습니다",
        f"cylinder_0014 의 05_views.png. 뷰 점수 실패 13장 중 12장의 원인 (v3_upgrade.md 3.1). 채점 이유: {why.get('cylinder_0014', {}).get('뷰')}",
        "cylinder_0014",
        "코드 05: 원 하나만 있는 덩어리도 뷰 후보로 (원통 6장, 경판 6장)",
        views=True,
    )
    failure_slide(
        d,
        "남은 실패 2: 콘 대경을 바깥지름 그대로 (#14)",
        "AI 가 바깥지름 150 을 안지름 칸에 넣었습니다. 소경은 AI 가 비워 코드가 맞게 채웠습니다",
        f"cone_0019. 채점 이유: {why.get('cone_0019')}",
        "cone_0019",
        "하네스: AI 가 읽은 지름을 외형 치수와 대조 (안지름 = 바깥지름 − 2t/cos α 이어야)",
    )
    failure_slide(
        d,
        "남은 실패 3: 경판 전개 (#15)",
        "2:1 타원 경판의 종류를 잘못 고릅니다. 이 도면에서는 FLAT FLANGED 로 읽었습니다",
        f"press_formed_0026: 09 의 head_type FLAT FLANGED (정답 2:1 타원). 경판 5장에서 HEMI 로 고른 경우도 있다 (v3_upgrade.md 4절 #15, 10-27 실행 기준). 채점 이유: {why.get('press_formed_0026')}. 이 실행은 경판 원판 식을 현업자 정답으로 바꾸기(2807e44) 전이다.",
        "press_formed_0026",
        "하네스: 높이 / 지름 = 1/4 이면 2:1 타원. 그리고 지금 코드로 다시 재기",
    )
    failure_slide(
        d,
        "남은 실패 4: 굽힘판 폭과 다리 (#17)",
        "폭과 다리 길이를 바꿔 읽거나, 굽힘 반경 0 을 두께로 읽습니다",
        f"bent_sheet_0007. 채점 이유: {why.get('bent_sheet_0007')}",
        "bent_sheet_0007",
        "하네스: 외형 치수와 대조, 반경이 도면에 없으면 0",
    )
    s = slide(
        d,
        4,
        "남은 것은 모델보다 하네스와 코드",
        "형상은 30/30. 틀리는 곳은 '읽은 값을 검사하지 않는 곳' 입니다",
        "docs/v3_upgrade.md 4절의 '남음' 항목: #11, #12, #14, #15, #17, #18.",
    )
    rows = [
        ["#", "실패", "고칠 곳", "영향"],
        ["11", "원만 있는 뷰를 놓침", "코드 05", "뷰 12장"],
        [
            "12",
            "정규식이 THIRD ANGLE · PART NAME 을 못 읽음",
            "코드 02",
            "30장 (04 가 메움)",
        ],
        ["14", "콘 대경을 바깥지름으로", "하네스: 외형 치수 대조", "콘 4장"],
        ["15", "2:1 경판의 종류를 잘못 고름", "하네스: 높이 / 지름 검사", "경판 3~5장"],
        ["17", "굽힘판 폭 · 다리, 반경", "하네스: 외형 치수 대조", "굽힘판 4장"],
        ["18", "평면도를 bottom 으로", "모델", "평판 1장"],
    ]
    table(s, X0, 1.9, CW, 4.2, rows, [0.8, 5.2, 3.9, 2.233], head_style)


# ---------------------------------------------------------------------- E. 실험
def experiment_section(d):
    section(
        d,
        "6",
        "추가 실험",
        "답 잘림 처리 · 모델 바꿔 끼우기 (진행 중)",
        "두 실험은 다른 세션에서 진행 중이다. 결과가 나오면 이 파트를 채운다 (docs/pbl_meeting.md 4절).",
    )


def truncation_slide(d):
    s = slide(
        d,
        5,
        "실험 1: JSON 답 잘림",
        "다시 묻기로 살리고 있지만, 잘림 자체는 reader+ 에서도 일어납니다",
        "docs/pbl_meeting.md 4.1절. 10-28 실행의 판단 호출 60번 중 4번 잘림 (06 cylinder_0017, flat_0002 / 09 press_formed_0025 · 0027). 09 의 잘림은 이번에 처음 확인했다.",
    )
    rows = [
        ["왜 잘리나", "예"],
        [
            "이유(reason) 칸에 계산을 길게 풀어 씀 (09)",
            '"… Total = 56. Still not 59. Let\'s"',
        ],
        ["줄바꿈 · 공백을 반복 (06)", "flat_0002"],
    ]
    table(s, X0, 1.9, CW, 1.6, rows, [6.0, 6.133], head_style)
    opts = [
        ("답 양식 바꾸기", "결정 칸을 앞에, 이유는 맨 뒤 · 짧게. 잘려도 결정은 남음"),
        ("이어 쓰기", "잘린 곳부터 이어 쓰게 함. 양식 제약을 다시 걸기 어려움"),
        ("길이 제한 올리기", "1,500 → 4,096 토큰. 가장 쉽지만 공백 반복엔 시간만 더"),
    ]
    for i, (head, body) in enumerate(opts):
        y = 3.8 + i * 0.8
        chip(
            s,
            X0,
            y,
            2.8,
            0.65,
            head,
            fill=ORANGE_TINT,
            color=ORANGE,
            size=15,
            bold=True,
        )
        text(s, X0 + 3.0, y, 9.1, 0.65, [body], size=16, anchor=MSO_ANCHOR.MIDDLE)
    text(
        s,
        X0,
        6.3,
        CW,
        0.4,
        [
            "결과: 실험 뒤 채움 (같은 30장을 두 번 이상, 잘림 · 다시 묻기 횟수 · 시간 · 점수)"
        ],
        size=14,
        color=GRAY,
    )


def model_swap_slide(d):
    s = slide(
        d,
        5,
        "실험 2: 모델 바꿔 끼우기",
        "하네스는 그대로 두고 모델 하나만 바꿔, 같은 30장 · 같은 채점기로 잽니다",
        "docs/pbl_meeting.md 4.2절. 모델은 experiments/models/<이름>.sh 프로필로 고른다. 가설: 작은 로컬 모델도 하네스가 받쳐 주면 쓸 만하다 (docs/harness_engineering.md 1절).",
    )
    card(
        s,
        X0,
        1.9,
        5.6,
        3.0,
        [
            {"text": "그대로", "bold": True, "size": 20, "color": TEAL},
            {"text": "10단계, 질문, 답 양식, 검사", "bullet": True},
            {"text": "계산 코드, 채점기, 30장", "bullet": True},
        ],
        fill=TEAL_TINT,
        size=17,
        after=10,
    )
    card(
        s,
        X0 + 6.5,
        1.9,
        5.63,
        3.0,
        [
            {"text": "바꿈 (한 번에 하나)", "bold": True, "size": 20, "color": ORANGE},
            {"text": "OCR 모델 (GPU 한 장, 24 GB)", "bullet": True},
            {"text": "판단 모델 (GPU 세 장, 72 GB)", "bullet": True},
        ],
        fill=ORANGE_TINT,
        size=17,
        after=10,
    )
    band(
        s,
        5.2,
        "고려",
        "VRAM: BF16 은 파라미터당 2바이트 + 요청 메모리. context: 모델 사양(128k~262k)이고 우리는 16k 만 씀",
        fill=LIGHT,
        color=TEAL,
        h=0.9,
        size=16,
    )


def candidates_slide(d):
    s = slide(
        d,
        5,
        "후보 모델",
        "OCR 은 더 작고 점수가 높은 새 모델, 판단은 같은 크기의 새 판 · 다른 계열 · 작은 모델",
        "docs/pbl_meeting.md 4.2절. 크기와 context 는 2026-10-29 Hugging Face API. OmniDocBench v1.6 점수는 Roboflow 정리(2026-08-03). 모두 vLLM 0.31 지원 목록에 있다. 결과는 실험 뒤 채운다.",
    )
    rows = [
        ["역할", "모델", "크기", "context", "볼 것"],
        ["OCR (지금)", "DeepSeek-OCR-2", "3.4B", "8k", "OmniDocBench v1.6 약 90"],
        ["OCR", "PaddleOCR-VL-1.6", "0.96B", "131k", "v1.6 96.3"],
        ["OCR", "GLM-OCR", "1.3B", "131k", "v1.6 95.2"],
        ["판단 (지금)", "Qwen3.6-27B", "27.8B (55.6 GB)", "262k", "기준"],
        ["판단", "Qwen3.8-27B", "27.8B (55.6 GB)", "262k", "같은 크기의 새 판"],
        ["판단", "Gemma 4 26B-A4B", "25.8B (51.6 GB)", "262k", "다른 계열, MoE"],
        [
            "판단",
            "Qwen3-VL-8B / Gemma 4 12B",
            "8.8B / 12B",
            "262k",
            "작은 모델 + 하네스",
        ],
    ]
    table(s, X0, 1.85, CW, 4.3, rows, [1.8, 3.6, 2.4, 1.3, 3.033], head_style)
    text(
        s,
        X0,
        6.35,
        CW,
        0.4,
        ["결과: 실험 뒤 채움 (단계별 점수 · 30장 시간)"],
        size=14,
        color=GRAY,
    )


# ---------------------------------------------------------------------- F. v4
def v4_section(d):
    section(
        d,
        "7",
        "다음 단계: v4",
        "실제 도면을 부품표부터 읽기",
        "v3 고도화로 목표를 바꾸며 미뤘던 실제 도면 작업 (git show c71cca0:docs/v4.md).",
    )


def v4_why_slide(d):
    s = slide(
        d,
        6,
        "실제 도면은 왜 아직 안 되나",
        "판독기는 '도면 1장 = 부품 1개' 를 전제로 합니다. 실제 상세도는 한 장에 부품 4~13종",
        "v4.md 1 · 4절. S-2120 상세 도면 3장의 커팅플랜 판재 품번이 장마다 4~13종. 모델을 붙여 실제 도면 5장을 돌렸을 때 정답 22종 중 전개까지 간 것은 1개 (docs/presentation.md 5절).",
    )
    shape(s, MSO_SHAPE.RECTANGLE, X0, 2.0, 4.0, 2.8, WHITE, line=GRAY)
    for i, (x, y) in enumerate([(0.4, 0.5), (0.4, 1.6), (1.9, 1.6)]):
        shape(s, MSO_SHAPE.RECTANGLE, X0 + x, 2.0 + y, 1.1, 0.9, TEAL_TINT, line=TEAL)
    text(
        s, X0, 4.9, 4.0, 0.4, ["합성: 부품 1개, 3면도"], size=15, align=PP_ALIGN.CENTER
    )
    real_sheet(s, X0 + 5.0, 2.0, 4.2, 2.8)
    text(
        s,
        X0 + 5.0,
        4.9,
        4.2,
        0.4,
        ["실제: 여러 부품, 부품표, 상세도"],
        size=15,
        align=PP_ALIGN.CENTER,
    )
    card(
        s,
        X0 + 9.6,
        2.0,
        2.53,
        2.8,
        [
            {"text": "22종 중", "size": 16},
            {"text": "1개", "size": 40, "bold": True, "color": ORANGE},
            {"text": "전개까지 감", "size": 14},
        ],
        fill=ORANGE_TINT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    band(
        s,
        5.6,
        "원인",
        "모델 성능이 아니라 단계 설계: 06 은 시트 하나에 형상 하나를 묻습니다. 시트 → 부품으로 나누는 단계가 없습니다",
        h=0.95,
        size=16,
    )


def v4_bom_slide(d):
    s = slide(
        d,
        6,
        "부품표부터 읽는다",
        "실제 도면에는 '무엇이 몇 개' 가 부품표에, '어디에 그렸나' 가 품번 풍선에 있습니다",
        "v4.md 4.4 · 5절. 상세 도면 3장의 부품표는 DXF 안에 열 위치가 일정한 TEXT 로 있어 코드로 읽을 수 있다. 커팅플랜의 부품 라벨 S-2120-002 7-2 는 부품표 한 행을 가리킨다.",
    )
    steps = [
        ("부품표", "품번 · 이름 · 재질\n두께 · 수량", TEAL_TINT),
        ("부품 목록", "설비 전체를 합침\nS-2120-002 7-2", TEAL_TINT),
        ("판재 판정", "형강 · 볼트 · 배관 제외", TEAL_TINT),
        ("부품마다\n판독 10단계", "형상 · 치수 · 전개", ORANGE_TINT),
    ]
    for i, (head, body, fill) in enumerate(steps):
        x = X0 + i * 3.1
        card(
            s,
            x,
            2.0,
            2.7,
            2.2,
            [
                {"text": head, "bold": True, "size": 18},
                {"text": body, "size": 14, "color": GRAY},
            ],
            fill=fill,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if i < 3:
            arrow(s, x + 2.75, 2.95, w=0.3, h=0.3)
    code(
        s,
        X0,
        4.5,
        7.0,
        1.3,
        [
            "7  -1  SUPPORT BRACING   A36     4  EA  L75x75x9",
            "   -2  GUSSET PLATE      A283-C  8  EA  t10",
        ],
        size=13,
    )
    text(
        s,
        X0 + 7.3,
        4.5,
        4.8,
        1.3,
        [
            "부품표의 SIZE 칸에는 판의 두께만 있습니다 (t10). 가로 · 세로는 뷰의 치수에서 읽어야 합니다"
        ],
        size=15,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    band(
        s,
        6.0,
        "판독기는 그대로",
        "01 읽기는 부품표 입력으로, 10 전개는 그대로. 06 · 09 는 부품 하나의 영역을 떼어 넣으면 씁니다",
        fill=LIGHT,
        color=TEAL,
        h=0.75,
        size=15,
    )


def v4_expect_slide(d):
    s = slide(
        d,
        6,
        "손으로 확인한 기댓값 (S-2120)",
        "정답 커팅플랜의 판재 22종이 모두 부품표에 있고, 재질 · 두께는 21종이 같습니다",
        "v4.md 5.2절. 정답 test_data/cases/S-2120/output_cutting_plan/parts.csv 를 (도면, 품번)으로 부품표 행과 맞췄다. 다른 1건은 DWG-003 2-3 END PLATE (부품표 A240-304 t6, 커팅플랜 A283-C t6, company_questions.md Q17).",
    )
    rows = [
        ["도면", "정답 품번", "부품표에 있음", "재질 · 두께 같음"],
        ["상세도 002", "13", "13", "13"],
        ["상세도 003", "4", "4", "3"],
        ["상세도 004", "5", "5", "5"],
        ["합계", "22", "22", "21"],
    ]
    table(s, X0 + 1.0, 1.9, 10.1, 2.8, rows, [3.0, 2.2, 2.4, 2.5], head_style)
    band(
        s,
        5.1,
        "뜻",
        "부품 목록 · 재질 · 두께 · 수량은 AI 없이 부품표만으로 만들 수 있습니다. AI 는 크기를 읽을 때 씁니다",
        fill=TEAL_TINT,
        color=TEAL,
    )


def v4_plan_slide(d):
    s = slide(
        d,
        6,
        "v4 계획",
        "부품표 단계를 판독기처럼 '단계마다 파일' 로 붙이고, 실제 도면 정답으로 잽니다",
        "v4.md 8절. 범위 밖: 판재 크기 (뷰 치수와 품번 풍선), D-1203 (글자가 없는 PDF, OCR 필요). 합성 30장은 회귀 테스트로 남는다.",
    )
    steps = [
        ("1", "부품표 읽기", "도면 1장, 코드만. 01 의 글자 위치로 열과 행을 나눔"),
        ("2", "부품 목록", "설비 단위로 합침. 판재 판정은 근거를 남기는 함수로"),
        ("3", "채점", "정답 parts.csv 와 품번 · 판재 판정 · 재질 · 두께 · 수량 대조"),
        ("4", "도구로 등록", "AI 가 부를 수 있게 (orchestrator)"),
    ]
    for i, (n, head, body) in enumerate(steps):
        y = 1.9 + i * 1.05
        chip(s, X0, y, 0.75, 0.85, n, fill=ORANGE, color=WHITE, size=22, bold=True)
        chip(
            s, X0 + 0.9, y, 2.6, 0.85, head, fill=TEAL, color=WHITE, size=18, bold=True
        )
        text(s, X0 + 3.7, y, 8.4, 0.85, [body], size=17, anchor=MSO_ANCHOR.MIDDLE)
    band(
        s,
        6.15,
        "그 뒤",
        "판재 크기 읽기 → v2 뒷단(분할 · 네스팅)과 연결 → 커팅플랜까지 로컬로",
        fill=LIGHT,
        color=TEAL,
        h=0.7,
        size=15,
    )


def roadmap_slide(d):
    s = slide(
        d,
        6,
        "하네스 로드맵에서 지금 위치",
        "단계로 나누기와 단계별 채점은 됐고, 모델 비교와 보완 장치가 다음입니다",
        "docs/harness_engineering.md 3절 로드맵.",
    )
    rows = [
        ("0", "합성 생성기 다시 쓰고 검증", "됨"),
        ("1", "판독을 단계로 나눔", "됨"),
        ("2", "단계별 채점", "됨 (score_synthetic.py)"),
        ("3", "단계마다 모델 설정", "프로필로 일부"),
        ("4", "Claude 대 로컬 비교", "실험 2 와 함께"),
        ("5", "보완 장치 (다시 묻기, 다수결, 대조)", "첫 장치: 다시 묻기"),
        ("6", "AI 가 단계를 고름", "시제품"),
        ("7", "v2 뒷단까지 연결", "v4 뒤"),
    ]
    for i, (n, head, state) in enumerate(rows):
        y = 1.85 + i * 0.6
        done = state.startswith("됨")
        chip(
            s,
            X0,
            y,
            0.6,
            0.5,
            n,
            fill=TEAL if done else LIGHT,
            color=WHITE if done else GRAY,
            size=14,
            bold=True,
        )
        text(s, X0 + 0.8, y, 6.5, 0.5, [head], size=17, anchor=MSO_ANCHOR.MIDDLE)
        text(
            s,
            X0 + 7.5,
            y,
            4.6,
            0.5,
            [state],
            size=16,
            color=TEAL if done else ORANGE,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def ask_slide(d):
    s = slide(
        d,
        6,
        "회사에 부탁드릴 것",
        "정답의 기준과 실제 도면 세트",
        "docs/v3_upgrade.md 5.3 · 5.4절, docs/domain/company_questions.md.",
    )
    rows = [
        (
            "계산 기준",
            "계산 문서와 현업자 정답이 다른 두 곳 (경판 원판, 콘 평균지름). 어느 쪽이 현장 기준인지",
        ),
        (
            "콘 기준",
            "받은 커팅플랜 D-1203 의 콘은 안지름 기준입니다. 현업자 정답(가로로 잼)과 다릅니다",
        ),
        (
            "실제 도면",
            "입력 도면과 커팅플랜이 짝지어진 설비를 더 (지금 2건: S-2120, D-1203)",
        ),
    ]
    for i, (head, body) in enumerate(rows):
        y = 1.95 + i * 1.4
        chip(s, X0, y, 2.6, 1.15, head, fill=ORANGE, color=WHITE, size=18, bold=True)
        card(
            s,
            X0 + 2.8,
            y,
            9.33,
            1.15,
            [body],
            fill=LIGHT,
            size=17,
            anchor=MSO_ANCHOR.MIDDLE,
        )


# ---------------------------------------------------------------------- G. 마무리
def wrapup_slide(d, s3):
    s = slide(
        d,
        6,
        "정리",
        "정답을 고치고, 단계마다 재고, 틀린 곳을 단계 하나로 짚습니다",
        "",
    )
    rows = [
        (
            "전 → 후",
            f"새 정답으로 단계 {frac(count(s3, '단계'))}, 형상 {frac(count(s3, '형상'))}, 전개 {frac(count(s3, '전개'))}",
        ),
        ("하네스", "AI 는 네 단계에서 읽고 고르기만. 계산 · 검사 · 기록은 코드"),
        ("남은 것", "뷰(원만 있는 뷰), 치수 대조. 모델보다 하네스와 코드"),
        ("다음", "답 잘림 · 모델 비교 실험 → 실제 도면을 부품표부터 (v4)"),
    ]
    for i, (head, body) in enumerate(rows):
        y = 1.95 + i * 1.15
        chip(s, X0, y, 2.4, 0.9, head, fill=TEAL, color=WHITE, size=18, bold=True)
        text(s, X0 + 2.65, y, 9.5, 0.9, [body], size=19, anchor=MSO_ANCHOR.MIDDLE)


def questions_slide(d):
    s = d.slide("질문", dark=True)
    text(
        s,
        X0,
        2.8,
        CW,
        1.2,
        ["질문"],
        size=48,
        bold=True,
        color=WHITE,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        X0,
        4.0,
        CW,
        0.6,
        ["PBL · 2026-10-30"],
        size=18,
        color=PALE,
        align=PP_ALIGN.CENTER,
    )


# ---------------------------------------------------------------------- 부록
def appendix_section(d):
    section(
        d,
        "부록",
        "부록",
        "시험 도면 · 도면별 점수 · 하네스 구조 · 실행 명령",
        "질문이 나오면 가는 슬라이드.",
    )


def testset_slide(d):
    s = slide(
        d,
        6,
        "부록: 현업자가 그린 시험 도면 3건",
        "합성은 개발 세트, 사람이 그린 3건은 시험 세트. 시험 세트를 보고 하네스를 고치지 않습니다",
        "docs/v3_upgrade.md 5.1 · 5.2절. data_v3/20261027example, DWG 와 PDF. 실행 결과는 돌린 뒤 넣는다.",
    )
    rows = [
        ["부품", "형상", "도면", "정답 전개"],
        ["SHELL", "원통", "원 1000 · 1040, 길이 1500", "3204.4 × 1500"],
        [
            "CONE",
            "콘",
            "큰 쪽 1000 · 1046.2, 작은 쪽 422.6 · 468.8",
            "R1 1023.09, R2 445.75, θ 180°",
        ],
        ["HEAD", "경판", "2:1, 깊이 250, 직선부 30", "원판 1301.6"],
    ]
    table(s, X0, 1.9, CW, 2.2, rows, [1.6, 1.4, 5.2, 3.933], head_style)
    bullets(
        s,
        X0,
        4.4,
        CW,
        2.0,
        [
            "DWG 라 00 변환부터. 표제란이 부품표 칸 모양이고 도면 번호 · 축척 글자가 없습니다",
            "뷰 이름이 글자로 있습니다 (<TOP VIEW>, <FRONT VIEW>, <SIDE VIEW>)",
            "결과: 실행 뒤 채움 (형상, 전개 값을 정답 전개도와 대조)",
        ],
        size=16,
    )


def per_drawing_slides(d, s3):
    if not s3:
        return
    rows_all = sorted(s3, key=lambda r: r["id"])
    for part, chunk in enumerate((rows_all[:15], rows_all[15:])):
        s = slide(
            d,
            6,
            f"부록: 도면별 결과 ({part + 1}/2)",
            "O = 맞음, X = 틀림. 틀린 이유는 발표자 노트",
            "company_synthetic_20261028_042351/score.md.\n"
            + "\n".join(f"{r['id']}: {r['why']}" for r in chunk if r["why"]),
        )
        rows = [["도면"] + ITEMS[:-1]] + [
            [r["id"]] + ["O" if r["ok"][it] else "X" for it in ITEMS[:-1]]
            for r in chunk
        ]
        table(
            s,
            X0,
            1.75,
            CW,
            5.0,
            rows,
            [3.133] + [1.5] * 6,
            lambda r, c: (
                (TEAL, WHITE, True, 12, PP_ALIGN.CENTER)
                if r == 0
                else (
                    LIGHT if r % 2 else WHITE,
                    ORANGE if rows[r][c] == "X" else INK,
                    rows[r][c] == "X",
                    12,
                    PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER,
                )
            ),
        )


def commands_slide(d):
    s = slide(
        d,
        6,
        "부록: 다시 돌리는 명령",
        "레포 루트에서. 서버를 띄운 셸과 다른 셸에서 돌립니다",
        "docs/reader/quickstart.md, docs/pbl_meeting.md 3절.",
    )
    code(
        s,
        X0,
        1.9,
        CW,
        4.6,
        [
            "# 서버 (GPU 0: OCR, GPU 1-3: 판단)",
            "./experiments/serve.sh --vllm-bin ~/venvs/vllm-0.31/bin/vllm",
            "",
            "# 30장을 3묶음으로 돌리고 단계별 채점",
            "experiments/batch_parallel.sh data_v3/generated runs/reader/<폴더> 3",
            "uv run python scripts/reader/score_synthetic.py runs/reader/<폴더>",
            "",
            "# 도면 한 장의 단계별 그림 (figures/NN_<단계>.png)",
            "uv run python scripts/reader/show_stages.py runs/reader/<폴더>/shard0/cone_0023",
            "",
            "# 이 슬라이드",
            "PYTHONPATH=. uv run --with python-pptx python presentation/build_meeting.py",
        ],
        size=14,
    )


# ---------------------------------------------------------------------- 1. 용어
GEN = ROOT / "data_v3" / "generated"
EMU = 914400


def drawing_png(drawing: str) -> Path:
    """The generator's own clean rendering of a synthetic drawing (scripts/build_synthetic.py)."""
    return GEN / drawing / f"{drawing}.png"


def mark(s, pic, fx, fy, fw, fh, label, *, color=ORANGE, below=False):
    """A dashed box over part of a picture (fractions of the picture) with a label chip."""
    px, py = pic.left / EMU, pic.top / EMU
    pw, ph = pic.width / EMU, pic.height / EMU
    x, y, w, h = px + fx * pw, py + fy * ph, fw * pw, fh * ph
    dashed(outline(s, MSO_SHAPE.RECTANGLE, x, y, w, h), color, 2.0)
    ly = y + h + 0.03 if below else y - 0.36
    chip(
        s,
        x,
        ly,
        max(1.2, 0.17 * len(label) + 0.4),
        0.33,
        label,
        fill=color,
        color=WHITE,
        size=12,
        bold=True,
    )


def define_section(d):
    section(
        d,
        "1",
        "용어부터",
        "오늘 이야기에 나오는 말을 예시 도면으로 먼저 정합니다",
        "처음 오신 분을 위한 파트. 예시는 합성 도면 cone_0023 이다.",
    )


def job_def_slide(d):
    s = slide(
        d,
        0,
        "하려는 일",
        "설계 도면을 읽어, 철판을 어떤 모양으로 자를지(전개도) 자동으로 만드는 것",
        "왼쪽 data_v3/generated/cone_0023/cone_0023.png (생성기가 그린 도면), 가운데 같은 도면을 reader 가 읽어 만든 flat_pattern.png "
        "(runs/reader/company_synthetic_20261028_042351). 커팅플랜은 모식도. 이번 범위는 가운데까지다.",
    )
    w3 = workdir(RUN3, EXAMPLE)
    cols = [
        ("설계 도면", "부품을 그린 그림 (입력)", drawing_png(EXAMPLE)),
        ("전개도", "철판에서 잘라낼 모양 (출력)", w3 / "flat_pattern.png"),
    ]
    for i, (head, sub, path) in enumerate(cols):
        x = X0 + i * 4.25
        caption(s, x, 1.85, 3.8, head, fill=TEAL if i == 0 else ORANGE, color=WHITE)
        fit(s, path, x, 2.35, 3.8, 2.9)
        text(s, x, 5.3, 3.8, 0.4, [sub], size=15, color=GRAY, align=PP_ALIGN.CENTER)
        arrow(s, x + 3.88, 3.6, w=0.3, h=0.3)
    x = X0 + 8.5
    caption(s, x, 1.85, 3.63, "커팅플랜", fill=LIGHT, color=GRAY)
    shape(s, MSO_SHAPE.RECTANGLE, x + 0.2, 2.5, 3.2, 2.6, WHITE, line=GRAY)
    for kind, fx, fy, fw, fh in [
        (MSO_SHAPE.BLOCK_ARC, 0.25, 2.65, 1.5, 1.2),
        (MSO_SHAPE.RECTANGLE, 1.9, 2.7, 1.3, 0.8),
        (MSO_SHAPE.OVAL, 0.4, 3.95, 1.0, 1.0),
        (MSO_SHAPE.RECTANGLE, 1.7, 3.75, 1.5, 1.1),
    ]:
        shape(s, kind, x + fx, fy, fw, fh, TEAL_TINT, line=TEAL)
    text(
        s,
        x,
        5.3,
        3.63,
        0.4,
        ["큰 철판 위 배치 (다음 일)"],
        size=15,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    band(
        s,
        5.95,
        "오늘",
        "왼쪽 → 가운데, 도면 한 장에서 전개도 하나까지가 오늘 이야기의 범위입니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.75,
        size=16,
    )


def drawing_def_slide(d):
    s = slide(
        d,
        0,
        "설계 도면: 무엇이 그려져 있나",
        "부품 하나를 세 방향에서 본 그림(뷰)과, 이름 · 재질 · 두께를 적은 표(표제란)",
        "cone_0023 (콘). 3면도는 정면 · 평면(위에서) · 우측면. 회사 도면은 CAD 원본 DWG 로 오고, reader 는 같은 내용을 글자로 적은 DXF 를 읽는다 (00 단계가 바꾼다).",
    )
    pic = fit(s, drawing_png(EXAMPLE), X0, 1.95, 7.3, 4.75)
    mark(s, pic, 0.07, 0.165, 0.235, 0.29, "평면도 (위에서)")
    mark(s, pic, 0.07, 0.555, 0.23, 0.325, "정면도", below=True)
    mark(s, pic, 0.37, 0.555, 0.2, 0.325, "우측면도", below=True)
    mark(s, pic, 0.69, 0.84, 0.3, 0.145, "표제란", color=TEAL)
    rows = [
        ("뷰", "부품을 한 방향에서 본 그림. 세 개를 3면도라 합니다"),
        ("치수", "150 처럼 길이를 적은 숫자 (mm)"),
        ("표제란", "부품 이름 CONE, 재질 SPHC, 두께 4t, 축척 1/2, 도면 번호"),
        ("파일", "CAD 원본은 DWG. reader 는 글자로 된 DXF 를 읽습니다"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.95 + i * 1.18
        chip(s, X0 + 7.6, y, 1.2, 0.9, k, fill=TEAL, color=WHITE, size=16, bold=True)
        text(s, X0 + 8.95, y, 3.2, 0.9, [v], size=15, anchor=MSO_ANCHOR.MIDDLE)


SHAPE_DEF = {
    "flat": ("평평한 판", "펼쳐도 그대로"),
    "bent_sheet": ("판을 접은 것", "접기 전 긴 판"),
    "cylinder": ("판을 말아 만든 통", "직사각형"),
    "cone": ("원뿔의 윗부분을 자른 통", "부채꼴"),
    "press_formed": ("압력 용기의 뚜껑 (경판)", "원판"),
}


def shape_def_slide(d):
    s = slide(
        d,
        0,
        "형상: 부품 모양의 종류",
        "오늘 다루는 형상은 5가지입니다. 형상을 알아야 어떤 공식으로 펼칠지 정할 수 있습니다",
        "그림은 data_v3/generated/<도면>/<도면>.png. 회사 도면에 흔한 쉬운 형상 5종 (docs/interim_report.md 2절).",
    )
    w = 2.3
    for i, cls in enumerate(CLASSES):
        x = X0 + i * (w + 0.16)
        caption(s, x, 1.85, w, CLASS_KR[cls], fill=TEAL, color=WHITE, size=16)
        fit(s, drawing_png(SHOWCASE[cls]), x, 2.35, w, 1.75)
        what, flat = SHAPE_DEF[cls]
        card(
            s,
            x,
            4.25,
            w,
            1.6,
            [
                {"text": what, "size": 15},
                {"text": "펼치면", "size": 12, "color": GRAY},
                {"text": flat, "size": 16, "bold": True, "color": ORANGE},
            ],
            fill=LIGHT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            margin=0.08,
            after=2,
        )
    band(
        s,
        6.05,
        "형상 분류",
        "도면을 보고 이 다섯 중 무엇인지 고르는 일. 오늘 말하는 '형상 30/30' 은 30장 모두 맞게 골랐다는 뜻",
        h=0.75,
        size=15,
    )


def unfold_def_slide(d):
    s = slide(
        d,
        0,
        "전개: 말기 전의 평평한 판",
        "원통 · 콘은 철판을 잘라 말아서 만듭니다. 그 잘라낼 모양과 크기를 구하는 것이 전개입니다",
        "오른쪽은 cone_0023 을 reader 가 계산한 전개도 (flat_pattern.png). 전개에 쓰는 지름은 두께 가운데 지름 (평균지름).",
    )
    shape(s, MSO_SHAPE.CAN, X0 + 0.2, 1.95, 1.3, 1.6, TEAL_TINT, line=TEAL)
    arrow(s, X0 + 1.7, 2.6, w=0.45, h=0.35)
    shape(s, MSO_SHAPE.RECTANGLE, X0 + 2.4, 2.15, 2.6, 1.2, ORANGE_TINT, line=ORANGE)
    text(s, X0 + 2.4, 3.4, 3.6, 0.6, ["가로 = π × 평균지름\n세로 = 길이"], size=13)
    shape(s, MSO_SHAPE.TRAPEZOID, X0 + 0.2, 4.3, 1.3, 1.4, TEAL_TINT, line=TEAL)
    arrow(s, X0 + 1.7, 4.85, w=0.45, h=0.35)
    shape(s, MSO_SHAPE.BLOCK_ARC, X0 + 2.4, 4.2, 2.6, 1.6, ORANGE_TINT, line=ORANGE)
    text(s, X0 + 2.4, 5.85, 3.6, 0.5, ["부채꼴: 바깥 · 안쪽 반경, 각도"], size=13)
    fit(s, workdir(RUN3, EXAMPLE) / "flat_pattern.png", X0 + 5.6, 1.85, 3.3, 3.0)
    text(
        s,
        X0 + 5.6,
        4.9,
        3.3,
        0.4,
        ["cone_0023 의 전개도"],
        size=13,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    rows = [
        ("전개도", "잘라낼 판의 그림 (DXF)"),
        ("전개 값", "반경 321.0 · 167.0, 각도 81.8°"),
        ("치수", "공식에 넣는 값: 두께, 지름, 높이"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.95 + i * 1.05
        chip(
            s, X0 + 9.15, y, 1.3, 0.45, k, fill=ORANGE, color=WHITE, size=13, bold=True
        )
        text(s, X0 + 9.15, y + 0.47, 2.98, 0.5, [v], size=13)
    band(
        s,
        6.2,
        "전개가 맞다",
        "계산한 값이 정답과 1% 이내. 지름 10 mm 오차는 둘레 31 mm 오차라 그 판은 못 씁니다",
        h=0.65,
        size=15,
    )


def answer_def_slide(d):
    s = slide(
        d,
        0,
        "합성 도면과 정답",
        "정답이 미리 있는 연습 도면 30장으로 잽니다. 정답이 있어야 어디서 틀렸는지 압니다",
        "data_v3/generated/cone_0023/label.json 을 줄였다. 합성 도면은 회사 도면에 흔한 형상을 골라 프로그램(scripts/build_synthetic.py)으로 그렸다. 회사 도면 파일을 그대로 쓴 것이 아니다.",
    )
    fit(s, drawing_png(EXAMPLE), X0, 1.9, 4.6, 3.3)
    text(
        s,
        X0,
        5.25,
        4.6,
        0.4,
        ["cone_0023.dxf (합성 도면)"],
        size=13,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, X0 + 4.75, 3.4, w=0.35, h=0.3)
    code(
        s,
        X0 + 5.25,
        1.9,
        6.88,
        3.75,
        [
            "label.json  (정답)",
            '  "class": "cone",                    ← 형상',
            '  "params": {"large_outer_diameter": 150,',
            '             "small_outer_diameter": 80,',
            '             "height": 150, "thickness": 4},  ← 치수',
            '  "views": front · top · right          ← 뷰',
            '  "sheet": {"drawing_no": "SYN-00023",',
            '            "scale_text": "1/2", ...}    ← 표제란',
            '  "flat_pattern": {"sector_outer_radius": 321.02,',
            '                   "sector_angle_deg": 81.8}  ← 전개',
        ],
        size=12,
    )
    band(
        s,
        5.95,
        "왜 합성",
        "실제 회사 도면에는 단계별 정답이 없습니다 (최종 커팅플랜뿐). 합성은 형상 5종 × 6장 = 30장, 정답이 단계마다 있습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.8,
        size=15,
    )


def reader_def_slide(d):
    s = slide(
        d,
        0,
        "reader 와 로컬 AI",
        "reader 는 도면 한 장을 받아 전개도를 내는 프로그램입니다. 일부 단계에서 사내 서버의 AI 를 부릅니다",
        "서버 mlic: RTX A5000 24 GB × 4. OCR 은 GPU 0, 판단 모델은 GPU 1~3 (experiments/models/*.sh). 도면은 외부 AI 서비스로 나가지 않는다.",
    )
    chip(s, X0, 2.4, 2.0, 1.2, "DXF 도면", fill=LIGHT, color=INK, size=17, bold=True)
    arrow(s, X0 + 2.1, 2.85, w=0.4, h=0.3)
    card(s, X0 + 2.6, 1.95, 6.0, 2.1, [], fill=TEAL_TINT)
    text(
        s, X0 + 2.8, 2.0, 5.6, 0.4, ["reader (10단계)"], size=16, bold=True, color=TEAL
    )
    chip(
        s,
        X0 + 2.85,
        2.5,
        2.6,
        1.3,
        "코드\n읽기 · 계산 · 검사",
        fill=TEAL,
        color=WHITE,
        size=14,
        bold=True,
    )
    chip(
        s,
        X0 + 5.75,
        2.5,
        2.6,
        1.3,
        "AI\n읽고 고르기",
        fill=ORANGE,
        color=WHITE,
        size=14,
        bold=True,
    )
    arrow(s, X0 + 8.7, 2.85, w=0.4, h=0.3)
    chip(
        s, X0 + 9.2, 2.4, 2.9, 1.2, "전개도", fill=LIGHT, color=INK, size=17, bold=True
    )
    rows = [
        (
            "OCR 모델",
            "DeepSeek-OCR-2 (GPU 1장)",
            "그림 속 글자를 받아 씀. 표제란을 읽을 때",
        ),
        (
            "판단 모델",
            "Qwen3.6-27B (GPU 3장)",
            "그림과 글자를 보고 고름. 뷰 이름, 형상, 치수",
        ),
        (
            "로컬",
            "사내 GPU 서버",
            "외부 AI 서비스(Claude 등)를 쓰지 않음. 도면이 밖으로 안 나감",
        ),
    ]
    for i, (k, m, v) in enumerate(rows):
        y = 4.35 + i * 0.75
        chip(
            s,
            X0,
            y,
            1.8,
            0.6,
            k,
            fill=ORANGE if i < 2 else TEAL,
            color=WHITE,
            size=14,
            bold=True,
        )
        text(
            s, X0 + 2.0, y, 3.6, 0.6, [m], size=15, bold=True, anchor=MSO_ANCHOR.MIDDLE
        )
        text(s, X0 + 5.6, y, 6.5, 0.6, [v], size=15, anchor=MSO_ANCHOR.MIDDLE)


def harness_def_slide(d):
    s = slide(
        d,
        0,
        "하네스: AI 를 감싸는 장치",
        "AI 에게 다 맡기지 않고, 질문 · 답 검사 · 계산 · 기록을 코드가 맡습니다",
        "PBL 의 목표: 작은 로컬 AI 라도 하네스를 잘 만들면 쓸 만한 결과를 낸다 (docs/harness_engineering.md 1절, 아직 가설).",
    )
    cx, cy = X0 + 4.6, 3.2
    boxes = [
        (X0 + 0.3, 1.85, "질문을 좁게", "단계마다 한 가지만 묻기"),
        (X0 + 8.4, 1.85, "답 양식 · 검사", "정해진 칸에만 답, 코드가 확인"),
        (X0 + 0.3, 4.6, "계산은 코드", "공식은 AI 가 아니라 코드가"),
        (X0 + 8.4, 4.6, "기록", "무엇을 묻고 뭐라 답했는지 파일로"),
    ]
    for x, y, head, body in boxes:
        card(
            s,
            x,
            y,
            3.43,
            1.3,
            [
                {"text": head, "bold": True, "size": 17, "color": TEAL},
                {"text": body, "size": 14},
            ],
            fill=TEAL_TINT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    for x1, y1 in [
        (X0 + 3.73, 2.5),
        (X0 + 8.4, 2.5),
        (X0 + 3.73, 5.25),
        (X0 + 8.4, 5.25),
    ]:
        connect(s, x1, y1, cx + 1.45, cy + 0.65, color=TEAL, width=2)
    chip(
        s,
        cx,
        cy,
        2.9,
        1.3,
        "AI\n(로컬 모델)",
        fill=ORANGE,
        color=WHITE,
        size=20,
        bold=True,
    )
    band(
        s,
        6.15,
        "목표",
        "작은 로컬 AI 라도 하네스가 받쳐 주면 쓸 만하다 (PBL 의 가설)",
        h=0.65,
        size=15,
    )


def score_def_slide(d):
    tb = stage_json(RUN3, EXAMPLE, "04_title_fields").get("title_block", {})
    views = [
        v["label"] for v in stage_json(RUN3, EXAMPLE, "06_view_labels").get("views", [])
    ]
    rec = stage_json(RUN3, EXAMPLE, "10_develop").get("record", {})
    blank = rec.get("blank", {})
    params = rec.get("params", {})
    s = slide(
        d,
        0,
        "채점: 무엇을 맞았다고 하나",
        "단계마다 정답과 비교합니다. 예시 cone_0023 은 모두 맞았습니다",
        "scripts/reader/score_synthetic.py, 기준은 docs/v3_upgrade.md 2절. reader 는 안지름을 쓰므로 정답 바깥지름에서 2t/cos α 를 빼 비교한다. 값은 RUN3 의 04 · 06 · 10 단계 파일.",
    )
    rows = [
        ["항목", "무엇을 보나", "정답", "reader"],
        ["단계", "10단계가 오류 없이 끝남", "", "모두 done"],
        [
            "표제란",
            "도면 번호 · 축척 · 재질 · 두께",
            "SYN-00023 · 1/2 · SPHC · 4",
            f"{tb.get('drawing_no')} · {tb.get('scale_text')} · {tb.get('material')}",
        ],
        ["뷰", "뷰 이름", "front · top · right", " · ".join(views)],
        ["형상", "5가지 중 무엇", "cone", rec.get("part_class", "")],
        [
            "치수",
            "전개에 넣는 값",
            "바깥지름 150 · 80, 높이 150",
            f"안지름 {params.get('large_inner_dia', 0):.1f} · {params.get('small_inner_dia', 0):.1f}, 높이 {params.get('cone_height', 0):.0f}",
        ],
        [
            "전개",
            "전개 값이 1% 이내",
            "R 321.02 · 167.0, 81.8°",
            f"R {blank.get('outer_radius', 0):.2f} · {blank.get('inner_radius', 0):.1f}, {blank.get('angle_deg', 0):.1f}°",
        ],
        ["전부", "위 여섯이 모두 맞음", "", "맞음"],
    ]
    table(s, X0, 1.85, CW, 4.6, rows, [1.3, 3.6, 3.6, 3.633], head_style)


# ---------------------------------------------------------------------- 3. 지난주
def lastweek_section(d):
    section(
        d,
        "3",
        "지난주까지",
        "범위 · 성능 · 성공과 실패 · 드러난 문제",
        "지난 미팅까지의 상태. 숫자는 동료의 2026-10-18 실행 (RUN1).",
    )


def lastweek_scope_slide(d):
    s = slide(
        d,
        2,
        "지난주까지의 범위",
        "같은 로컬 AI 로, 합성 도면 30장과 실제 회사 도면 5장을 읽어 봤습니다",
        "① = 동료 v3 (253020c) 를 옛 합성 30장(data_v3/synthetic)에 돌린 runs/reader/deepseek_ocr_qwen_reasoning_skills (2026-10-18). 실제 도면 5장은 2026-10-23 실행 (docs/presentation.md 5절).",
    )
    rows = [
        ("데이터", "옛 합성 도면 30장 (동료의 생성기가 그림) + 실제 회사 도면 5장"),
        ("reader", "동료 v3: 13단계 (전개도 다음에 3D 모양 복원까지)"),
        ("AI", "OCR DeepSeek-OCR-2 + 판단 Qwen3.6-27B (지금과 같음)"),
        ("채점", "형상과 전개 두 가지만"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.95 + i * 1.1
        chip(s, X0, y, 2.2, 0.85, k, fill=TEAL, color=WHITE, size=18, bold=True)
        text(s, X0 + 2.45, y, 9.7, 0.85, [v], size=19, anchor=MSO_ANCHOR.MIDDLE)


def lastweek_perf_slide(d):
    s = slide(
        d,
        2,
        "지난주 성능 (합성 30장)",
        "형상은 30장 중 27장을 맞혔지만, 전개는 11장만 정답과 맞았습니다",
        "RUN1 accuracy.md (형상), flat_patterns.md (전개, 그때의 정답 기준 1% 이내).",
    )
    rows = [["", *[CLASS_KR[c] for c in CLASSES], "전체"]]
    rows.append(["형상 맞음", *[f"{RUN1_SHAPE[c]}/6" for c in CLASSES], "27/30"])
    rows.append(["전개 맞음", *[f"{RUN1_FLAT[c]}/6" for c in CLASSES], "11/30"])

    def style(r, c):
        if r == 0:
            return TEAL, WHITE, True, 16, PP_ALIGN.CENTER
        low = 0 < c < 6 and rows[r][c].startswith("0")
        return (
            LIGHT if r % 2 else WHITE,
            ORANGE if low else INK,
            c == 0 or low or c == 6,
            20,
            PP_ALIGN.CENTER,
        )

    table(s, X0, 2.0, CW, 1.9, rows, [2.133] + [1.7] * 5 + [1.5], style)
    bullets(
        s,
        X0,
        4.3,
        CW,
        2.2,
        [
            "형상: 틀린 3장은 다른 형상으로 답한 게 아니라, 답을 못 냈습니다 (뒤의 실패 사례 1)",
            "전개: 평판 · 원통은 거의 맞고, 콘 · 경판은 하나도 안 맞았습니다 (실패 사례 2)",
            "어느 단계에서 틀렸는지는 이 숫자만으로 알 수 없었습니다",
        ],
        size=17,
    )


def lastweek_success_slide(d):
    dr = "cylinder_0014"
    w1 = workdir(RUN1, dr)
    s = slide(
        d,
        2,
        "성공 사례: 원통 (cylinder_0014)",
        "뷰를 찾고, 원통이라고 고르고, 펼친 직사각형이 정답과 같았습니다 (오차 0%)",
        f"{w1.relative_to(ROOT)}/analysis/sheet_labeled.png 와 flat_pattern.png. flat_patterns.md: length 618.9, width 400.0, 오차 0.00%.",
    )
    before_after(
        s,
        (
            w1 / "analysis" / "sheet_labeled.png",
            "AI 에게 보인 그림 (빨간 번호 = 뷰 후보)",
        ),
        (w1 / "flat_pattern.png", "전개도: 618.9 × 400 (정답과 같음)"),
        labels=("판독", "전개"),
    )


def lastweek_fail_shape_slide(d):
    dr = "cylinder_0013"
    w1 = workdir(RUN1, dr)
    s = slide(
        d,
        2,
        "실패 사례 1: 형상을 답하지 못함 (cylinder_0013)",
        "AI 는 처음에 cylinder 라고 썼지만, 이유를 길게 쓰다 답이 잘려 형상 칸이 비었습니다",
        f"{w1.relative_to(ROOT)}/prediction.json 의 vlm_trace: view_labels 호출 57.6초, JSONDecodeError. 원문 앞부분에 part_class cylinder (점수 10), 뒤에 같은 문단 반복과 공백 반복. "
        "형상이 비면 09 · 10 을 건너뛴다. 같은 실행의 cylinder_0018, flat_0005 도 같은 원인 (docs/server_handoff.md 6.3).",
    )
    fit(s, w1 / "analysis" / "sheet_labeled.png", X0, 1.85, 5.0, 3.6)
    code(
        s,
        X0 + 5.3,
        1.85,
        6.83,
        3.6,
        [
            "판단 AI 의 답 (줄임)",
            '{"part_class": "cylinder",          ← 맞게 시작',
            ' "views": [{"id": 1, "type": "front",',
            '   "reason": "… Let\'s re-evaluate. …',
            "    Wait, let's look at the content. …",
            '    Wait, the prompt says "',
            "    \\r    \\r    \\r    \\r    \\r  …     ← 공백 반복",
            "",
            "→ 길이 제한(1,500 토큰)에서 잘림",
            "→ JSON 이 깨져 형상 = 없음 → 전개 건너뜀",
        ],
        size=12,
    )
    band(
        s,
        5.75,
        "문제",
        "AI 가 형상을 몰라서가 아니라, 답의 형식이 깨져서 틀렸습니다. 실행마다 잘리는 도면이 바뀝니다",
        h=0.85,
        size=16,
    )


def lastweek_fail_unfold_slide(d):
    flat1 = load_flat1()
    s = slide(
        d,
        2,
        "실패 사례 2: 콘 · 경판 전개가 모두 틀림",
        "형상은 맞혔는데, 펼친 크기가 정답과 달랐습니다. 콘은 100% 넘게 차이",
        "RUN1 flat_patterns.md 의 도면별 오차 (그때의 정답 기준). 그림은 cone_0023 의 flat_pattern.png.",
    )
    rows = [["도면", "오차", "도면", "오차"]]
    cones = [f"cone_00{n}" for n in range(19, 25)]
    heads = [f"press_formed_00{n}" for n in range(25, 31)]
    for a, b in zip(cones, heads):
        rows.append(
            [
                a,
                flat1.get(a, "–").replace("오차 ", ""),
                b,
                flat1.get(b, "–").replace("오차 ", ""),
            ]
        )
    table(s, X0, 1.85, 7.0, 3.8, rows, [1.9, 1.5, 2.3, 1.3], head_style)
    fit(s, workdir(RUN1, "cone_0023") / "flat_pattern.png", X0 + 7.3, 1.85, 4.83, 3.8)
    band(
        s,
        5.9,
        "문제",
        "AI 가 치수를 잘못 읽었나, 공식이 틀렸나, 정답이 틀렸나? 단계별 기록이 없어 그때는 가릴 수 없었습니다",
        h=0.85,
        size=16,
    )


def lastweek_real_slide(d):
    s = slide(
        d,
        2,
        "실제 회사 도면 5장",
        "커팅플랜에 나온 판재 22종 중, 전개도까지 나온 것은 1개였습니다",
        "2026-10-23 실행 runs/reader/real_drawings_vlm/merged (docs/presentation.md 5절). S-2120 정답 parts.csv 의 판재 22종. 고객 도면이라 그림은 모식도로만.",
    )
    shape(s, MSO_SHAPE.RECTANGLE, X0, 2.0, 3.6, 2.6, WHITE, line=GRAY)
    for x, y in [(0.35, 0.4), (0.35, 1.5), (1.75, 1.5)]:
        shape(s, MSO_SHAPE.RECTANGLE, X0 + x, 2.0 + y, 1.1, 0.85, TEAL_TINT, line=TEAL)
    text(
        s, X0, 4.7, 3.6, 0.4, ["합성: 한 장에 부품 1개"], size=15, align=PP_ALIGN.CENTER
    )
    real_sheet(s, X0 + 4.2, 2.0, 4.0, 2.6)
    text(
        s,
        X0 + 4.2,
        4.7,
        4.0,
        0.4,
        ["실제: 한 장에 부품 여러 개 + 부품표"],
        size=15,
        align=PP_ALIGN.CENTER,
    )
    card(
        s,
        X0 + 8.7,
        2.0,
        3.43,
        2.6,
        [
            {"text": "판재 22종 중", "size": 16},
            {"text": "1개", "size": 40, "bold": True, "color": ORANGE},
            {"text": "전개도까지", "size": 14},
        ],
        fill=ORANGE_TINT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    band(
        s,
        5.5,
        "문제",
        "reader 는 '도면 한 장 = 부품 하나' 를 전제로 만들어졌습니다. 실제 도면은 이 전제가 맞지 않습니다 (v4 에서)",
        h=0.9,
        size=16,
    )


def lastweek_problems_slide(d):
    s = slide(
        d,
        2,
        "지난주에 드러난 문제",
        "실제 도면으로 가기 전에, 쉬운 합성 도면에서 왜 틀리는지부터 알아야 했습니다",
        "docs/v3_upgrade.md 1절.",
    )
    rows = [
        (
            "어디서 틀렸나 모름",
            "형상 · 전개 두 숫자만 있었습니다. 표제란 · 뷰 · 치수는 맞았는지 재지 않았습니다",
        ),
        (
            "답 잘림",
            "형상 실패 3장이 모두 같은 원인. 실행할 때마다 다른 도면이 잘립니다",
        ),
        (
            "정답이 의심스러움",
            "콘 6장이 모두 100% 넘게 틀림. 판독보다 정답 쪽을 봐야 했습니다 (뒤에서: 실제로 틀렸음)",
        ),
        ("실제 도면은 다름", "한 장에 부품 여러 개. 합성에서 완주한 뒤에 할 일"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.9 + i * 1.15
        chip(s, X0, y, 3.0, 0.95, k, fill=ORANGE, color=WHITE, size=17, bold=True)
        card(
            s,
            X0 + 3.2,
            y,
            8.93,
            0.95,
            [v],
            fill=LIGHT,
            size=16,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def devices_section(d):
    section(
        d,
        "4",
        "하네스",
        "PBL 의 핵심 주제: AI 를 믿지 않고 받쳐 주는 장치",
        "JSON 약속, 양식 강제, 다시 묻기, 기록, 그리고 AI 가 도구를 골라 부르는 tool calling.",
    )


# ---------------------------------------------------------------------- 2. 판독 과정 (입력 → 처리 → 출력)
COL_IN, COL_PROC, COL_OUT = (X0, 4.55), (X0 + 4.85, 2.55), (X0 + 7.7, 4.43)


def ipo_block(s, col, item, y=2.25, h=3.6):
    """One input/output column: a picture, a code box, a table or plain lines, with a caption."""
    x, w = col
    kind = item[0]
    if kind == "pic":
        fit(s, item[1], x, y, w, h - 0.4)
    elif kind == "code":
        code(s, x, y, w, h - 0.4, item[1], size=item[3] if len(item) > 3 else 11)
    elif kind == "table":
        rows = item[1]
        table(
            s,
            x,
            y,
            w,
            min(h - 0.4, 0.4 * len(rows)),
            rows,
            [w * 0.5, w * 0.5],
            head_style,
        )
    elif kind == "params":
        params_table(s, RUN3, EXAMPLE, x, y, w)
    elif kind == "lines":
        card(
            s,
            x,
            y,
            w,
            h - 0.4,
            [{"text": t, "bullet": True} for t in item[1]],
            fill=LIGHT,
            size=14,
            after=6,
        )
    text(
        s,
        x,
        y + h - 0.35,
        w,
        0.35,
        [item[2]],
        size=12,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )


def ipo(d, title, message, notes, inp, who, ai, steps, out, point):
    s = slide(d, 1, title, message, notes)
    for (x, w), label in ((COL_IN, "입력"), (COL_PROC, "처리"), (COL_OUT, "출력")):
        chip(s, x, 1.75, w, 0.4, label, fill=INK, color=WHITE, size=14, bold=True)
    ipo_block(s, COL_IN, inp)
    x, w = COL_PROC
    card(
        s,
        x,
        2.25,
        w,
        3.2,
        [{"text": who, "bold": True, "size": 15, "color": WHITE}]
        + [{"text": t, "size": 13, "color": WHITE} for t in steps],
        fill=ORANGE if ai else TEAL,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=6,
        margin=0.12,
    )
    arrow(s, x - 0.27, 3.7, w=0.22, h=0.3)
    arrow(s, x + w + 0.05, 3.7, w=0.22, h=0.3)
    ipo_block(s, COL_OUT, out)
    band(
        s,
        6.0,
        "핵심",
        point,
        fill=TEAL_TINT if not ai else ORANGE_TINT,
        color=TEAL if not ai else ORANGE,
        h=0.75,
        size=15,
    )
    return s


def walkthrough_slides(d):
    w3 = workdir(RUN3, EXAMPLE)
    read = stage_json(RUN3, EXAMPLE, "01_read")
    counts = read.get("entity_counts", {})
    texts = [e.get("text") for e in read.get("entities", []) if e.get("kind") == "text"]
    names = {
        "line": "선",
        "circle": "원",
        "arc": "호",
        "dimension": "치수",
        "dimension_geom": "치수선 조각",
        "text": "글자",
    }
    ipo(
        d,
        "01 읽기",
        "도면 파일을 열어 선 · 원 · 글자를 하나도 빼지 않고 위치와 함께 목록으로 만듭니다",
        f"{EXAMPLE} 의 stages/01_read.json entity_counts {counts}. 모델을 쓰지 않는다 (dxf_reader.read_dxf, ezdxf).",
        ("pic", drawing_png(EXAMPLE), "cone_0023.dxf (도면 파일)"),
        "코드",
        False,
        ["DXF 파일 열기", "선 · 원 · 글자를 모두 꺼냄", "각각의 좌표를 기록"],
        (
            "table",
            [["종류", "개수"]]
            + [[names.get(k, k), str(v)] for k, v in counts.items()]
            + [["합계", str(sum(counts.values()))]],
            "01_read.json: 요소 목록",
        ),
        "여기까지는 AI 없이, 파일에 적힌 그대로를 꺼냅니다. 실제 회사 도면은 2,000 ~ 5,900 개",
    )
    regex = stage_json(RUN3, EXAMPLE, "02_title_regex")
    tb = regex.get("title_block", {})
    ipo(
        d,
        "02 표제란: 글자 규칙",
        "표제란 자리를 찾고, 정해진 글자 규칙(정규식)으로 칸을 채웁니다",
        f"{EXAMPLE} 의 02_title_regex.json. 못 읽은 칸 {regex.get('missing')}. 정규식은 합성 도면의 표제란 모양에 맞춰져 있어 THIRD ANGLE · PART NAME 은 못 읽는다 (v3_upgrade.md 4절 #12).",
        ("code", [repr(t) for t in texts], "01 이 꺼낸 글자 13개", 12),
        "코드 (정규식)",
        False,
        ["'SCALE' 옆 → 축척", "'DW'G NO' 옆 → 도면 번호", "'4t' → 두께 4 mm"],
        (
            "table",
            [
                ["칸", "값"],
                ["도면 번호", str(tb.get("drawing_no"))],
                ["재질", str(tb.get("material"))],
                ["두께", f"{tb.get('thickness_mm')} mm"],
                ["축척", str(tb.get("scale_text"))],
                ["부품명", "못 읽음"],
                ["투상법", "못 읽음"],
            ],
            "02_title_regex.json",
        ),
        "글자로 확실히 적힌 값은 AI 없이 코드가 읽습니다. 못 읽은 칸만 다음 단계로 넘깁니다",
    )
    ocr = stage_json(RUN3, EXAMPLE, "03_title_ocr")
    ipo(
        d,
        "03 표제란: OCR (AI)",
        "표제란 부분만 그림으로 잘라 OCR 모델에게 보여 주고, 보이는 글자를 받아 쓰게 합니다",
        f"{EXAMPLE} 의 analysis/title_block.png 와 03_title_ocr.json 의 text. OCR 모델에게 주는 지시는 'Free OCR.' 한 줄이다 (reader/vlm.py ocr_text).",
        (
            "pic",
            w3 / "analysis" / "title_block.png",
            "title_block.png: 잘라 낸 표제란 그림",
        ),
        "OCR 모델\nDeepSeek-OCR-2",
        True,
        ['지시: "Free OCR."', "그림 속 글자를", "보이는 그대로 받아 씀"],
        ("code", (ocr.get("text") or "").splitlines(), "03_title_ocr.json 의 text", 13),
        "OCR 은 본 것만 씁니다. 그림이 오른쪽에서 잘려 도면 번호가 'SYN-000' 까지만 나왔습니다",
    )
    fields = stage_json(RUN3, EXAMPLE, "04_title_fields")
    ai_tb = fields.get("fields") or {}
    fin = fields.get("title_block") or {}
    ipo(
        d,
        "04 표제란: 정리 (AI)",
        "판단 AI 가 OCR 글자를 표제란 칸으로 정리합니다. 02 가 이미 읽은 칸은 덮어쓰지 않습니다",
        f"{EXAMPLE} 의 04_title_fields.json: fields (AI 답) 와 title_block (최종). 합치는 규칙은 dxf_adapter.apply_title_fields.",
        (
            "code",
            ["OCR 글자 (03):"]
            + [
                "  " + line
                for line in (ocr.get("text") or "").splitlines()
                if line.strip()
            ]
            + ["", "02 가 못 읽은 칸:", "  부품명, 투상법"],
            "03 의 글자 + 02 의 빈칸",
            12,
        ),
        "판단 모델\nQwen3.6-27B",
        True,
        [
            '"OCR 글자를 표제란 칸으로 정리하라"',
            '"모르면 null, 지어내지 말 것"',
            "답은 정해진 JSON 양식",
        ],
        (
            "table",
            [
                ["칸", "AI 답 → 최종"],
                ["부품명", f"{ai_tb.get('part_name')} → {fin.get('part_name')} (채움)"],
                [
                    "도면 번호",
                    f"{ai_tb.get('drawing_no')} → {fin.get('drawing_no')} (02 유지)",
                ],
                ["두께", f"{ai_tb.get('thickness_mm')} → {fin.get('thickness_mm')}"],
                ["축척", f"{ai_tb.get('scale')} → {fin.get('scale_text')}"],
            ],
            "04_title_fields.json",
        ),
        "AI 가 잘린 번호 SYN-000 을 답했지만, 코드가 이미 확실히 읽은 SYN-00023 을 지켰습니다",
    )
    ipo(
        d,
        "05 뷰 찾기",
        "서로 떨어진 선 덩어리를 묶어 뷰 후보로 삼습니다. 표제란과 도면 틀은 뺍니다",
        f"{EXAMPLE} 의 figures/05_views.png (scripts/reader/show_stages.py). dxf_adapter.find_views.",
        ("pic", drawing_png(EXAMPLE), "01 의 선 위치 + 02 의 표제란 위치"),
        "코드",
        False,
        ["가까운 선끼리 한 덩어리", "표제란 · 틀 빼기", "덩어리마다 크기 · 치수 기록"],
        (
            "pic",
            w3 / "figures" / "05_views.png",
            "05_views.json: 뷰 후보 3개 (이름은 아직 없음)",
        ),
        "후보에는 번호만 붙습니다. 어느 것이 정면인지, 무슨 형상인지는 다음 단계의 AI 가 정합니다",
    )
    raw6 = (stage_json(RUN3, EXAMPLE, "06_view_labels").get("decision") or {}).get(
        "raw"
    ) or {}
    scores = raw6.get("part_class_scores") or {}
    views6 = raw6.get("views") or []
    ipo(
        d,
        "06 뷰 이름 · 형상 (AI)",
        "번호 상자를 그린 도면 그림을 보여 주고, 뷰마다 이름을, 형상 6가지에 점수를 매기게 합니다",
        f"{EXAMPLE} 의 analysis/sheet_labeled.png 와 06_view_labels.json decision.raw. 참고 문서 unfold_rules, unfold_extract. 이 호출은 45초 걸렸다.",
        (
            "pic",
            w3 / "analysis" / "sheet_labeled.png",
            "빨간 번호 상자 그림 + 후보별 크기 · 치수 + 참고 문서 2개",
        ),
        "판단 모델\nQwen3.6-27B",
        True,
        ['"뷰마다 이름과 이유"', '"형상 6가지에 점수"', "답은 정해진 JSON 양식"],
        (
            "code",
            ["AI 답 (줄임)"]
            + [f"  {k:13s} {v:+.0f}" for k, v in scores.items()]
            + [""]
            + [
                f"  뷰 {v.get('id')}: {v.get('type')} ({v.get('confidence')})"
                for v in views6
            ],
            "06_view_labels.json",
            12,
        ),
        "점수가 가장 높은 cone 이 형상이 됩니다. 뷰 이름은 위치로 붙인 이름과 대조해 다르면 기록합니다",
    )
    ipo(
        d,
        "07 합치기 · 08 구조화",
        "앞 단계 결과를 한 파일로 모으고, 뷰마다 선과 치수를 붙여 정면 · 평면 · 측면으로 정리합니다",
        "07 은 analysis/sheet_analysis.json 과 sheet.png, 08 은 DrawingDocument (3D 쪽 모델 클래스를 같이 써서 3D 코드를 지우지 않은 이유, v3_upgrade.md 1.1).",
        (
            "lines",
            ["01 요소 목록", "02 · 04 표제란", "05 뷰 후보", "06 뷰 이름 · 형상"],
            "앞 단계의 파일들",
        ),
        "코드",
        False,
        ["결과를 한 파일로", "뷰마다 선 · 치수 붙이기", "축척 검사"],
        ("pic", w3 / "analysis" / "sheet.png", "sheet.png: 최종 이름을 그린 도면"),
        "사람이 한눈에 확인하는 요약 그림이 여기서 나옵니다",
    )
    rec9 = stage_json(RUN3, EXAMPLE, "09_unfold_params").get("record") or {}
    ipo(
        d,
        "09 치수 (AI + 코드)",
        "AI 가 형상별로 전개에 필요한 치수를 읽고, AI 가 비운 칸은 코드가 도면의 외형 치수로 채웁니다",
        f"{EXAMPLE} 의 09_unfold_params.json. AI notes: '{(rec9.get('notes') or '')[:160]}…'. 코드 보충: {rec9.get('fallback_notes')}. 참고 문서 3개 (unfold_extract, unfold_rules, drawing_conventions_kr). 26초.",
        (
            "pic",
            w3 / "analysis" / "sheet_labeled.png",
            "같은 그림 + 뷰별 치수 글자 + 표제란 + 참고 문서 3개",
        ),
        "판단 모델 + 코드",
        True,
        [
            "AI: 콘이면 두께 · 큰 · 작은 안지름 · 높이",
            'AI: 지름은 "도면에 없음" → 비움',
            "코드: 바깥지름 150 · 80 − 2t/cos α",
        ],
        ("params", None, "09_unfold_params.json: 칸마다 누가 채웠나"),
        "AI 가 모르는 값을 지어내지 않고 비웠고, 코드가 도면 치수로 정확히 채웠습니다",
    )
    blank = (stage_json(RUN3, EXAMPLE, "10_develop").get("record") or {}).get(
        "blank"
    ) or {}
    p = rec9.get("params") or {}
    ipo(
        d,
        "10 전개",
        "전개 공식은 코드가 계산합니다. AI 는 계산하지 않습니다",
        f"{EXAMPLE} 의 10_develop.json blank 와 flat_pattern.png. 정답 label.json: R 321.02 · 167.0, 81.8°. 콘 공식은 현업자 정답 기준 (v3_upgrade.md 5.4).",
        (
            "lines",
            [
                f"두께 {p.get('thickness', 0):g}",
                f"큰 안지름 {p.get('large_inner_dia', 0):.1f}",
                f"작은 안지름 {p.get('small_inner_dia', 0):.1f}",
                f"높이 {p.get('cone_height', 0):g}",
            ],
            "09 의 치수",
        ),
        "코드 (공식)",
        False,
        [
            "평균지름 = 안지름 + t/cos α",
            "경사 길이 → 부채꼴 반경",
            "각도 θ = 360° · sin α",
        ],
        (
            "pic",
            w3 / "flat_pattern.png",
            f"전개도: R {blank.get('outer_radius', 0):.1f} · {blank.get('inner_radius', 0):.1f}, {blank.get('angle_deg', 0):.1f}° (정답과 같음)",
        ),
        "지름 10 mm 오차는 둘레 31 mm 오차이고 그 판은 버립니다. 계산은 틀리지 않는 코드에게",
    )


# ---------------------------------------------------------------------- 1. 용어: AI 를 부르는 법
def ai_message_slide(d):
    s = slide(
        d,
        0,
        "AI 를 부르는 법 1: 메시지 한 통",
        "로컬 AI 는 사내 서버에서 도는 프로그램입니다. reader 가 질문 메시지를 보내면 글자로 답이 옵니다",
        "reader/vlm.py VLMClient._call_openai: OpenAI 호환 /chat/completions 로 POST. 서버는 vLLM (experiments/serve.sh). "
        "temperature 0, max_tokens 1500 (VLMConfig 기본값), 시간 제한 120초 (배치에서는 900초).",
    )
    parts = [
        (
            "시스템 지시",
            '역할 + 규칙 문서\n"꼼꼼한 제도 검토자. 지어내지 말 것"',
            TEAL_TINT,
        ),
        ("질문", "이번 일 + 도면 정보\n+ 답 양식", TEAL_TINT),
        ("그림", "도면 그림 (PNG)\n글자로 바꿔 함께 보냄", TEAL_TINT),
    ]
    for i, (head, body, fill) in enumerate(parts):
        card(
            s,
            X0,
            1.85 + i * 1.15,
            3.6,
            1.0,
            [
                {"text": head, "bold": True, "size": 15, "color": TEAL},
                {"text": body, "size": 12},
            ],
            fill=fill,
            after=2,
            margin=0.12,
        )
    text(
        s,
        X0,
        5.35,
        3.6,
        0.4,
        ["질문 메시지 (reader 가 만듦)"],
        size=12,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    arrow(s, X0 + 3.75, 3.4, w=0.4, h=0.35)
    chip(
        s,
        X0 + 4.3,
        2.4,
        2.9,
        2.4,
        "사내 GPU 서버\n(vLLM)\n\nQwen3.6-27B",
        fill=ORANGE,
        color=WHITE,
        size=16,
        bold=True,
    )
    arrow(s, X0 + 7.35, 3.4, w=0.4, h=0.35)
    code(
        s,
        X0 + 7.9,
        1.85,
        4.23,
        3.5,
        [
            "{",
            '  "part_class": "cone",',
            '  "part_class_scores":',
            '     {"cone": 10, "flat": -10, …},',
            '  "views": [',
            '    {"id": 1, "type": "front",',
            '     "confidence": 0.95, …}',
            "  ]",
            "}",
        ],
        size=12,
    )
    text(
        s,
        X0 + 7.9,
        5.35,
        4.23,
        0.4,
        ["답 (정해진 양식의 글자)"],
        size=12,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    rows = [
        ("temperature 0", "매번 가장 그럴듯한 답 하나 (무작위성 끔)"),
        ("답 길이 1,500 토큰", "넘으면 잘림 (장치 2)"),
        ("OCR 모델", '지시는 "Free OCR." 한 줄, 답은 받아쓴 글자'),
    ]
    for i, (k, v) in enumerate(rows):
        y = 5.85 + i * 0.36
        text(s, X0, y, 2.6, 0.34, [k], size=13, bold=True, color=ORANGE)
        text(s, X0 + 2.7, y, 9.4, 0.34, [v], size=13)


def ai_prompt_slide(d):
    s = slide(
        d,
        0,
        "AI 를 부르는 법 2: 지시문 (06 형상)",
        "할 일을 번호 붙여 좁게 적고, 도면에서 코드가 찾은 사실을 함께 줍니다",
        "dxf_adapter.label_with_vlm 의 prompt 와 system (영어 원문을 줄였다). Regions 는 05 가 찾은 뷰 후보의 위치 · 크기 · 치수 글자.",
    )
    code(
        s,
        X0,
        1.85,
        6.6,
        4.9,
        [
            "[system]",
            "You are a careful mechanical drafting checker.",
            "Never invent regions that are not listed.",
            "",
            "[user]",
            "You are reading a 2D mechanical engineering",
            "drawing sheet. Red numbered boxes mark",
            "candidate view regions found by clustering.",
            'Title block: {"drawing_no": "SYN-00023", …}',
            'Regions: [{"id": 1, "bbox_norm": […],',
            '           "dimension_texts": ["150", …]}, …]',
            "1. projection: first or third",
            "2. part_class: one of flat, cylinder, cone,",
            "   press_formed, bent_sheet, other",
            "   + a score for EVERY class",
            "4. For EVERY region give type, confidence,",
            "   and a one-sentence reason …",
        ],
        size=11,
    )
    rows = [
        ("역할", "꼼꼼한 제도 검토자. 목록에 없는 영역을 지어내지 말 것"),
        ("상황", "빨간 번호 상자 = 코드가 찾은 뷰 후보"),
        ("사실", "표제란 값, 후보마다 위치 · 크기 · 치수 글자"),
        ("할 일 1", "투상법 (1각법 / 3각법)"),
        ("할 일 2", "형상 6가지 중 하나 + 모든 형상에 점수"),
        ("할 일 4", "뷰마다 이름, 확신도, 이유 한 문장"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.9 + i * 0.8
        chip(
            s,
            X0 + 6.85,
            y,
            1.4,
            0.62,
            k,
            fill=ORANGE if i > 2 else TEAL,
            color=WHITE,
            size=13,
            bold=True,
        )
        text(s, X0 + 8.4, y, 3.73, 0.62, [v], size=14, anchor=MSO_ANCHOR.MIDDLE)


def ai_skills_slide(d):
    s = slide(
        d,
        0,
        "AI 를 부르는 법 3: 규칙 문서 (skill)",
        "회사의 전개 규칙을 적은 문서를 시스템 지시 앞에 붙입니다. 단계마다 붙이는 문서가 정해져 있습니다",
        "reader/knowledge.py skill_system_prompt 와 STAGE_TOPICS. 문서는 레포의 skills/ (회사 담당자 계산 문서를 옮긴 규칙). 붙인 문서의 sha256 이 단계 파일에 남는다.",
    )
    code(
        s,
        X0,
        1.85,
        7.0,
        3.6,
        [
            "skills/01_core_knowledge/unfold_rules.md  (줄임)",
            "",
            "| 부품  | 전개  | 전개 형상          |",
            "| SHELL | 필요  | 원통 → 직사각형 L = π(ID+t) |",
            "| CONE  | 필요  | 원뿔대 → 환형 부채꼴  |",
            "| HEAD  | 조건부 | 블랭크 원판 지름    |",
            "",
            "## 파라미터 읽기 규칙",
            "- cone_frustum: 큰쪽/작은쪽 안지름과 수직 높이.",
            "  모선 길이만 있으면 높이로 환산 …",
        ],
        size=12,
    )
    rows = [
        ["단계", "붙이는 문서"],
        ["06 형상", "unfold_rules, unfold_extract"],
        ["09 치수", "+ drawing_conventions_kr"],
        ["03 · 04", "없음"],
    ]
    table(s, X0 + 7.3, 1.85, 4.83, 1.8, rows, [1.5, 3.33], head_style)
    text(
        s,
        X0 + 7.3,
        3.8,
        4.83,
        1.6,
        [
            "문서 3개, 각 4.6 ~ 5.3 KB. 한국어 표와 규칙 그대로 붙입니다. 출력 양식이 문서와 다르면 '답 양식을 따르고 규칙만 쓰라' 고 덧붙입니다"
        ],
        size=14,
    )
    band(
        s,
        5.75,
        "왜",
        "모델을 다시 학습시키지 않고, 회사 규칙을 읽혀서 판단하게 합니다. 규칙을 고치면 문서만 고치면 됩니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.85,
        size=15,
    )


def ai_contract_slide(d):
    s = slide(
        d,
        0,
        "AI 를 부르는 법 4: 답 양식",
        "질문 끝에 '이 양식의 JSON 하나만 답하라' 를 붙이고, 서버가 양식 밖의 글자를 못 쓰게 막습니다",
        "vlm_output.output_instructions (OUTPUT CONTRACT) 와 response_schema. 서버에는 response_format json_schema, strict (vLLM structured outputs, xgrammar). 받은 답은 vlm_output 의 _validate 로 다시 검사한다.",
    )
    code(
        s,
        X0,
        1.85,
        6.4,
        2.9,
        [
            "OUTPUT CONTRACT:",
            "Return ONE JSON object matching the schema,",
            "without Markdown or prose.",
            "Use null for unknown scalar facts;",
            "never invent values or scores.",
            "Confidence must be between 0 and 1.",
            '{"type": "object", "properties": {…}}',
        ],
        size=12,
    )
    rows = [
        ("JSON 하나만", "설명문 · 표 없이 정해진 칸만"),
        ("모르면 null", "값이나 점수를 지어내지 말 것"),
        ("범위", "확신도 0 ~ 1, 축척은 1/4 같은 글자"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 1.95 + i * 0.95
        chip(s, X0 + 6.7, y, 1.9, 0.7, k, fill=ORANGE, color=WHITE, size=14, bold=True)
        text(s, X0 + 8.75, y, 3.38, 0.7, [v], size=14, anchor=MSO_ANCHOR.MIDDLE)
    steps = [
        ("서버", "양식에 맞는 글자만\n고를 수 있게 막음"),
        ("코드 검사", "칸 · 종류 · 범위 확인\n틀리면 버림"),
        ("통과", "다음 단계로"),
    ]
    for i, (k, v) in enumerate(steps):
        x = X0 + i * 4.15
        card(
            s,
            x,
            5.0,
            3.7,
            1.15,
            [{"text": k, "bold": True, "size": 15}, {"text": v, "size": 13}],
            fill=TEAL_TINT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
        if i < 2:
            arrow(s, x + 3.75, 5.45, w=0.35, h=0.28)
    text(
        s,
        X0,
        6.3,
        CW,
        0.4,
        ["왜 JSON 인지, 서버가 어떻게 양식을 강제하는지는 4. 하네스 파트에서 자세히"],
        size=13,
        color=GRAY,
    )


def ai_client_slide(d):
    s = slide(
        d,
        0,
        "AI 를 부르는 법 5: 한 번의 호출 (VLMClient)",
        "reader 의 VLMClient 가 매번 같은 순서로 묻고, 검사하고, 기록합니다",
        "reader/vlm.py VLMClient.ask. 설정은 환경변수 CUTPLAN_REASON_* / CUTPLAN_OCR_* 또는 experiments/models/*.sh 프로필. 같은 코드로 로컬(vLLM)과 Claude(Anthropic API)를 모두 부를 수 있다.",
    )
    steps = [
        ("1", "설정", "서버 주소, 모델 이름"),
        ("2", "규칙 문서", "단계별 skill 붙이기"),
        ("3", "답 양식", "OUTPUT CONTRACT 붙이기"),
        ("4", "그림", "PNG 를 글자로 바꿔 첨부"),
        ("5", "보내기", "서버에 질문, 답 받기"),
        ("6", "잘렸나?", "잘렸으면 짧게 한 번 더"),
        ("7", "검사", "JSON 양식 확인"),
        ("8", "기록", "그림 · 문서 · 원문 · 시간"),
    ]
    for i, (n, head, body) in enumerate(steps):
        row, col = divmod(i, 4)
        x = X0 + col * 3.05
        y = 1.95 + row * 2.0
        ai = n in ("5", "6")
        card(
            s,
            x,
            y,
            2.75,
            1.6,
            [
                {"text": f"{n}. {head}", "bold": True, "size": 16, "color": WHITE},
                {"text": body, "size": 13, "color": WHITE},
            ],
            fill=ORANGE if ai else TEAL,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=4,
        )
        if col < 3:
            arrow(s, x + 2.78, y + 0.65, w=0.24, h=0.28, fill=PALE)
    band(
        s,
        6.0,
        "요점",
        "AI 가 하는 일은 5 하나뿐입니다. 나머지 일곱 칸이 하네스입니다",
        h=0.75,
        size=16,
    )


# ---------------------------------------------------------------------- 4. 하네스: JSON 과 tool calling
DEMO = RUNS / "agent" / "orchestrator" / "20261023-021136"


def demo_turns():
    """The cone_0019 orchestrator run: model turns and tool results, in order."""
    path = DEMO / "trajectory.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def harness_eng_slide(d):
    s = slide(
        d,
        3,
        "하네스 엔지니어링: PBL 의 핵심 주제",
        "모델을 바꾸거나 학습시키는 대신, 모델을 둘러싼 장치를 설계해서 결과를 믿을 수 있게 만듭니다",
        "docs/harness_engineering.md. 최종 목표는 orchestration 과 각 작업을 모두 로컬 LLM 이 맡는 하네스다.",
    )
    rows = [
        ("단계로 나누기", "AI 에게는 좁은 판단 하나씩만. 계산은 코드", "판독 10단계"),
        ("JSON 약속", "AI 의 답을 정해진 칸으로 받고, 양식 밖은 못 쓰게", "다음 장"),
        ("검사 · 다시 묻기", "칸 · 범위 검사, 잘리면 짧게 다시", "장치 2"),
        ("기록", "무엇을 보여 주고 뭐라 답했는지 파일로", "장치 3"),
        ("도구 호출 반복", "AI 가 단계를 골라 부르고, 코드가 실행", "tool calling"),
    ]
    for i, (head, body, where) in enumerate(rows):
        y = 1.9 + i * 0.85
        chip(s, X0, y, 2.6, 0.68, head, fill=TEAL, color=WHITE, size=16, bold=True)
        text(s, X0 + 2.85, y, 7.0, 0.68, [body], size=16, anchor=MSO_ANCHOR.MIDDLE)
        text(
            s,
            X0 + 9.9,
            y,
            2.2,
            0.68,
            [where],
            size=14,
            color=GRAY,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    band(
        s,
        6.2,
        "가설",
        "작은 로컬 AI 라도 하네스가 받쳐 주면 쓸 만하다. 이 덱의 모든 장치가 이 가설을 위한 것",
        h=0.65,
        size=15,
    )


def json_contract_slide(d):
    s = slide(
        d,
        3,
        "JSON: AI 와 코드 사이의 약속",
        "AI 는 글을 씁니다. 코드는 정해진 칸만 읽습니다. 둘을 잇는 것이 JSON 입니다",
        "JSON 은 '이름: 값' 칸으로 된 글자 형식이다. reader 의 모든 AI 답, 단계 사이 파일(stages/*.json), 도구 호출이 JSON 이다.",
    )
    card(
        s,
        X0,
        1.9,
        5.6,
        1.6,
        [
            {"text": "자유 문장으로 답하면", "bold": True, "size": 15, "color": GRAY},
            {"text": '"아마 콘 같습니다. 큰 지름은 150 정도로 보이고 …"', "size": 15},
        ],
        fill=LIGHT,
        after=6,
    )
    text(
        s,
        X0,
        3.55,
        5.6,
        0.5,
        ["→ 코드는 어디가 형상이고 어디가 숫자인지 모릅니다"],
        size=14,
        color=GRAY,
    )
    code(
        s,
        X0 + 6.5,
        1.9,
        5.63,
        1.6,
        [
            '{"part_class": "cone",',
            ' "part_class_scores": {"cone": 10, …},',
            ' "views": [{"id": 1, "type": "front"}]}',
        ],
        size=13,
    )
    text(
        s,
        X0 + 6.5,
        3.55,
        5.63,
        0.5,
        ['→ 코드가 reply["part_class"] 로 바로 꺼냅니다'],
        size=14,
        color=TEAL,
        bold=True,
    )
    rows = [
        ("AI 의 답", "06 형상, 09 치수, 04 표제란: 칸이 정해진 JSON"),
        ("단계 사이", "01_read.json → 02 → … 다음 단계는 앞 JSON 만 읽음"),
        ("도구 호출", 'AI 가 {"tool": …, "arguments": …} 로 할 일을 고름'),
    ]
    for i, (k, v) in enumerate(rows):
        y = 4.25 + i * 0.7
        chip(s, X0, y, 2.2, 0.56, k, fill=ORANGE, color=WHITE, size=14, bold=True)
        text(s, X0 + 2.4, y, 9.7, 0.56, [v], size=15, anchor=MSO_ANCHOR.MIDDLE)
    text(
        s,
        X0,
        6.4,
        CW,
        0.4,
        [
            "칸이 정해져 있으니 검사할 수 있고(장치 2), 기록할 수 있고(장치 3), 서버가 양식을 강제할 수 있습니다(다음 장)"
        ],
        size=13,
        color=GRAY,
    )


def decoding_slide(d):
    s = slide(
        d,
        3,
        "하네스 장치 1: 양식 강제 (제약 디코딩)",
        "AI 는 다음 글자를 하나씩 골라 씁니다. 서버가 그때마다 양식에 맞지 않는 후보를 지웁니다",
        "vLLM structured outputs (xgrammar), 요청의 response_format json_schema strict. 양식은 vlm_output.response_schema. 받은 답은 코드가 한 번 더 검사한다 (_validate). 칸 하나라도 틀리면 응답 전체를 버린다.",
    )
    code(s, X0, 1.9, 5.2, 0.7, ['{"part_class": "▮'], size=16)
    text(
        s,
        X0,
        2.65,
        5.2,
        0.4,
        ["지금까지 쓴 글자. 다음에 올 글자는?"],
        size=13,
        color=GRAY,
    )
    cands = [
        ("cone", True),
        ("flat", True),
        ("cylinder", True),
        ("원뿔", False),
        ("probably", False),
        ("press_formed", True),
    ]
    for i, (c, ok) in enumerate(cands):
        x = X0 + (i % 3) * 1.75
        y = 3.2 + (i // 3) * 0.75
        chip(
            s,
            x,
            y,
            1.6,
            0.6,
            c,
            fill=TEAL if ok else LIGHT,
            color=WHITE if ok else GRAY,
            size=14,
            bold=ok,
        )
    text(
        s,
        X0,
        4.75,
        5.2,
        0.6,
        ["청록 = 허용 (형상 6가지 이름만), 회색 = 서버가 지움"],
        size=13,
        color=GRAY,
    )
    steps = [
        ("질문 + 양식", "형상: 6가지 중 하나\n점수: 숫자"),
        ("서버", "매 글자 양식 밖 후보 삭제"),
        ("코드 검사", "칸 · 종류 · 범위"),
    ]
    for i, (k, v) in enumerate(steps):
        y = 1.9 + i * 1.2
        card(
            s,
            X0 + 6.0,
            y,
            3.4,
            1.0,
            [{"text": k, "bold": True, "size": 15}, {"text": v, "size": 12}],
            fill=ORANGE_TINT if i == 1 else TEAL_TINT,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
        )
    chip(
        s,
        X0 + 9.75,
        1.9,
        2.38,
        1.0,
        "통과 → 다음 단계",
        fill=TEAL,
        color=WHITE,
        size=13,
        bold=True,
    )
    chip(
        s,
        X0 + 9.75,
        3.1,
        2.38,
        1.0,
        "거부 → 실패 기록",
        fill=GRAY,
        color=WHITE,
        size=13,
        bold=True,
    )
    band(
        s,
        5.55,
        "효과",
        "없는 형상 이름, 산문, 표를 쓸 수 없습니다. 실패해도 어디서 왜인지 남습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.6,
        size=15,
    )
    band(
        s,
        6.25,
        "한계",
        "양식은 지키는데 답이 길어 중간에 잘리면 JSON 이 깨집니다 → 장치 2",
        h=0.6,
        size=15,
    )


def tool_idea_slide(d):
    s = slide(
        d,
        3,
        "tool calling: AI 는 함수를 실행하지 않습니다",
        "Qwen 은 '어느 도구를, 어떤 값으로' 부를지 JSON 으로 적기만 합니다. 실행은 Python 코드가 합니다",
        "reader/orchestrator.py (반복), reader/tools.py (도구와 실행). 개념은 docs/reader/orchestrator.md 2.1절. 그림의 JSON 은 cone_0019 시연의 실제 두 번째 답.",
    )
    chip(
        s,
        X0,
        2.0,
        2.3,
        1.1,
        '사용자\n"cone_0019 를\n전개도까지"',
        fill=LIGHT,
        color=INK,
        size=13,
    )
    arrow(s, X0 + 2.4, 2.4, w=0.35, h=0.3)
    chip(
        s,
        X0 + 2.85,
        1.9,
        2.0,
        1.3,
        "Qwen\n(고르기만)",
        fill=ORANGE,
        color=WHITE,
        size=16,
        bold=True,
    )
    arrow(s, X0 + 4.95, 2.4, w=0.35, h=0.3)
    code(
        s,
        X0 + 5.4,
        1.85,
        6.73,
        1.45,
        [
            '{"thought": "아직 실행된 단계가 없으므로 …",',
            ' "tool": "run_stages",',
            ' "arguments": {"work": "runs/reader/agent/cone_0019",',
            '               "first": "read", "last": "develop"}}',
        ],
        size=12,
    )
    arrow(s, X0 + 8.6, 3.4, w=0.3, h=0.4, kind=MSO_SHAPE.DOWN_ARROW)
    chip(
        s,
        X0 + 5.4,
        3.9,
        6.73,
        1.0,
        'Python: ReaderTools.call("run_stages", {...})\n→ 실제로 stages/read.py … develop.py 실행 (92초)',
        fill=TEAL,
        color=WHITE,
        size=14,
        bold=True,
    )
    arrow(s, X0 + 4.95, 4.2, w=0.35, h=0.3, kind=MSO_SHAPE.LEFT_ARROW)
    card(
        s,
        X0 + 2.85,
        3.85,
        2.0,
        1.1,
        [
            {"text": "결과 JSON 을", "size": 13},
            {"text": "대화에 붙여", "size": 13},
            {"text": "다시 묻기", "size": 13, "bold": True},
        ],
        fill=ORANGE_TINT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=0,
    )
    arrow(s, X0 + 3.7, 3.3, w=0.3, h=0.45, kind=MSO_SHAPE.UP_ARROW)
    band(
        s,
        5.4,
        "핵심",
        "모델은 이름과 값을 고르고, 실행 · 검사 · 기록은 코드가 합니다. 이걸 끝날 때까지 반복합니다",
        h=0.75,
        size=16,
    )
    text(
        s,
        X0,
        6.3,
        CW,
        0.4,
        [
            "ChatGPT 의 '도구 사용' 도 같은 원리입니다. 모델은 글만 쓰고, 글을 읽어 실행하는 프로그램이 따로 있습니다"
        ],
        size=13,
        color=GRAY,
    )


def tool_list_slide(d):
    s = slide(
        d,
        3,
        "도구 목록 (tools.py)",
        "도구 하나 = 이름 + 설명 + 인자 양식 + 실제로 부를 Python 함수. 모델에게는 앞의 셋만 보입니다",
        "tools.py _build(): run_<단계> 는 STAGES 를 돌며 자동으로 만들고 설명은 단계 스크립트의 docstring 에서 가져온다. _stage_caller() 가 stages/<단계>.py 의 run 을 부르는 클로저라, 도구로 부르든 main.py --batch 로 돌리든 같은 파일이 생긴다. "
        "call(): 이름으로 찾고 인자를 검사한 뒤 실행. 에러는 예외 대신 {'error': ...} 로 돌려준다. 도구 17개는 2026-10-23 기준 (3D 를 끈 뒤 3D 단계 도구는 빠졌다).",
    )
    code(
        s,
        X0,
        1.85,
        6.4,
        3.9,
        [
            '{"name": "run_view_labels",',
            ' "description": "Stage 06 view_labels: name every',
            "   view cluster. Model: reasoning (with the",
            "   part_class skills). Reads stages/01_read.json,",
            '   stages/04_title_fields.json, stages/05_views.json.",',
            ' "parameters": {',
            '   "properties": {',
            '     "work": {"type": "string"},',
            '     "projection_default":',
            '        {"enum": ["first", "third"]}},',
            '   "required": ["work"]}}',
        ],
        size=11,
    )
    text(
        s,
        X0,
        5.8,
        6.4,
        0.4,
        ["모델에게 보이는 도구 설명 (실제 기록 command.json)"],
        size=12,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    groups = [
        ("보기", "list_drawings · stage_status · show_stage"),
        ("단계 실행", "run_read … run_develop (단계마다 하나)"),
        ("묶어 실행", "run_stages (처음 ~ 끝 단계)"),
    ]
    for i, (k, v) in enumerate(groups):
        y = 1.9 + i * 0.85
        chip(s, X0 + 6.7, y, 1.6, 0.68, k, fill=TEAL, color=WHITE, size=14, bold=True)
        text(s, X0 + 8.45, y, 3.68, 0.68, [v], size=13, anchor=MSO_ANCHOR.MIDDLE)
    card(
        s,
        X0 + 6.7,
        4.55,
        5.43,
        1.6,
        [
            {
                "text": "실행 담당 call(이름, 인자)",
                "bold": True,
                "size": 14,
                "color": TEAL,
            },
            {"text": '없는 도구 · 틀린 인자 → {"error": …} 로 돌려줌', "size": 13},
            {"text": "모델이 에러를 읽고 다른 방법을 고름", "size": 13},
        ],
        fill=TEAL_TINT,
        after=3,
    )


def tool_loop_slide(d):
    s = slide(
        d,
        3,
        "대화 반복 (orchestrator.py)",
        "묻고 → 실행하고 → 결과를 붙여 다시 묻기. 모델이 도구 없이 답하면 그게 최종 보고입니다",
        "orchestrator.py orchestrate(). 매 턴과 도구 결과가 trajectory.jsonl, 전체 대화가 messages.json 에 남는다 (scripts/reader/show_trajectory.py 로 본다). 최대 40턴.",
    )
    code(
        s,
        X0,
        1.9,
        6.6,
        3.0,
        [
            "for turn in range(1, 41):",
            "  reply = backend.next()       # 1. 모델에게 묻기",
            "  if not reply.calls:          # 도구 없이 답하면",
            "    return reply.text          #    최종 보고",
            "  for call in reply.calls:",
            "    result = tools.call(call.name, call.arguments)",
            "                               # 2. Python 실행",
            "  backend.add_results(results) # 3. 결과 붙이기",
        ],
        size=12,
    )
    cx, cy = X0 + 9.4, 3.4
    nodes = [
        (cx, cy - 1.45, "1. 모델에게 묻기", ORANGE),
        (cx + 1.6, cy, "2. 도구 실행", TEAL),
        (cx, cy + 1.45, "3. 결과 붙이기", TEAL),
        (cx - 1.6, cy, "끝? → 보고", GRAY),
    ]
    for x, y, label, c in nodes:
        chip(
            s,
            x - 0.95,
            y - 0.35,
            1.9,
            0.7,
            label,
            fill=c,
            color=WHITE,
            size=13,
            bold=True,
        )
    for (x1, y1), (x2, y2) in [
        ((cx + 0.6, cy - 1.1), (cx + 1.4, cy - 0.35)),
        ((cx + 1.4, cy + 0.35), (cx + 0.6, cy + 1.1)),
        ((cx, cy + 1.05), (cx, cy - 1.05)),
        ((cx - 0.6, cy - 1.1), (cx - 1.4, cy - 0.35)),
    ]:
        connect(s, x1, y1, x2, y2, color=PALE, width=2.5)
    band(
        s,
        5.4,
        "하네스",
        "반복 횟수 제한, 에러를 모델에게 돌려주기, 모든 턴 기록. 모델이 길을 잃어도 프로그램은 멈추지 않습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.85,
        size=15,
    )


def tool_modes_slide(d):
    s = slide(
        d,
        3,
        "도구를 알려주는 세 가지 방법",
        "같은 반복 위에서, 모델에게 도구를 알려주고 답을 꺼내는 방법만 다릅니다",
        "orchestrator.py: OpenAITools, OpenAISchema, AnthropicTools. 시연(cone_0019)은 schema 모드. 2026-10-23 추론 서버는 --tool-call-parser 없이 떠 있어 tools 방식 요청이 400 이었다 (docs/presentation.md 6절).",
    )
    rows = [
        ["방식", "도구를 알려주는 법", "모델의 선택을 꺼내는 법"],
        [
            "tools (OpenAI 표준)",
            "요청의 tools 칸. vLLM 이 Qwen 이 학습한 형식으로 넣어 줌",
            "vLLM 의 tool parser 가 꺼낸 tool_calls",
        ],
        [
            "schema (시연에 씀)",
            "도구 설명을 시스템 지시에 글로",
            "답을 {thought, tool, arguments} JSON 으로 강제, 코드가 읽음",
        ],
        ["Claude", "Claude API 의 tools", "답의 tool_use 블록"],
    ]
    table(s, X0, 1.9, CW, 2.6, rows, [2.6, 4.8, 4.733], head_style)
    code(
        s,
        X0,
        4.75,
        7.3,
        1.85,
        [
            '"anyOf": [',
            '  {"tool": {"const": "run_read"},    "arguments": {work, drawing}},',
            '  {"tool": {"const": "show_stage"},  "arguments": {work, stage}},',
            '  … 도구마다 한 줄,  {"tool": {"const": "finish"}, …}]',
        ],
        size=11,
    )
    text(
        s,
        X0 + 7.6,
        4.75,
        4.53,
        1.85,
        [
            "schema 모드는 '이 도구면 이 인자' 를 모두 나열합니다. 그래서 없는 도구 이름이나 맞지 않는 인자는 처음부터 쓸 수 없습니다 (장치 1 의 제약 디코딩)"
        ],
        size=14,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def tool_demo_slide(d):
    turns = [t for t in demo_turns() if "text" in t]
    results = [t for t in demo_turns() if "tool" in t]
    s = slide(
        d,
        3,
        "시연: cone_0019 실제 대화",
        '"cone_0019 도면을 전개도까지 판독하고 결과를 알려줘" → AI 판단 3번, 133초',
        f"{DEMO.relative_to(ROOT)} 의 trajectory.jsonl (2026-10-23, schema 모드, Qwen3.6-27B, 옛 합성 도면). 보고의 작은 지름 92.0 은 모델이 읽은 값이고 정답은 100 이다. 프롬프트 토큰은 턴마다 2,318 → 2,470 → 4,328 로 늘었다 (결과가 대화에 쌓임).",
    )
    rows = [["턴", "시각", "Qwen 이 고른 것", "Python 이 실행한 결과"]]
    for t in turns:
        calls = t.get("calls") or []
        pick = (
            ", ".join(
                f"{c['name']}({', '.join(f'{k}={v}' for k, v in c['arguments'].items() if k != 'work' and k != 'drawing')})"
                for c in calls
            )
            or "finish (보고)"
        )
        res = next((r for r in results if r["turn"] == t["turn"]), None)
        if res:
            out = res["result"]
            summary = f"{res['seconds']}초, " + (
                f"status {out.get('status')}, 단계 {len(out.get('stages', []))}개"
                if "stages" in out
                else f"work = {out.get('drawings', [{}])[0].get('work')}"
            )
        else:
            summary = "형상 원추대, 전개 R 405.65 · 252.87, 68.33°"
        rows.append([str(t["turn"]), f"{t['seconds']}초", pick, summary])
    table(s, X0, 1.85, CW, 2.2, rows, [0.7, 1.1, 5.0, 5.333], head_style)
    for i, t in enumerate(turns[:2]):
        text(
            s,
            X0,
            4.3 + i * 0.6,
            CW,
            0.55,
            [
                [
                    {
                        "text": f"턴 {t['turn']} thought  ",
                        "bold": True,
                        "color": ORANGE,
                        "size": 13,
                    },
                    {"text": t["text"], "size": 13},
                ]
            ],
        )
    band(
        s,
        5.75,
        "보인 것",
        "모델은 도구 이름과 인자만 골랐고, 판독 10단계는 코드가 돌렸습니다. 숫자를 지어내지 않고 단계 결과를 옮겨 보고했습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.85,
        size=15,
    )


# ---------------------------------------------------------------------- 부록: 하네스 구조
def concept_slide(d, title, message, notes):
    return slide(d, 6, title, message, notes)


def role_box(s, x, y, w, h, name, role, where, *, fill=TEAL, size=15):
    """A part of the harness: its name, what it does, and (small) where it lives in code."""
    card(
        s,
        x,
        y,
        w,
        h,
        [
            {"text": name, "bold": True, "size": size, "color": WHITE},
            {"text": role, "size": 12, "color": WHITE},
        ],
        fill=fill,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        after=3,
        margin=0.1,
    )
    text(
        s,
        x,
        y + h + 0.02,
        w,
        0.3,
        [f"코드: {where}"],
        size=10,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )


def concept_parts_slide(d):
    s = concept_slide(
        d,
        "부록 · 하네스 구조 1: 다섯 부품",
        "모델은 가운데 한 부품일 뿐입니다. 나머지 넷은 모델을 둘러싼 코드입니다",
        "orchestrator.py: orchestrate (진행), OpenAITools / OpenAISchema / AnthropicTools (연결부), "
        "system_prompt (지시문), Log (기록). tools.py: ReaderTools, Tool (도구 상자). "
        "실행 진입점은 main 이고, make_backend 가 연결부를 고른다.",
    )
    # 연결선을 먼저 그려 상자 밑으로 가게 한다
    connect(s, 2.6, 3.65, 4.6, 3.65, color=GRAY, width=2)
    connect(s, 7.6, 3.65, 9.4, 3.65, color=GRAY, width=2)
    connect(s, 6.1, 3.05, 6.1, 2.85, color=GRAY, width=2)
    connect(s, 6.1, 4.55, 6.1, 5.0, color=GRAY, width=2)
    chip(s, X0, 3.2, 2.0, 0.9, "사용자 명령\n'cone_0019 판독해줘'", size=12)
    role_box(
        s,
        4.6,
        3.05,
        3.0,
        1.2,
        "진행",
        "묻기 → 실행 → 결과 전달을 반복",
        "orchestrate()",
        fill=INK,
    )
    role_box(
        s,
        4.35,
        1.55,
        3.5,
        1.0,
        "모델 (AI)",
        "다음에 쓸 도구를 고르기만 함",
        "backend (구조 3)",
        fill=ORANGE,
    )
    role_box(
        s,
        9.4,
        3.05,
        3.33,
        1.2,
        "도구 상자",
        "판독 단계를 실제로 실행",
        "ReaderTools · Tool",
    )
    role_box(
        s,
        4.6,
        5.0,
        3.0,
        0.95,
        "기록",
        "모든 질문 · 답 · 결과를 파일로",
        "Log",
        fill=GRAY,
    )
    role_box(
        s,
        X0,
        1.55,
        3.2,
        1.0,
        "지시문",
        "역할 · 순서 · 금지 사항",
        "system_prompt()",
        fill=TEAL,
    )
    connect(s, X0 + 3.2, 2.05, 4.35, 2.05, color=GRAY, width=2)
    card(
        s,
        9.4,
        4.75,
        3.33,
        1.65,
        [
            {"text": "왜 나눴나", "bold": True, "size": 14, "color": TEAL},
            {
                "text": "모델을 바꿔도 도구는 그대로, 도구를 늘려도 진행은 그대로입니다. 부품마다 따로 고치고 따로 시험합니다",
                "size": 12,
            },
        ],
        fill=TEAL_TINT,
        after=3,
    )


def concept_tool_slide(d):
    s = concept_slide(
        d,
        "부록 · 하네스 구조 2: 도구 상자",
        "모델에게는 도구의 이름과 설명만 보입니다. 실제 실행은 보이지 않는 코드가 합니다",
        "tools.py 의 Tool(name, description, parameters, call): 앞 셋은 모델에게 보내는 목록, call 은 Python 함수. "
        "ReaderTools._build 가 판독 단계 목록(STAGES)에서 run_<단계> 도구를 자동으로 만들고, 설명은 단계 스크립트의 docstring 에서 가져온다. "
        "단계가 쓰는 OCR · 판단 모델은 명령줄에서 정해지고, 오케스트레이터는 단계와 옵션만 고른다.",
    )
    card(s, X0, 1.85, 5.6, 4.0, [], fill=ORANGE_TINT)
    text(
        s,
        X0 + 0.2,
        1.95,
        5.2,
        0.4,
        ["모델에게 보이는 것"],
        size=16,
        bold=True,
        color=ORANGE,
    )
    menu = [
        ("run_view_labels", "뷰마다 정면 · 측면 이름을 붙인다"),
        ("run_develop", "전개도 길이를 계산한다"),
        ("run_stages", "여러 단계를 차례로 실행한다"),
        ("show_stage", "한 단계의 결과를 본다"),
    ]
    for i, (k, v) in enumerate(menu):
        y = 2.5 + i * 0.75
        chip(s, X0 + 0.2, y, 2.3, 0.6, k, fill=ORANGE, color=WHITE, size=12, bold=True)
        text(s, X0 + 2.65, y, 2.9, 0.6, [v], size=12, anchor=MSO_ANCHOR.MIDDLE)
    text(
        s,
        X0 + 0.2,
        5.5,
        5.2,
        0.3,
        ["…그리고 도구마다 받는 값(인자)의 양식"],
        size=11,
        color=GRAY,
    )
    arrow(s, X0 + 5.75, 3.65, w=0.5, h=0.4)
    card(s, X0 + 6.4, 1.85, 5.73, 4.0, [], fill=LIGHT)
    text(
        s,
        X0 + 6.6,
        1.95,
        5.3,
        0.4,
        ["보이지 않는 것 (코드가 정함)"],
        size=16,
        bold=True,
        color=TEAL,
    )
    hidden = [
        ("실행", "고른 도구 이름에 맞는 판독 단계를 실제로 돌림"),
        ("사용할 AI", "단계 안의 OCR · 판단 모델은 미리 고정"),
        ("쓸 수 있는 곳", "출력 폴더 아래에만 파일을 씀"),
        ("돌려줄 것", "단계 파일 전체가 아니라 짧은 요약만"),
    ]
    for i, (k, v) in enumerate(hidden):
        y = 2.5 + i * 0.75
        chip(s, X0 + 6.6, y, 1.8, 0.6, k, fill=TEAL, color=WHITE, size=12, bold=True)
        text(s, X0 + 8.55, y, 3.5, 0.6, [v], size=12, anchor=MSO_ANCHOR.MIDDLE)
    band(
        s,
        6.05,
        "하네스",
        "모델이 할 수 있는 일의 범위는 '도구 목록' 이 정합니다. 목록에 없는 일은 할 수 없습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.7,
        size=14,
    )


def concept_adapter_slide(d):
    s = concept_slide(
        d,
        "부록 · 하네스 구조 3: 모델 연결부",
        "모델마다 답하는 형식이 다릅니다. 연결부가 하나의 공통 형식으로 바꿔 주므로 모델을 바꿔 끼울 수 있습니다",
        "orchestrator.py 의 backend 세 가지(OpenAITools, OpenAISchema, AnthropicTools)는 모두 start · next · add_results 를 가진다. "
        "공통 형식은 Turn(text, calls, stop, usage)과 Call(id, name, arguments). "
        "schema 방식은 tool parser 가 없는 vLLM 을 위해 답 양식을 anyOf {thought, tool, arguments} 로 강제한다. 시연 cone_0019 는 이 방식이다.",
    )
    models = [
        ("로컬 Qwen", "도구 호출 기능 사용", "tools"),
        ("로컬 Qwen", "답 양식을 강제", "schema"),
        ("Claude", "도구 호출 기능 사용", "anthropic"),
    ]
    for i, (k, v, mode) in enumerate(models):
        y = 1.9 + i * 1.2
        card(
            s,
            X0,
            y,
            3.0,
            1.0,
            [
                {"text": k, "bold": True, "size": 15, "color": WHITE},
                {"text": v, "size": 12, "color": WHITE},
                {"text": f"--tool-mode {mode}", "size": 9, "color": WHITE},
            ],
            fill=ORANGE,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            after=2,
            margin=0.1,
        )
        connect(s, X0 + 3.0, y + 0.5, 4.9, 3.6, color=GRAY, width=1.5)
    role_box(
        s,
        4.9,
        2.9,
        2.6,
        1.4,
        "연결부",
        "질문 보내기 · 답 받기 · 결과 붙이기",
        "backend",
        fill=TEAL,
    )
    arrow(s, 7.6, 3.4, w=0.5, h=0.4)
    card(
        s,
        8.2,
        2.55,
        4.53,
        2.1,
        [
            {"text": "공통 형식", "bold": True, "size": 15, "color": TEAL},
            {"text": "• 모델이 쓴 생각 · 보고 글", "size": 13},
            {"text": "• 부른 도구 이름과 인자", "size": 13},
            {"text": "• 멈춘 이유 (끝냄 / 도구 호출)", "size": 13},
            {"text": "• 쓴 글자 수 (토큰)", "size": 13},
        ],
        fill=TEAL_TINT,
        after=4,
    )
    text(
        s,
        8.2,
        4.7,
        4.53,
        0.3,
        ["코드: Turn · Call"],
        size=10,
        color=GRAY,
        align=PP_ALIGN.CENTER,
    )
    band(
        s,
        5.95,
        "그래서",
        "진행 · 도구 · 기록은 하나만 있으면 됩니다. 같은 일을 로컬 모델과 Claude 에 시켜 비교할 수 있습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.75,
        size=14,
    )


def concept_rules_slide(d):
    s = concept_slide(
        d,
        "부록 · 하네스 구조 4: 규칙을 거는 두 가지 방법",
        "글로 부탁한 규칙은 모델이 어길 수 있습니다. 중요한 규칙은 코드 구조로 막습니다",
        "글로 부탁: orchestrator.py system_prompt (역할, 순서, 직접 계산 금지, 결과 값만 인용, 정답 파일 금지). "
        "구조로 강제: 도구 목록(ReaderTools._build), 인자 검사(ReaderTools.call), 폴더 제한(ReaderTools.workspace), "
        "답 양식(OpenAISchema 의 response_format), 최대 40턴(orchestrate max_turns), 단계 모델 고정(make_clients).",
    )
    card(s, X0, 1.85, 5.9, 3.95, [], fill=ORANGE_TINT)
    text(
        s,
        X0 + 0.2,
        1.95,
        5.5,
        0.4,
        ["글로 부탁 (지시문)"],
        size=16,
        bold=True,
        color=ORANGE,
    )
    asks = [
        "판독 파이프라인을 운영하는 역할이다",
        "단계는 정해진 순서대로 돌린다",
        "길이 · 치수를 직접 계산하지 않는다",
        "숫자는 도구 결과에 있는 값만 옮긴다",
        "정답 파일은 읽지 않는다",
    ]
    text(
        s,
        X0 + 0.3,
        2.5,
        5.4,
        3.2,
        [{"text": f"“{a}”", "size": 14} for a in asks],
        after=8,
    )
    text(
        s,
        X0 + 0.3,
        5.2,
        5.4,
        0.5,
        ["모델이 대개 지키지만, 지킨다는 보장은 없습니다"],
        size=12,
        color=GRAY,
    )
    card(s, X0 + 6.23, 1.85, 5.9, 3.95, [], fill=TEAL_TINT)
    text(
        s,
        X0 + 6.43,
        1.95,
        5.5,
        0.4,
        ["구조로 강제 (코드)"],
        size=16,
        bold=True,
        color=TEAL,
    )
    forced = [
        ("도구 목록", "목록에 없는 일은 못 함"),
        ("인자 검사", "양식에 안 맞는 값은 실행 전에 거절"),
        ("폴더 제한", "출력 폴더 밖에는 못 씀"),
        ("답 양식", "정해진 JSON 밖의 글자는 못 씀"),
        ("턴 제한", "40번 안에 못 끝내면 멈춤"),
    ]
    for i, (k, v) in enumerate(forced):
        y = 2.5 + i * 0.62
        chip(s, X0 + 6.43, y, 1.6, 0.5, k, fill=TEAL, color=WHITE, size=12, bold=True)
        text(s, X0 + 8.18, y, 3.85, 0.5, [v], size=13, anchor=MSO_ANCHOR.MIDDLE)
    band(
        s,
        6.0,
        "하네스",
        "모델이 똑똑해지길 기다리지 않고, 틀릴 수 있는 자리를 코드가 줄여 둡니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.7,
        size=14,
    )


def concept_safety_slide(d):
    s = concept_slide(
        d,
        "부록 · 하네스 구조 5: 실패해도 멈추지 않고, 모두 남긴다",
        "모델의 실수와 도구의 실패를 '에러' 결과로 모델에게 돌려줍니다. 모델은 그걸 보고 다시 고릅니다",
        "orchestrate(): 깨진 답(invalid_reply)은 실행하지 않고 에러를 돌려준다. ReaderTools.call 은 예외를 던지지 않고 {'error': …} 를 돌려준다. "
        "Log 가 command.json(설정 · 도구 목록), trajectory.jsonl(턴마다 한 줄), messages.json(대화 전체, 실패해도 finally 에서), answer.json(최종 보고)을 "
        "runs/reader/agent/orchestrator/<시각>/ 에 쓴다. scripts/reader/show_trajectory.py 로 읽는다.",
    )
    # 반복 고리: 모델 → 진행 → 도구 → 진행 → 모델
    connect(s, 2.1, 3.25, 2.1, 4.35, color=GRAY, width=2)
    connect(s, 3.35, 4.8, 5.2, 4.8, color=GRAY, width=2)
    role_box(
        s, X0 + 0.25, 1.9, 2.5, 1.05, "모델", "도구를 고름", "backend", fill=ORANGE
    )
    role_box(
        s,
        X0 + 0.25,
        4.35,
        2.5,
        0.95,
        "진행",
        "골라진 도구 실행",
        "orchestrate()",
        fill=INK,
    )
    role_box(s, 5.2, 4.35, 2.0, 0.95, "도구", "판독 단계", "ReaderTools", fill=TEAL)
    fails = [
        ("답이 깨짐", "실행하지 않고 '양식이 아님' 을 돌려줌"),
        ("도구 실패", "멈추지 않고 '실패: 이유' 를 돌려줌"),
        ("앞 단계 없음", "'아직 못 함' 을 돌려줌"),
    ]
    text(s, 3.6, 1.85, 3.8, 0.4, ["실패하면"], size=15, bold=True, color=ORANGE)
    for i, (k, v) in enumerate(fails):
        y = 2.3 + i * 0.62
        chip(s, 3.6, y, 1.5, 0.5, k, fill=ORANGE_TINT, color=ORANGE, size=11, bold=True)
        text(s, 5.2, y, 2.4, 0.5, [v], size=11, anchor=MSO_ANCHOR.MIDDLE)
    card(s, 8.0, 1.85, 4.73, 3.95, [], fill=LIGHT)
    text(s, 8.2, 1.95, 4.4, 0.4, ["남기는 기록"], size=16, bold=True, color=TEAL)
    logs = [
        ("명령", "무엇을 시켰고 어떤 도구를 줬나"),
        ("턴마다", "모델의 생각, 고른 도구, 걸린 시간"),
        ("대화 전체", "실패로 끝나도 저장"),
        ("최종 보고", "모델이 사람에게 한 답"),
    ]
    for i, (k, v) in enumerate(logs):
        y = 2.5 + i * 0.78
        chip(s, 8.2, y, 1.55, 0.6, k, fill=TEAL, color=WHITE, size=12, bold=True)
        text(s, 9.9, y, 2.75, 0.6, [v], size=12, anchor=MSO_ANCHOR.MIDDLE)
    band(
        s,
        6.0,
        "하네스",
        "기록이 있어야 어느 단계에서 왜 틀렸는지 사람이 찾고 고칠 수 있습니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.7,
        size=14,
    )


# ---------------------------------------------------------------------- main
def main() -> None:
    s3, pre = load_score(RUN3), load_score(RUN3_PRE)
    d = Deck(OUT, TITLE, FOOTER)
    title_slide(d)
    agenda_slide(d)
    # 1. 용어
    define_section(d)
    job_def_slide(d)
    drawing_def_slide(d)
    shape_def_slide(d)
    unfold_def_slide(d)
    answer_def_slide(d)
    reader_def_slide(d)
    ai_message_slide(d)
    ai_prompt_slide(d)
    ai_skills_slide(d)
    ai_contract_slide(d)
    ai_client_slide(d)
    harness_def_slide(d)
    score_def_slide(d)
    # 2. 판독 과정 (예시 도면 한 장)
    harness_section(d)
    flow_slide(d)
    walkthrough_slides(d)
    # 3. 지난주
    lastweek_section(d)
    lastweek_scope_slide(d)
    lastweek_perf_slide(d)
    lastweek_success_slide(d)
    lastweek_fail_shape_slide(d)
    lastweek_fail_unfold_slide(d)
    lastweek_real_slide(d)
    lastweek_problems_slide(d)
    goal_change_slide(d)
    scope_slide(d)
    # 4. 하네스 장치
    devices_section(d)
    harness_eng_slide(d)
    json_contract_slide(d)
    decoding_slide(d)
    guard_retry_slide(d, pre, s3)
    rules_slide(d)
    stage_file_slide(d)
    guard_trace_slide(d)
    tool_idea_slide(d)
    tool_list_slide(d)
    tool_loop_slide(d)
    tool_modes_slide(d)
    tool_demo_slide(d)
    # 5. 전 → 후
    change_section(d)
    summary_slide(d, s3)
    history_slide(d)
    stages_split_slide(d)
    wrong_ruler_slide(d)
    data_figure_slide(
        d,
        "콘: 정답을 고쳤습니다",
        "평균지름은 두께 가운데에서, 부채꼴 각도는 θ = 360° · sin α",
        ["cone_wall.png", "cone_sector.png"],
        "현업자 정답대로 평균지름을 끝면에서 가로로 잽니다 (안지름 + t / cos α)",
        "docs/data/synthetic/cone_wall.png, cone_sector.png (scripts/synthetic_figures.py). docs/v3_upgrade.md 4.2 · 5.4절.",
    )
    data_figure_slide(
        d,
        "경판: 윤곽과 원판 지름",
        "꺾인 윤곽 → 2:1 반타원 + 짧은 직선부. 원판 지름은 두께 가운데 반타원 길이 + 직선부 × 2",
        ["press_profile.png", "head_blank.png"],
        "옛 계수 1.3415 → 현업자 정답 (회사 계산 문서 1.2 × Dm 과는 1.35% 차이, 검토 요청)",
        "docs/data/synthetic/press_profile.png, head_blank.png. docs/v3_upgrade.md 4.1 · 4.3 · 5.4 · 5.5절. 그림은 2026-10-28 판 생성기 기준.",
    )
    drafting_slide(d)
    practitioner_slide(d)
    grid_slide(d)
    score_compare_slide(d, pre, s3)
    class_score_slide(d, s3)
    class_pair_slides(d, s3)
    fixed_slide(d)
    remaining_slides(d, s3)
    # E. 실험
    experiment_section(d)
    truncation_slide(d)
    model_swap_slide(d)
    candidates_slide(d)
    # F. v4
    v4_section(d)
    v4_why_slide(d)
    v4_bom_slide(d)
    v4_expect_slide(d)
    v4_plan_slide(d)
    roadmap_slide(d)
    ask_slide(d)
    # G. 마무리
    wrapup_slide(d, s3)
    questions_slide(d)
    # 부록
    appendix_section(d)
    testset_slide(d)
    per_drawing_slides(d, s3)
    concept_parts_slide(d)
    concept_tool_slide(d)
    concept_adapter_slide(d)
    concept_rules_slide(d)
    concept_safety_slide(d)
    commands_slide(d)
    print(d.save(), d.count)


if __name__ == "__main__":
    main()
