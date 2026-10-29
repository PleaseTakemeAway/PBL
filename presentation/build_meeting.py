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
    chip,
    code,
    page,
    picture,
    real_sheet,
    road,
    shape,
    table,
    text,
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

PARTS = ["도입", "하네스", "전 → 후", "실험", "v4"]
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
        "도면을 넣으면 전개도가 나오는 판독기를, 합성 도면에서 끝까지 맞히도록 고쳤습니다",
        "네 부분. 지난 발표와 겹치는 배경 슬라이드는 건너뛸 수 있다.",
    )
    rows = [
        ("1", "범위", "도면 → 전개도까지. 3D 복원은 뺐습니다"),
        ("2", "하네스", "판독 10단계를 그림으로: AI 가 하는 곳과 코드가 하는 곳"),
        (
            "3",
            "전 → 후",
            "합성 데이터와 판독 코드가 어떻게 바뀌었고 결과가 어떻게 달라졌나",
        ),
        ("4", "다음", "추가 실험(답 잘림, 모델 바꿔 끼우기)과 실제 도면을 읽는 v4"),
    ]
    for i, (n, head, body) in enumerate(rows):
        y = 1.9 + i * 1.2
        chip(s, X0, y, 0.7, 0.9, n, fill=ORANGE, color=WHITE, size=24, bold=True)
        chip(
            s, X0 + 0.85, y, 2.0, 0.9, head, fill=TEAL, color=WHITE, size=20, bold=True
        )
        text(s, X0 + 3.1, y, 8.9, 0.9, [body], size=20, anchor=MSO_ANCHOR.MIDDLE)


def summary_slide(d, s3):
    s = slide(
        d,
        0,
        "한 장 요약",
        "정답(저울)부터 고친 뒤 다시 쟀습니다. 형상은 30/30, 전개는 아직 절반쯤입니다",
        "① 은 옛 정답, ③ 은 새 정답으로 잰 숫자라 같은 저울이 아니다. 같은 저울로 나눈 비교(2×2)는"
        " 다시 돌린 뒤 넣는다 (docs/pbl_meeting.md 3절). ③ 은 2026-10-28 04:23 실행.",
    )
    cols = [
        (
            "① 시작",
            "옛 합성 / 동료 v3",
            TEAL_TINT,
            [("형상", "27/30"), ("전개", "11/30")],
            "단계별 기록 없음",
        ),
        (
            "② 단계로",
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
        [
            "①·③ 은 정답이 달라 같은 저울이 아닙니다. 같은 저울 비교는 뒤에서 (전 → 후 파트)"
        ],
        size=14,
        color=GRAY,
    )


def goal_change_slide(d):
    s = slide(
        d,
        0,
        "지난 미팅 뒤 바뀐 것",
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
            {"text": "전", "bold": True, "color": GRAY, "size": 20},
            {"text": "합성 30장은 형상 27/30 으로 '됐다' 고 보고", "bullet": True},
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
            {"text": "후", "bold": True, "color": ORANGE, "size": 20},
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
        0,
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
def background_section(d):
    section(
        d,
        "배경",
        "다시 짚기",
        "지난 발표와 겹칩니다. 건너뛰어도 됩니다",
        "배경 4장. 지난 발표를 들은 청중이면 건너뛴다.",
    )


def job_slide(d):
    s = slide(
        d,
        0,
        "하려는 일",
        "설계 도면을 읽어 판재를 펼친 모양(전개도)을 만들고, 그것으로 커팅플랜을 짭니다",
        "전체 지도. 이번 범위는 가운데 화살표까지다.",
    )
    boxes = [
        ("설계 도면", "DWG · DXF\n정면 · 평면 · 측면", TEAL_TINT),
        ("전개도", "판을 펼친 모양과 크기\n(이번 범위)", ORANGE_TINT),
        ("커팅플랜", "철판 위 배치\n(v2 뒷단)", LIGHT),
    ]
    for i, (head, body, fill) in enumerate(boxes):
        x = X0 + i * 4.2
        card(
            s,
            x,
            2.2,
            3.6,
            2.6,
            [
                {"text": head, "bold": True, "size": 24},
                {"text": body, "size": 17, "color": GRAY},
            ],
            fill=fill,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if i < 2:
            arrow(s, x + 3.7, 3.3, w=0.4, h=0.4)
    band(
        s,
        5.4,
        "판독기 (reader)",
        "도면 → 전개도 부분입니다. 오늘 이야기는 모두 이 부분입니다",
        fill=TEAL_TINT,
        color=TEAL,
    )


def synthetic_slide(d):
    s = slide(
        d,
        0,
        "합성 도면 30장",
        "회사 도면에 흔한 쉬운 형상 5종 × 6장. 도면 한 장에 부품 하나, 3면도와 표제란",
        "docs/interim_report.md 2절. 형상 종류는 회사 도면에서 골랐고 도면 파일은 프로그램이 그렸다. 그림은 ③ 실행(RUN3)의 analysis/sheet.png.",
    )
    w = 2.3
    for i, cls in enumerate(CLASSES):
        x = X0 + i * (w + 0.16)
        fit(s, workdir(RUN3, SHOWCASE[cls]) / "analysis" / "sheet.png", x, 2.0, w, 1.7)
        caption(s, x, 3.85, w, CLASS_KR[cls])
        text(
            s,
            x,
            4.3,
            w,
            0.4,
            [SHOWCASE[cls]],
            size=11,
            color=GRAY,
            align=PP_ALIGN.CENTER,
        )
    band(
        s,
        5.2,
        "정답",
        "도면마다 label.json: 형상, 치수, 뷰 이름, 표제란, 전개 값. 그래서 단계마다 채점할 수 있습니다",
        fill=TEAL_TINT,
        color=TEAL,
    )


def models_slide(d):
    s = slide(
        d,
        0,
        "로컬 AI 두 개, 사내 GPU 서버",
        "도면은 외부 AI 서비스로 나가지 않습니다",
        "서버 mlic: RTX A5000 24 GB × 4 (AGENTS.md 6절). 배치는 experiments/models/*.sh 프로필.",
    )
    gpus = [
        ("GPU 0", "글자 읽기 (OCR)\nDeepSeek-OCR-2\n3.4B", ORANGE_TINT),
        ("GPU 1 · 2 · 3", "판단\nQwen3.6-27B\n27.8B, 세 장에 나눠 올림", TEAL_TINT),
    ]
    card(
        s,
        X0,
        2.0,
        2.8,
        3.4,
        [{"text": "RTX A5000\n24 GB × 4", "bold": True, "size": 22}],
        fill=LIGHT,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    for i, (head, body, fill) in enumerate(gpus):
        y = 2.0 + i * 1.8
        chip(
            s,
            X0 + 3.3,
            y,
            2.2,
            1.6,
            head,
            fill=TEAL if i else ORANGE,
            color=WHITE,
            size=18,
            bold=True,
        )
        card(
            s,
            X0 + 5.7,
            y,
            6.4,
            1.6,
            [body],
            fill=fill,
            size=18,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    band(
        s,
        5.75,
        "역할",
        "OCR 은 표제란 그림을 글자로 받아쓰고, 판단 모델은 그림과 글자를 보고 고릅니다. 계산은 둘 다 하지 않습니다",
        fill=TEAL_TINT,
        color=TEAL,
    )


# ---------------------------------------------------------------------- C. 하네스
STAGES = [
    ("01", "읽기", "DXF 의 선 · 원 · 글자", False),
    ("02", "표제란 정규식", "글자 규칙으로 먼저 읽기", False),
    ("03", "표제란 OCR", "그림을 글자로", True),
    ("04", "표제란 정리", "빈칸만 채우기", True),
    ("05", "뷰 찾기", "선 덩어리 묶기", False),
    ("06", "뷰 이름 · 형상", "정면? 콘?", True),
    ("07", "합치기", "결과 한 파일로", False),
    ("08", "구조화", "정면·평면·측면 계약", False),
    ("09", "치수", "전개에 쓸 값", True),
    ("10", "전개", "공식 계산 · 전개도", False),
]


def harness_section(d):
    section(
        d,
        "2",
        "하네스는 이렇게 돕니다",
        "판독 10단계를 그림으로",
        "코드 대신 그림으로 판독기의 동작을 보인다. 예시 도면은 cone_0023 (③ 에서 모두 맞힌 도면).",
    )


def flow_slide(d):
    s = slide(
        d,
        1,
        "전체 흐름: 10단계",
        "AI 는 네 곳(주황)에서 읽고 고릅니다. 나머지와 모든 계산은 코드(청록)가 합니다",
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
        1,
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
        1,
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


def read_slide(d):
    counts = stage_json(RUN3, EXAMPLE, "01_read").get("entity_counts", {})
    total = sum(counts.values())
    s = slide(
        d,
        1,
        "01 읽기 (코드)",
        "DXF 는 글자 파일입니다. 선 · 원 · 글자를 위치와 함께 목록으로 만듭니다",
        f"{EXAMPLE} 의 01_read.json entity_counts: {counts}. 모델을 쓰지 않는다.",
    )
    code(
        s,
        X0,
        1.9,
        5.2,
        4.2,
        [
            "  0",
            "LINE",
            "  8",
            "OUTLINE",
            " 10",
            "100.0",
            " 20",
            "110.0",
            " 11",
            "250.0",
            " 21",
            "110.0",
            "  0",
            "CIRCLE",
            "…",
        ],
        size=13,
    )
    text(s, X0, 6.2, 5.2, 0.4, ["DXF 원문 (선 하나)"], size=12, color=GRAY)
    arrow(s, X0 + 5.4, 3.8, w=0.5, h=0.4)
    names = {
        "line": "선",
        "circle": "원",
        "arc": "호",
        "dimension": "치수",
        "dimension_geom": "치수선 조각",
        "text": "글자",
    }
    rows = (
        [["종류", "개수"]]
        + [[names.get(k, k), str(v)] for k, v in counts.items()]
        + [["합계", str(total)]]
    )
    table(s, X0 + 6.2, 1.9, 5.9, 0.45 * len(rows), rows, [3.4, 2.5], head_style)
    text(
        s,
        X0 + 6.2,
        2.0 + 0.45 * len(rows) + 0.2,
        5.9,
        0.8,
        [f"{EXAMPLE} (콘). 실제 회사 도면은 2,000~5,900개"],
        size=14,
        color=GRAY,
    )


def title_block_slide(d):
    regex = stage_json(RUN3, EXAMPLE, "02_title_regex")
    fields = stage_json(RUN3, EXAMPLE, "04_title_fields")
    tb = regex.get("title_block", {})
    model_no = (fields.get("fields") or {}).get("drawing_no")
    final_no = (fields.get("title_block") or {}).get("drawing_no")
    s = slide(
        d,
        1,
        "02 → 03 → 04 표제란",
        "정규식이 먼저 읽고, AI 는 정규식이 못 읽은 칸만 채웁니다",
        f"{EXAMPLE}: 02 정규식 도면 번호 {tb.get('drawing_no')}, 못 읽은 칸 {regex.get('missing')}. "
        f"03 OCR 그림은 표제란이 오른쪽에서 잘려 도면 번호가 SYN-000 까지만 보인다. 04 모델 답의 도면 번호 {model_no}, "
        f"최종 {final_no} (정규식 값을 지킴). dxf_adapter.apply_title_fields.",
    )
    steps = [
        (
            "02 정규식 (코드)",
            f"도면 번호 {tb.get('drawing_no')}\n재질 {tb.get('material')}\n축척 {tb.get('scale_text')}\n못 읽음: 부품명, 투상법",
            TEAL_TINT,
        ),
        (
            "03 OCR (AI)",
            "표제란 그림 → 글자\n(그림이 잘려\n'SYN-000' 까지만)",
            ORANGE_TINT,
        ),
        (
            "04 정리 (AI)",
            f"부품명 CONE ← 채움\n도면 번호 {model_no} ← 버림\n(정규식 값이 이미 있음)",
            ORANGE_TINT,
        ),
    ]
    for i, (head, body, fill) in enumerate(steps):
        x = X0 + i * 4.15
        card(
            s,
            x,
            1.9,
            3.7,
            2.2,
            [{"text": head, "bold": True, "size": 17}, {"text": body, "size": 15}],
            fill=fill,
            after=6,
        )
        if i < 2:
            arrow(s, x + 3.75, 2.85, w=0.35, h=0.3)
    fit(s, workdir(RUN3, EXAMPLE) / "figures" / "03_title_ocr.png", X0, 4.3, 7.0, 2.4)
    card(
        s,
        X0 + 7.2,
        4.45,
        4.93,
        2.1,
        [
            [
                {"text": "규칙  ", "bold": True, "color": TEAL},
                {"text": "코드가 확실히 읽은 값은 AI 가 덮어쓰지 못합니다"},
            ]
        ],
        fill=TEAL_TINT,
        size=17,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0.3,
    )


def views_slide(d):
    s = slide(
        d,
        1,
        "05 뷰 찾기 (코드)",
        "서로 떨어진 선 덩어리를 묶어 뷰 후보로 삼습니다. 표제란과 도면 틀은 뺍니다",
        f"{EXAMPLE} 의 figures/05_views.png (scripts/reader/show_stages.py). 주황 = 뷰 후보, 회색 = 제외 영역, 파란 점선 = 도면 틀.",
    )
    fit(s, workdir(RUN3, EXAMPLE) / "figures" / "05_views.png", X0, 1.75, 7.6, 5.0)
    bullets(
        s,
        X0 + 7.9,
        2.0,
        4.2,
        4.5,
        [
            "선이 가까우면 한 덩어리",
            "표제란 · 표 · 틀은 제외",
            "덩어리 3개 → 뷰 후보 3개",
            "정투상 도면인지, 네스팅 도면인지도 여기서 정합니다",
            "이름(정면 · 평면)은 아직 없음",
        ],
        size=17,
    )


def labels_slide(d):
    s = slide(
        d,
        1,
        "06 뷰 이름 · 형상 (AI)",
        "번호 붙은 그림, 참고 문서, 답 양식을 주고 고르게 합니다",
        f"{EXAMPLE} 의 figures/06_view_labels.png. 참고 문서는 skills/01_core_knowledge 의 unfold_rules, unfold_extract (reader/knowledge.py STAGE_TOPICS). 위치로 붙인 라벨과 AI 라벨이 다르면 review 에 남긴다.",
    )
    ins = [
        ("번호 붙은 그림", "sheet_labeled.png"),
        ("참고 문서 2개", "전개 규칙 · 판독 요령"),
        ("답 양식", "형상 6종 중 하나 + 점수"),
    ]
    for i, (head, body) in enumerate(ins):
        card(
            s,
            X0,
            1.85 + i * 1.0,
            3.0,
            0.85,
            [
                {"text": head, "bold": True, "size": 15},
                {"text": body, "size": 12, "color": GRAY},
            ],
            fill=LIGHT,
            after=0,
            margin=0.12,
        )
    arrow(s, X0 + 3.1, 3.05, w=0.35, h=0.3)
    chip(
        s,
        X0 + 3.55,
        2.6,
        1.4,
        1.2,
        "판단\nAI",
        fill=ORANGE,
        color=WHITE,
        size=18,
        bold=True,
    )
    arrow(s, X0 + 5.05, 3.05, w=0.35, h=0.3)
    fit(
        s,
        workdir(RUN3, EXAMPLE) / "figures" / "06_view_labels.png",
        X0 + 5.5,
        1.75,
        6.6,
        3.9,
    )
    band(
        s,
        5.85,
        "검사",
        "위치로 붙인 이름(정면은 아래 왼쪽 …)과 AI 의 답이 다르면 기록에 남겨 사람이 봅니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.8,
        size=16,
    )


def merge_slide(d):
    s = slide(
        d,
        1,
        "07 합치기 · 08 구조화 (코드)",
        "앞 단계 결과를 한 파일로 모으고, 정면 · 평면 · 측면 약속(계약)으로 바꿉니다",
        "07 은 analysis/sheet_analysis.json 과 sheet.png, 08 은 DrawingDocument. 08 은 3D 쪽 모델 클래스를 같이 써서 3D 코드를 지우지 않은 이유다 (v3_upgrade.md 1.1).",
    )
    card(
        s,
        X0,
        1.9,
        5.8,
        3.8,
        [
            {"text": "07 합치기", "bold": True, "size": 20},
            {"text": "01~06 의 결과 → sheet_analysis.json", "bullet": True},
            {"text": "최종 이름을 그린 sheet.png", "bullet": True},
            {"text": "사람이 한눈에 보는 요약", "bullet": True},
        ],
        fill=TEAL_TINT,
        size=17,
        after=10,
    )
    card(
        s,
        X0 + 6.33,
        1.9,
        5.8,
        3.8,
        [
            {"text": "08 구조화", "bold": True, "size": 20},
            {"text": "뷰마다 선과 치수를 붙임", "bullet": True},
            {
                "text": "왼쪽면 → 오른쪽면처럼 뒤집어 정면 · 평면 · 우측면으로",
                "bullet": True,
            },
            {"text": "축척 검사", "bullet": True},
        ],
        fill=TEAL_TINT,
        size=17,
        after=10,
    )
    band(
        s,
        5.95,
        "여기까지",
        "AI 는 03 · 04 · 06 에서만 썼습니다",
        fill=LIGHT,
        color=TEAL,
        h=0.75,
        size=16,
    )


def params_slide(d):
    s = slide(
        d,
        1,
        "09 치수 (AI + 코드)",
        "AI 가 형상별 치수를 읽고, 비운 칸은 코드가 도면 전체 치수로 채웁니다. 누가 채웠는지 남깁니다",
        f"{EXAMPLE} 의 stages/09_unfold_params.json 의 record.params 와 record.sources (vlm_reason = AI, overall_dimensions = 코드). 참고 문서 3개 (STAGE_TOPICS 09).",
    )
    params_table(s, RUN3, EXAMPLE, X0, 1.9, 6.2)
    text(s, X0, 4.4, 6.2, 0.4, [f"{EXAMPLE} (콘)"], size=13, color=GRAY)
    rows = [
        ("AI", "도면에서 두께 · 지름 · 높이를 골라 읽음", ORANGE),
        ("코드", "AI 가 비운 값은 외형 치수로:\n안지름 = 바깥지름 − 2t/cos α", TEAL),
        ("기록", "값마다 출처 → 틀리면 누가 틀렸는지 압니다", GRAY),
    ]
    for i, (k, v, c) in enumerate(rows):
        y = 1.9 + i * 1.15
        chip(s, X0 + 6.6, y, 1.2, 0.9, k, fill=c, color=WHITE, size=16, bold=True)
        text(s, X0 + 8.0, y, 4.1, 0.9, [v], size=16, anchor=MSO_ANCHOR.MIDDLE)


def develop_slide(d):
    s = slide(
        d,
        1,
        "10 전개 (코드)",
        "전개 공식은 코드가 계산합니다. AI 는 계산하지 않습니다",
        f"{EXAMPLE} 의 figures/10_develop.png 왼쪽 절반. 검정 = 계산 결과, 초록 점선 = 정답 (여기서는 겹친다). 콘 공식은 현업자 정답 기준 (v3_upgrade.md 5.4).",
    )
    fit(s, develop_plot(RUN3, EXAMPLE), X0, 1.8, 6.4, 4.1)
    rows = [
        ("09 에서 받은 것", "두께, 큰 · 작은 안지름, 높이"),
        ("계산", "평균지름 → 경사 길이 → 부채꼴 반경 · 각도"),
        ("내는 것", "flat_pattern.dxf · png · json"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 2.0 + i * 1.2
        chip(s, X0 + 6.8, y, 2.2, 0.9, k, fill=TEAL, color=WHITE, size=15, bold=True)
        text(s, X0 + 9.2, y, 2.9, 0.9, [v], size=15, anchor=MSO_ANCHOR.MIDDLE)
    band(
        s,
        6.1,
        "왜",
        "지름 10 mm 오차는 둘레 31 mm 오차이고 그 판은 버립니다. 계산은 틀리지 않는 코드에게",
        fill=TEAL_TINT,
        color=TEAL,
        h=0.7,
        size=16,
    )


def guard_schema_slide(d):
    s = slide(
        d,
        1,
        "하네스 장치 1: 답 양식",
        "서버가 답 양식(JSON)에 맞는 글자만 쓰게 하고, 받은 답을 코드가 한 번 더 검사합니다",
        "structured outputs (vLLM, xgrammar). 검사는 reader/vlm_output.py. 칸 하나의 오류로도 응답 전체를 거부한다.",
    )
    steps = [
        ("질문 + 양식", "형상: 6종 중 하나\n점수: 숫자", LIGHT),
        ("서버", "양식 밖 글자는\n못 씀", ORANGE_TINT),
        ("검사 (코드)", "값의 범위 · 종류", TEAL_TINT),
    ]
    for i, (head, body, fill) in enumerate(steps):
        x = X0 + i * 3.35
        card(
            s,
            x,
            2.0,
            2.9,
            2.0,
            [{"text": head, "bold": True, "size": 18}, {"text": body, "size": 15}],
            fill=fill,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        arrow(s, x + 2.97, 2.85, w=0.33, h=0.3)
    chip(
        s,
        X0 + 10.05,
        2.0,
        2.08,
        0.9,
        "통과 → 다음 단계",
        fill=TEAL,
        color=WHITE,
        size=14,
        bold=True,
    )
    chip(
        s,
        X0 + 10.05,
        3.1,
        2.08,
        0.9,
        "거부 → 실패 기록",
        fill=GRAY,
        color=WHITE,
        size=14,
        bold=True,
    )
    band(
        s,
        4.6,
        "효과",
        "AI 가 산문을 쓰거나 없는 형상을 지어내지 못합니다. 실패해도 어디서 왜인지 남습니다",
        fill=TEAL_TINT,
        color=TEAL,
    )
    band(
        s,
        5.65,
        "한계",
        "양식은 지키는데 답이 길어 중간에 잘리면 JSON 이 깨집니다 → 장치 2",
        h=0.85,
    )


def guard_retry_slide(d, pre, s3):
    s = slide(
        d,
        1,
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
        1,
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


def orchestrator_slide(d):
    s = slide(
        d,
        1,
        "같은 단계를 AI 가 골라 부르면",
        "단계를 도구로 내놓으면, 로컬 AI 가 자연어 명령을 받아 필요한 단계를 골라 부릅니다 (시제품)",
        "지난 발표와 겹친다. docs/reader/orchestrator.md. 도구 17개 = 판독 13단계 + 4 (목록, 상태, 보기, 묶어 돌리기). 2026-10-23 cone_0019 시연: AI 판단 3번, 133초 (runs/reader/agent/orchestrator/20261023-021136). 3D 를 끈 뒤로 3D 단계 도구는 빠졌다.",
    )
    chip(
        s,
        X0,
        2.3,
        2.6,
        1.2,
        '"cone_0019 를\n전개도까지"',
        fill=LIGHT,
        color=INK,
        size=15,
    )
    arrow(s, X0 + 2.7, 2.75, w=0.4, h=0.3)
    chip(
        s,
        X0 + 3.2,
        2.1,
        2.2,
        1.6,
        "로컬 AI\n(Qwen)",
        fill=ORANGE,
        color=WHITE,
        size=18,
        bold=True,
    )
    tools = [
        "list_drawings",
        "stage_status",
        "run_read",
        "run_view_labels",
        "run_unfold_params",
        "show_stage",
        "…",
    ]
    for i, t in enumerate(tools):
        chip(
            s,
            X0 + 6.0 + (i % 2) * 3.1,
            1.95 + (i // 2) * 0.55,
            2.95,
            0.45,
            t,
            fill=TEAL_TINT,
            color=TEAL,
            size=12,
        )
    arrow(s, X0 + 5.5, 2.75, w=0.4, h=0.3)
    band(
        s,
        4.4,
        "지금",
        "기본 실행은 순서가 정해진 10단계 (기준선). AI 가 고르는 방식은 같은 단계 위에서 비교할 다음 단계입니다",
        fill=TEAL_TINT,
        color=TEAL,
        h=1.0,
    )
    band(
        s,
        5.6,
        "시연",
        "cone_0019, AI 판단 3번, 133초 (2026-10-23)",
        fill=LIGHT,
        color=GRAY,
        h=0.75,
        size=16,
    )


# ---------------------------------------------------------------------- D. 전 → 후
def change_section(d):
    section(
        d,
        "3",
        "전 → 후",
        "합성 데이터와 판독 코드가 어떻게 바뀌었나",
        "변천사 세 단계와 결과.",
    )


def history_slide(d):
    s = slide(
        d,
        2,
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
        2,
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
        "아래 '저울이 틀려 있었다' 를 찾았습니다. 단계별 채점이 정답의 오류를 드러냈습니다",
    )


def wrong_ruler_slide(d):
    s = slide(
        d,
        2,
        "저울이 틀려 있었다",
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
    s = slide(d, 2, title, message, notes)
    w = CW / len(files) - 0.15 * (len(files) - 1) / len(files)
    for i, f in enumerate(files):
        fit(s, FIG / f, X0 + i * (w + 0.15), 1.8, w, 3.9)
    band(s, 5.85, "", caption_text, fill=LIGHT, color=TEAL, h=0.8, size=16)


def drafting_slide(d):
    s = slide(
        d,
        2,
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
        2,
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
        2,
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
        2,
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
            "① 과 ③ 은 정답이 달라 같은 저울이 아닙니다. ③ 두 열은 같은 정답, 차이는 '잘리면 다시 묻기' 등"
        ],
        size=13,
        color=GRAY,
    )


def class_score_slide(d, s3):
    s = slide(
        d,
        2,
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
            2,
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
            2,
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
        2,
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
    s = slide(d, 2, title, message, notes)
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
        2,
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
        "4",
        "추가 실험",
        "답 잘림 처리 · 모델 바꿔 끼우기 (진행 중)",
        "두 실험은 다른 세션에서 진행 중이다. 결과가 나오면 이 파트를 채운다 (docs/pbl_meeting.md 4절).",
    )


def truncation_slide(d):
    s = slide(
        d,
        3,
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
        3,
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
        3,
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
        "5",
        "다음 단계: v4",
        "실제 도면을 부품표부터 읽기",
        "v3 고도화로 목표를 바꾸며 미뤘던 실제 도면 작업 (git show c71cca0:docs/v4.md).",
    )


def v4_why_slide(d):
    s = slide(
        d,
        4,
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
        4,
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
        4,
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
        4,
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
        4,
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
        4,
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
        4,
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
        "시험 도면 · 도면별 점수 · 실행 명령",
        "질문이 나오면 가는 슬라이드.",
    )


def testset_slide(d):
    s = slide(
        d,
        4,
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
            4,
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
        4,
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


# ---------------------------------------------------------------------- main
def main() -> None:
    s3, pre = load_score(RUN3), load_score(RUN3_PRE)
    d = Deck(OUT, TITLE, FOOTER)
    # A. 도입
    title_slide(d)
    agenda_slide(d)
    summary_slide(d, s3)
    goal_change_slide(d)
    scope_slide(d)
    # B. 배경
    background_section(d)
    job_slide(d)
    synthetic_slide(d)
    models_slide(d)
    # C. 하네스
    harness_section(d)
    flow_slide(d)
    rules_slide(d)
    stage_file_slide(d)
    read_slide(d)
    title_block_slide(d)
    views_slide(d)
    labels_slide(d)
    merge_slide(d)
    params_slide(d)
    develop_slide(d)
    guard_schema_slide(d)
    guard_retry_slide(d, pre, s3)
    guard_trace_slide(d)
    orchestrator_slide(d)
    # D. 전 → 후
    change_section(d)
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
    commands_slide(d)
    print(d.save(), d.count)


if __name__ == "__main__":
    main()
