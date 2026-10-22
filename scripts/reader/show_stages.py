"""판독 단계 결과(<작업 폴더>/stages/*.json)를 표로 출력하고 그림으로 그린다.

사용 (레포 루트에서):
  uv run python scripts/reader/show_stages.py <작업 폴더> [단계 ...] [--raw] [--limit N] [--no-figures]

  단계는 번호(6, 06), 이름(view_labels), 범위(6-9)로 준다. 없으면 있는 단계를 모두 보여 준다.
  표는 화면에 출력하고, 그림은 <작업 폴더>/figures/NN_<단계>.png 로 쓴다.
  figures/index.html 은 단계마다 그림과 표를 한 페이지에 묶는다. 고른 단계만 그림을 새로 그리고,
  index.html 에는 늘 모든 단계가 들어간다.
  --raw         모델 단계(03, 04, 06, 09, 12)의 원문 응답도 출력한다.
  --limit N     글자·치수·뷰 같은 목록을 몇 줄까지 출력할지 (기본 30, 0 이면 전부).
  --no-figures  그림과 index.html 을 만들지 않고 표만 출력한다.

DXF 옆에 label.json (합성 도면의 정답) 이 있으면 해당 단계에 정답을 나란히 보여 준다.
단계 파일만 읽고 cutplan_agent 를 import 하지 않는다. 필드의 뜻은 docs/reader/stages.md 에 있다.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import math
import subprocess
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from matplotlib.patches import Arc, Rectangle

# cutplan_agent/reader/stages/workspace.py 의 STAGES 와 같은 순서. 번호 = 위치 + 1
STAGE_NAMES = [
    "read",
    "title_regex",
    "title_ocr",
    "title_fields",
    "views",
    "view_labels",
    "sheet",
    "document",
    "unfold_params",
    "develop",
    "reconstruct",
    "confirm",
    "export",
]


def stage_name(step: int) -> str:
    """0 은 DWG·DXF 를 받는 convert (STAGES 밖의 선택 단계), 1–13 은 STAGES."""
    return "convert" if step == 0 else STAGE_NAMES[step - 1]


def parse_steps(args: list[str]) -> list[int]:
    """단계 번호(6), 이름(view_labels), 범위(6-9, views-sheet)를 번호 목록으로 바꾼다."""

    def one(a: str) -> int:
        if a.isdigit() and 0 <= int(a) <= len(STAGE_NAMES):
            return int(a)
        if a == "convert":
            return 0
        if a in STAGE_NAMES:
            return STAGE_NAMES.index(a) + 1
        raise SystemExit(
            f"단계를 모른다: {a}  (0–13 또는 convert, {', '.join(STAGE_NAMES)})"
        )

    steps: list[int] = []
    for a in args:
        lo, sep, hi = a.partition("-")
        first, last = (one(lo), one(hi)) if sep and lo and hi else (one(a), one(a))
        steps += [n for n in range(first, last + 1) if n not in steps]
    return sorted(steps)


TITLE_FIELDS = [
    "drawing_no",
    "part_name",
    "material",
    "thickness_mm",
    "scale",
    "scale_text",
    "units",
    "projection",
    "weight_kg",
]
EVIDENCE = {
    "plate_captions": "판 캡션 (네스팅 근거)",
    "nesting_words": "네스팅 단어",
    "clusters": "도형 묶음",
    "aligned_axes_at_best_front": "정면 후보와 축이 맞는 묶음",
}


def fmt(v, digits: int = 2) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(fmt(x, digits) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {fmt(x, digits)}" for k, x in v.items()) + "}"
    return str(v)


def short(text, n: int = 90) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def table(rows: list[list], header: list, indent: str = "  ") -> None:
    """머리글이 None 인 열은 출력하지 않는다."""
    if not rows:
        print(indent + "(없음)")
        return
    keep = [i for i, h in enumerate(header) if h is not None]
    cells = [[fmt(r[i]) for i in keep] for r in [header, *rows]]
    header = [header[i] for i in keep]
    widths = [max(len(r[i]) for r in cells) for i in range(len(header))]
    for i, r in enumerate(cells):
        print(indent + "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
        if i == 0:
            print(indent + "  ".join("-" * w for w in widths))


class Ctx:
    def __init__(self, work: Path, limit: int, raw: bool):
        self.work, self.limit, self.raw = work, limit, raw
        self.files = {
            int(f.name[:2]): f for f in sorted((work / "stages").glob("*.json"))
        }
        self.cache: dict[int, dict] = {}
        self.label = self._label()

    def stage(self, step: int) -> dict | None:
        if step not in self.cache and step in self.files:
            self.cache[step] = json.loads(self.files[step].read_text())
        return self.cache.get(step)

    def _label(self) -> dict | None:
        first = self.stage(1)
        if not first or not first.get("source"):
            return None
        src = Path(first["source"])
        for base in (src, Path.cwd() / src):
            f = base.parent / "label.json"
            if f.is_file():
                return json.loads(f.read_text())
        return None

    def rel(self, path) -> str:
        if not path:
            return "-"
        p = Path(path)
        try:
            return str(p.relative_to(self.work.resolve()))
        except ValueError:
            return str(p)

    def cut(self, items: list) -> tuple[list, int]:
        if self.limit and len(items) > self.limit:
            return items[: self.limit], len(items) - self.limit
        return items, 0


def more(n: int) -> None:
    if n:
        print(f"  … 외 {n}개 (--limit 0 이면 전부)")


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def label_view(ctx: Ctx, bbox) -> str:
    """정답 label.json 에서 bbox 가 가장 많이 겹치는 뷰 이름."""
    if not ctx.label or not bbox:
        return "-"
    best = max(
        ((iou(bbox, v["bbox_dxf"]), name) for name, v in ctx.label["views"].items()),
        default=(0.0, "-"),
    )
    return best[1] if best[0] > 0.5 else "(없음)"


def title_rows(tb: dict, extra: dict | None = None) -> list[list]:
    sources = tb.get("sources", {})
    return [
        [k, tb.get(k), sources.get(k, ""), *(extra or {}).get(k, [])]
        for k in TITLE_FIELDS
    ]


def truth_title(ctx: Ctx) -> dict[str, list]:
    lab = ctx.label
    if not lab:
        return {}
    sheet = lab.get("sheet", {})
    return {
        "drawing_no": [sheet.get("drawing_no")],
        "part_name": [lab.get("class")],
        "material": [sheet.get("material")],
        "thickness_mm": [lab.get("thickness")],
        "scale": [sheet.get("scale")],
        "scale_text": [sheet.get("scale_text")],
        "units": [lab.get("units")],
        "projection": [sheet.get("projection")],
        "weight_kg": [None],
    }


# ---- 단계별 출력 ----


def s00(d: dict, ctx: Ctx) -> None:
    print(
        f"  원본: {d.get('source')}  ({d.get('source_kind')}, sha256 {str(d.get('source_sha256'))[:12]}…)"
    )
    conv = d.get("converter")
    if conv is None:
        print("  변환: 없음 (DXF 를 그대로 쓴다)")
    else:
        print(
            f"  변환: {conv.get('version') or conv.get('program')}  종료 코드 {conv.get('exit_code')}"
        )
        for line in conv.get("stderr_tail") or []:
            print(f"    | {short(line, 150)}")
    print(
        f"  01 이 읽을 DXF: {d.get('dxf')}  (sha256 {str(d.get('dxf_sha256'))[:12]}…)"
    )
    print(f"  모델 공간 엔티티: {d.get('modelspace_entities')}개")


def s01(d: dict, ctx: Ctx) -> None:
    info = d.get("info", {})
    print(f"  원본: {d.get('source')}  (sha256 {str(d.get('source_sha256'))[:12]}…)")
    print(f"  단위: {info.get('units')}  읽은 라이브러리: {info.get('reader')}")
    ents = d.get("entities", [])
    print(f"\n  [레이어·종류별 개수] 전체 {len(ents)}개")
    counts = Counter((e.get("layer"), e.get("kind")) for e in ents)
    table(
        [[layer, kind, n] for (layer, kind), n in sorted(counts.items())],
        ["레이어", "종류", "개수"],
    )
    texts = [e for e in ents if e.get("kind") == "text"]
    print(f"\n  [글자] {len(texts)}개  위치는 글자 기준점")
    rows, n = ctx.cut(texts)
    table(
        [
            [e.get("center"), e.get("layer"), e.get("height"), short(e.get("text"), 60)]
            for e in rows
        ],
        ["위치", "레이어", "높이", "내용"],
    )
    more(n)
    dims = [e for e in ents if e.get("kind") == "dimension"]
    print(f"\n  [치수] {len(dims)}개  (dimension_geom 은 치수선·화살표라 뺐다)")
    rows, n = ctx.cut(dims)
    table(
        [
            [e.get("measurement"), e.get("text") or "", e.get("center"), e.get("layer")]
            for e in rows
        ],
        ["측정값", "글자", "위치", "레이어"],
    )
    more(n)
    arcs = [e for e in ents if e.get("kind") in ("circle", "arc")]
    print(f"\n  [원·호] {len(arcs)}개")
    rows, n = ctx.cut(arcs)
    table(
        [
            [
                e.get("kind"),
                e.get("center"),
                e.get("radius"),
                e.get("start_angle"),
                e.get("end_angle"),
                e.get("layer"),
            ]
            for e in rows
        ],
        ["종류", "중심", "반지름", "시작각", "끝각", "레이어"],
    )
    more(n)


def s02(d: dict, ctx: Ctx) -> None:
    print(
        f"  표제란 영역: {fmt(d.get('title_region'), 1)}  (후보 {len(d.get('title_regions') or [])}개)"
    )
    truth = truth_title(ctx)
    header = ["필드", "정규식 결과", "출처"] + (["정답"] if truth else [])
    print()
    table(title_rows(d.get("title_block", {}), truth), header)
    print(f"\n  못 읽은 필드: {', '.join(d.get('missing') or []) or '없음'}")


def s03(d: dict, ctx: Ctx) -> None:
    print(f"  모델: {d.get('model')}")
    print(f"  넣은 그림: {ctx.rel(d.get('image'))}")
    print("  받아쓴 글자:")
    for line in str(d.get("text") or "(없음)").splitlines():
        print("    | " + line)


def s04(d: dict, ctx: Ctx) -> None:
    print(f"  모델: {d.get('model')}")
    regex = (ctx.stage(2) or {}).get("title_block", {})
    fields = d.get("fields") or {}
    final = d.get("title_block", {})
    truth = truth_title(ctx)
    rows = [
        [
            k,
            regex.get(k),
            fields.get(k),
            final.get(k),
            final.get("sources", {}).get(k, ""),
            *truth.get(k, []),
        ]
        for k in TITLE_FIELDS
    ]
    print("  최종 = 02 정규식 값이 있으면 그것, 없으면 모델 답\n")
    table(
        rows,
        ["필드", "02 정규식", "04 모델 답", "최종", "최종 출처"]
        + (["정답"] if truth else []),
    )
    if fields.get("notes"):
        print(f"\n  모델 메모: {short(fields['notes'], 300)}")


def view_texts(ctx: Ctx, view: dict) -> str:
    ents = (ctx.stage(1) or {}).get("entities", [])
    texts = [ents[i].get("text") for i in view.get("texts", []) if i < len(ents)]
    return short(" / ".join(t for t in texts if t), 50)


def s05(d: dict, ctx: Ctx) -> None:
    print(
        f"  도면 종류: {d.get('sheet_type')}  (orthographic=정투상, nesting=판 배치도, unknown=판단 못 함)"
    )
    print("  근거:")
    for k, v in (d.get("sheet_type_evidence") or {}).items():
        print(f"    {EVIDENCE.get(k, k)}: {v}")
    seg = d.get("segmentation", {})
    print(
        f"  도면 틀: {len(d.get('frames') or [])}개, 제외 영역(표제란·표): {len(d.get('excluded_regions') or [])}개, 표 묶음: {len(seg.get('table_clusters') or [])}개"
    )
    print(
        f"  뷰 나누기에 쓴 도형: {seg.get('geometry_entities')}개, 뺀 도형: {fmt(seg.get('dropped'))}"
    )
    views = d.get("views", [])
    print(f"\n  [뷰 후보] {len(views)}개  bbox = (x0, y0, x1, y1)")
    rows, n = ctx.cut(views)
    out = []
    for v in rows:
        b = v.get("bbox") or [0, 0, 0, 0]
        c = v.get("counts", {})
        out.append(
            [
                v.get("id"),
                fmt(b, 1),
                f"{b[2] - b[0]:.0f}x{b[3] - b[1]:.0f}",
                f"{c.get('line', 0)}/{c.get('arc', 0)}/{c.get('circle', 0)}/{c.get('dimensions', 0)}",
                label_view(ctx, b),
                view_texts(ctx, v),
            ]
        )
    truth = "정답 뷰" if ctx.label else None
    table(out, ["id", "bbox", "크기", "선/호/원/치수", truth, "안의 글자"])
    more(n)


def s06(d: dict, ctx: Ctx) -> None:
    dec = d.get("decision") or {}
    lab = ctx.label or {}
    used = dec.get("used")
    print(f"  모델 판단 사용: {'예' if used else '아니오 (위치 규칙만)'}")
    print(
        f"  투상법: {d.get('projection_default')} → {d.get('projection')}"
        + (f"   정답: {lab.get('sheet', {}).get('projection')}" if lab else "")
    )
    if used:
        pc = dec.get("part_class")
        print(
            f"  형상(part_class): {pc}"
            + (
                f"   정답: {lab.get('class')}  {'맞음' if pc == lab.get('class') else '틀림'}"
                if lab
                else ""
            )
        )
        rec = dec.get("reconstructable")
        print(
            f"  3D 복원 가능: {rec}"
            + (
                f"   정답(wireframe_reconstructable): {lab.get('wireframe_reconstructable')}"
                if lab
                else ""
            )
        )
        probs = sorted(
            (dec.get("part_class_probabilities") or {}).items(), key=lambda kv: -kv[1]
        )
        scores = dec.get("part_class_scores") or {}
        if probs:
            print("  형상별 점수 (모델이 준 점수 → softmax 확률):")
            for k, p in probs:
                print(f"    {k:13s} {fmt(scores.get(k)):>6s}  {p:7.2%}")
        if dec.get("rejected"):
            print(f"  모델 답 중 받아들이지 않은 뷰: {dec['rejected']}")
        if dec.get("error"):
            print(f"  모델 답 오류: {dec['error']}")
    else:
        print("  형상(part_class): 정하지 않음 (모델만 정한다)")
    views = d.get("views", [])
    print(f"\n  [뷰 라벨] {len(views)}개")
    rows, n = ctx.cut(views)
    table(
        [
            [
                v.get("id"),
                v.get("label"),
                v.get("confidence"),
                v.get("label_source"),
                label_view(ctx, v.get("bbox")),
                short(v.get("reason"), 70),
            ]
            for v in rows
        ],
        [
            "id",
            "라벨",
            "확신도",
            "누가 정했나",
            "정답 뷰" if ctx.label else None,
            "이유",
        ],
    )
    more(n)
    if d.get("plates"):
        print(f"\n  [판 목록] {len(d['plates'])}개 (네스팅 도면)")
        rows, n = ctx.cut(d["plates"])
        for p in rows:
            print(f"    {short(fmt(p), 120)}")
        more(n)
    review(d.get("review"))
    if dec.get("notes"):
        print(f"\n  모델 메모: {short(dec['notes'], 400)}")
    tb = d.get("title_block")
    if tb:
        print("\n  [표제란] 06 에서 투상법을 채운 뒤")
        table([r for r in title_rows(tb) if r[1] is not None], ["필드", "값", "출처"])


def review(items) -> None:
    if not items:
        return
    print("\n  [사람 확인 필요]")
    for r in items:
        msg = (
            r.get("issue") or r.get("message") or r.get("kind")
            if isinstance(r, dict)
            else r
        )
        print(f"    - {short(msg, 150)}")


def s07(d: dict, ctx: Ctx) -> None:
    print(
        f"  도면 종류: {d.get('sheet_type')}  형상: {d.get('part_class')}  3D 복원 가능: {d.get('reconstructable')}"
    )
    for k, v in (d.get("outputs") or {}).items():
        print(f"  {k}: {ctx.rel(v)}")
    print(
        "  01–06 의 결과를 analysis/sheet_analysis.json 하나로 합친 단계다. sheet.png 를 열어 뷰 라벨을 본다."
    )


def s08(d: dict, ctx: Ctx) -> None:
    doc = d.get("document") or {}
    meta = doc.get("metadata", {})
    print(f"  3D 복원에 넘길 뷰: {', '.join(d.get('views') or [])}")
    print(
        f"  단위: {meta.get('units')}  좌표 축척: {meta.get('drawing_scale')}  표제란 축척: {meta.get('reported_drawing_scale')}  ({meta.get('geometry_scale_mode')})"
    )
    print(f"  판 두께: {meta.get('sheet_thickness')}")
    dims = meta.get("dimensions") or {}
    line = f"  전체 치수: x={fmt(dims.get('x'))}, y={fmt(dims.get('y'))}, z={fmt(dims.get('z'))}"
    if ctx.label:
        line += f"   정답 extents: {fmt(ctx.label.get('extents'))}"
    print(line)
    print()
    rows = []
    for v in doc.get("views", []):
        kinds = Counter(p.get("kind") for p in v.get("primitives", []))
        vals = [
            a.get("value")
            for a in v.get("annotations", [])
            if a.get("value") is not None
        ]
        rows.append(
            [v.get("name"), fmt(dict(kinds)), len(v.get("annotations", [])), fmt(vals)]
        )
    table(rows, ["뷰", "도형", "치수 수", "치수 값"])
    review(meta.get("review"))


def s09(d: dict, ctx: Ctx) -> None:
    rec = d.get("record") or {}
    print(
        f"  상태: {rec.get('status')}  형상: {rec.get('part_class')}  전개 종류: {rec.get('part_type')} (모델: {rec.get('model_part_type')})  확신도: {rec.get('confidence')}"
    )
    params, sources = rec.get("params") or {}, rec.get("sources") or {}
    print(
        "\n  [전개 파라미터]  출처 overall_dimensions = 모델이 비워서 전체 치수로 채운 값"
    )
    table(
        [[k, v, sources.get(k, "")] for k, v in params.items()], ["이름", "값", "출처"]
    )
    if ctx.label:
        print(
            f"\n  정답 params: {fmt(ctx.label.get('params'))}  두께: {ctx.label.get('thickness')}"
        )
        print(
            "  (이름 체계가 달라서 직접 맞춰 본다. 예: cone 의 정답 지름은 바깥지름, 위 *_inner_dia 는 안지름)"
        )
    if rec.get("holes"):
        print(f"  구멍: {fmt(rec['holes'])}")
    if rec.get("notes"):
        print(f"\n  모델 메모: {short(rec['notes'], 400)}")
    for note in rec.get("fallback_notes") or []:
        print(f"  코드 보충: {short(note, 200)}")
    if rec.get("skills"):
        print(f"  붙인 skill 문서: {', '.join(rec['skills'])}")


def s10(d: dict, ctx: Ctx) -> None:
    rec = d.get("record") or {}
    blank = rec.get("blank") or {}
    print(f"  상태: {rec.get('status')}  전개 종류: {rec.get('part_type')}")
    if blank.get("formula"):
        print(f"  공식: {blank['formula']}")
    print("\n  [계산 결과]")
    table([[k, v] for k, v in blank.items() if k != "formula"], ["이름", "값"])
    if ctx.label and ctx.label.get("flat_pattern"):
        print(f"\n  정답 flat_pattern: {fmt(ctx.label['flat_pattern'])}")
    for w in rec.get("warnings") or []:
        print(f"  경고: {short(w, 200)}")
    for k, v in (rec.get("artifacts") or {}).items():
        print(f"  {k}: {ctx.rel(v)}")


def s11(d: dict, ctx: Ctx) -> None:
    res = d.get("result") or {}
    cands = res.get("candidates") or []
    print(f"  허용 오차: {d.get('tolerance')}  최대 후보: {d.get('max_candidates')}")
    print(
        f"  후보: {len(cands)}개, 검사를 통과한 후보: {', '.join(d.get('valid') or []) or '없음'}"
    )
    if cands:
        print()
        rows = []
        for c, e in zip(cands, res.get("evaluations") or []):
            checks = e.get("checks") or {}
            rows.append(
                [
                    c.get("id"),
                    len(c.get("vertices") or []),
                    len(c.get("edges") or []),
                    e.get("valid"),
                    e.get("score"),
                    " ".join(f"{k}={v.get('status')}" for k, v in checks.items()),
                ]
            )
        table(rows, ["후보", "꼭짓점", "모서리", "통과", "점수", "검사"])
    rr = res.get("review_request") or {}
    if rr:
        print(
            f"\n  검토 상태: {rr.get('status')}  자동 승인: {rr.get('automatic_approval')}"
        )
        print("  [모호한 점]")
        for a in rr.get("ambiguities") or []:
            print(
                f"    - {a.get('kind')}: {short(a.get('message') or fmt(a.get('candidate_ids') or a.get('checks')), 130)}"
            )
        print("  [사람이 할 일]")
        for o in rr.get("resolution_options") or []:
            print(f"    - {o.get('ambiguity')}: {short(o.get('action'), 130)}")


def s12(d: dict, ctx: Ctx) -> None:
    conf = d.get("confirmation") or {}
    print(f"  모델 확인 사용: {conf.get('used')}  기록됨: {d.get('recorded')}")
    for k, v in conf.items():
        if k != "used":
            print(f"  {k}: {short(fmt(v), 200)}")
    rr = d.get("review_request") or {}
    if rr:
        print(
            f"  검토 상태: {rr.get('status')}  ({len(rr.get('ambiguities') or [])}건, 11 의 출력과 같은 형식)"
        )


def s13(d: dict, ctx: Ctx) -> None:
    rec = d.get("reconstruction") or {}
    print(f"  결과: {d.get('outcome')}")
    for k, v in rec.items():
        if k == "artifacts":
            continue
        print(f"  {k}: {short(fmt(v), 150)}")
    for k, v in (rec.get("artifacts") or {}).items():
        print(f"  파일 {k}: {ctx.rel(v)}")


SHOW = {
    0: s00,
    1: s01,
    2: s02,
    3: s03,
    4: s04,
    5: s05,
    6: s06,
    7: s07,
    8: s08,
    9: s09,
    10: s10,
    11: s11,
    12: s12,
    13: s13,
}


def show_trace(d: dict, ctx: Ctx) -> None:
    calls = [(role, t) for role, ts in (d.get("trace") or {}).items() for t in ts]
    if not calls:
        return
    print("\n  [모델 호출]")
    for role, t in calls:
        status = "성공" if t.get("ok") else f"실패: {short(t.get('error'), 150)}"
        skills = ", ".join(
            s.get("topic", "") for s in t.get("skills") or [] if isinstance(s, dict)
        )
        print(
            f"    {role} / {t.get('task')} / {t.get('model')} / {fmt(t.get('seconds'), 1)}초 / {status}"
            + (f" / skill: {skills}" if skills else "")
        )
        if ctx.raw:
            raw = t.get("raw") or ""
            try:
                raw = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                pass
            for line in str(raw).splitlines():
                print("      | " + line)
    if not ctx.raw:
        print("    (원문 응답은 --raw)")


def show(step: int, ctx: Ctx) -> None:
    d = ctx.stage(step)
    status = d.get("status")
    print(f"\n=== {step:02d} {d.get('stage')}: {status} ===")
    if d.get("inputs"):
        print(f"  읽은 파일: {', '.join(d['inputs'])}")
    if status == "skipped":
        print(f"  건너뛴 이유: {d.get('reason')}")
    elif status == "failed":
        print(f"  오류: {d.get('error')}")
    else:
        SHOW[step](d, ctx)
    show_trace(d, ctx)


# ---- 그림 ----


def use_hangul_font() -> None:
    """한글 폰트를 고른다. matplotlib 이 모르는 ~/.local/share/fonts 의 폰트는 fc-list 로 찾아 등록한다."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("NanumGothic", "Noto Sans CJK KR", "Malgun Gothic"):
        if name in names:
            plt.rcParams["font.family"] = [name, "DejaVu Sans"]
            return
    try:
        out = subprocess.run(
            ["fc-list", ":lang=ko", "file"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return
    files = sorted(
        path
        for path in (line.split(":")[0].strip() for line in out.splitlines())
        if path.endswith((".ttf", ".otf", ".ttc"))
    )
    if files:
        # 굵기별 파일을 모두 등록해야 보통 굵기가 Bold 로 대체되지 않는다
        first = font_manager.FontProperties(fname=files[0]).get_name()
        for f in files:
            if font_manager.FontProperties(fname=f).get_name() == first:
                font_manager.fontManager.addfont(f)
        name = first
        plt.rcParams["font.family"] = [name, "DejaVu Sans"]


use_hangul_font()
plt.rcParams["axes.unicode_minus"] = False

VIEW_COLORS = {
    "front": "#d62728",
    "top": "#1f77b4",
    "right": "#2ca02c",
    "left": "#9467bd",
    "bottom": "#8c564b",
    "back": "#e377c2",
}
GRAY = "#b0b0b0"


# ---- 도면 그리기 ----


def ent_bbox(e: dict):
    if e.get("points"):
        xs = [p[0] for p in e["points"]]
        ys = [p[1] for p in e["points"]]
        return min(xs), min(ys), max(xs), max(ys)
    if e.get("center") and e.get("radius"):
        (x, y), r = e["center"], e["radius"]
        return x - r, y - r, x + r, y + r
    if e.get("center"):
        x, y = e["center"]
        return x, y, x, y
    return None


def sheet_bbox(ctx: Ctx, ents: list[dict]):
    seg = (ctx.stage(5) or {}).get("segmentation") or {}
    if seg.get("sheet_bbox"):
        return seg["sheet_bbox"]
    boxes = [b for b in map(ent_bbox, ents) if b]
    if not boxes:
        return 0, 0, 1, 1
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def pad(b, frac: float = 0.02):
    m = frac * max(b[2] - b[0], b[3] - b[1], 1e-6)
    return b[0] - m, b[1] - m, b[2] + m, b[3] + m


def draw_entities(ax, ents, color_of, lw: float = 0.7, texts: bool = True) -> None:
    """선·원·호·글자를 그린다. color_of(e) 가 None 이면 그 요소는 그리지 않는다."""
    segs, cols, styles = [], [], []
    for e in ents:
        c = color_of(e)
        if c is None:
            continue
        kind = e.get("kind")
        dashed = (
            "HIDDEN" in str(e.get("linetype", "")).upper()
            or "DASH" in str(e.get("linetype", "")).upper()
        )
        if kind in ("line", "dimension_geom") and len(e.get("points") or []) >= 2:
            pts = e["points"]
            for a, b in zip(pts, pts[1:]):
                segs.append([a, b])
                cols.append(c)
                styles.append("--" if dashed else "-")
        elif kind == "circle" and e.get("center"):
            r = e["radius"]
            ax.add_patch(
                Arc(
                    e["center"],
                    2 * r,
                    2 * r,
                    lw=lw,
                    color=c,
                    ls="--" if dashed else "-",
                )
            )
        elif kind == "arc" and e.get("center"):
            a1, a2 = e.get("start_angle") or 0, e.get("end_angle") or 360
            if a2 < a1:
                a2 += 360
            r = e["radius"]
            ax.add_patch(
                Arc(e["center"], 2 * r, 2 * r, theta1=a1, theta2=a2, lw=lw, color=c)
            )
        elif texts and kind == "text" and e.get("center") and e.get("text"):
            ax.text(
                *e["center"],
                e["text"],
                fontsize=5,
                color=c,
                rotation=(e.get("attributes") or {}).get("rotation", 0),
                va="bottom",
                ha="left",
                clip_on=True,
            )
    if segs:
        ax.add_collection(
            LineCollection(segs, colors=cols, linewidths=lw, linestyles=styles)
        )


def sheet_axes(ax, bbox) -> None:
    b = pad(bbox)
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def box(
    ax, b, color, label: str = "", lw: float = 2.0, ls: str = "-", fill=None
) -> None:
    ax.add_patch(
        Rectangle(
            (b[0], b[1]),
            b[2] - b[0],
            b[3] - b[1],
            fill=fill is not None,
            fc=fill or "none",
            ec=color,
            lw=lw,
            ls=ls,
        )
    )
    if label:
        ax.text(
            b[0],
            b[3],
            f" {label}",
            color=color,
            fontsize=9,
            fontweight="bold",
            va="bottom",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.9),
        )


def figure_for_sheet(bbox, width: float = 13.0, extra: float = 0.0):
    w, h = max(bbox[2] - bbox[0], 1e-6), max(bbox[3] - bbox[1], 1e-6)
    height = max(4.0, min(width * h / w, 14.0))
    return plt.figure(figsize=(width + extra, height + 0.8))


def faded(ctx: Ctx, ax, ents) -> None:
    draw_entities(ax, ents, lambda e: GRAY, lw=0.5, texts=len(ents) < 600)


def text_panel(ax, lines: list[str], size: float = 9) -> None:
    ax.axis("off")
    ax.text(
        0,
        1,
        "\n".join(lines),
        va="top",
        ha="left",
        fontsize=size,
        transform=ax.transAxes,
    )


def table_panel(
    ax, rows: list[list], header: list[str], colors: list[list] | None = None
) -> None:
    ax.axis("off")
    if not rows:
        ax.text(0.5, 0.5, "(없음)", ha="center", va="center")
        return
    cells = [["-" if c is None else str(c) for c in r] for r in rows]
    t = ax.table(
        cellText=cells,
        colLabels=header,
        loc="upper center",
        cellLoc="left",
        cellColours=colors,
    )
    t.auto_set_font_size(False)
    t.set_fontsize(9)
    t.scale(1, 1.4)
    for (r, _), cell in t.get_celld().items():
        if r == 0:
            cell.set_facecolor("#e8e8e8")
            cell.set_text_props(fontweight="bold")


def number(v) -> float:
    """숫자나 "1/2" 같은 분수 글자를 숫자로 바꾼다."""
    if isinstance(v, str) and v.count("/") == 1:
        n, m = v.split("/")
        return float(n) / float(m)
    return float(v)


def same(a, b) -> bool | None:
    """정답 비교. 정답이 없으면 None. 글자는 정답이 값 안에 들어 있어도 같다고 본다
    (정답 재질 "SPCC" 와 표제란 "SPCC, 4t")."""
    if b is None:
        return None
    if a is None:
        return False
    try:
        return math.isclose(number(a), number(b), rel_tol=1e-3)
    except (TypeError, ValueError):
        a, b = str(a).strip().lower(), str(b).strip().lower()
        return a == b or (len(b) >= 3 and b in a)


def match_color(ok: bool | None) -> str:
    return {True: "#d9f2d9", False: "#f9d6d5", None: "white"}[ok]


# ---- 단계별 그림 ----


def f01(d, ctx):
    ents = d.get("entities", [])
    bbox = sheet_bbox(ctx, ents)
    layers = [name for name, _ in Counter(e.get("layer") for e in ents).most_common()]
    cmap = plt.get_cmap("tab10")
    color = {name: cmap(i % 10) for i, name in enumerate(layers)}
    fig = figure_for_sheet(bbox)
    ax = fig.add_axes([0.01, 0.01, 0.8, 0.92])
    draw_entities(ax, ents, lambda e: color[e.get("layer")], texts=len(ents) < 1500)
    sheet_axes(ax, bbox)
    lg = fig.add_axes([0.82, 0.01, 0.17, 0.92])
    counts = Counter(e.get("layer") for e in ents)
    lines = ["레이어 (개수)"] + [f"{name}  ({counts[name]})" for name in layers[:30]]
    lg.axis("off")
    for i, line in enumerate(lines):
        lg.text(
            0,
            1 - i * 0.035,
            line,
            color="black" if i == 0 else color[layers[i - 1]],
            fontsize=10,
            transform=lg.transAxes,
            va="top",
        )
    fig.suptitle(
        f"01 read: DXF 요소 {len(ents)}개를 레이어별 색으로  (점선 = 숨은선)",
        fontsize=13,
    )
    return fig


def f02(d, ctx):
    ents = (ctx.stage(1) or {}).get("entities", [])
    bbox = sheet_bbox(ctx, ents)
    region = d.get("title_region")
    fig = figure_for_sheet(bbox, extra=0)
    ax = fig.add_axes([0.01, 0.30, 0.55, 0.63])
    faded(ctx, ax, ents)
    sheet_axes(ax, bbox)
    if region:
        box(ax, region, "#d62728", "표제란")
        zx = fig.add_axes([0.58, 0.30, 0.41, 0.63])
        inside = [
            e
            for e in ents
            if (b := ent_bbox(e))
            and b[0] >= region[0] - 1
            and b[2] <= region[2] + 1
            and b[1] >= region[1] - 1
            and b[3] <= region[3] + 1
        ]
        draw_entities(zx, inside, lambda e: "#222", lw=0.8)
        for t in zx.texts:
            t.set_fontsize(9)
        sheet_axes(zx, region)
        zx.set_title("표제란 확대", fontsize=10)
    truth = truth_title(ctx)
    tb = d.get("title_block", {})
    missing = set(d.get("missing") or [])
    rows, colors = [], []
    for k in TITLE_FIELDS:
        t = truth.get(k, [None])[0]
        ok = same(tb.get(k), t) if truth else None
        rows.append(
            [
                k,
                tb.get(k),
                (tb.get("sources") or {}).get(k, ""),
                "못 읽음" if k in missing else "",
                t if truth else "",
            ]
        )
        colors.append(
            [
                "white",
                match_color(ok),
                "white",
                "#f9d6d5" if k in missing else "white",
                "white",
            ]
        )
    table_panel(
        fig.add_axes([0.02, 0.0, 0.96, 0.28]),
        rows,
        ["필드", "정규식 결과", "출처", "", "정답"],
        colors,
    )
    fig.suptitle(
        "02 title_regex: 표제란 위치와 정규식으로 읽은 필드  (초록=정답과 같음, 빨강=다름·못 읽음)",
        fontsize=13,
    )
    return fig


def f03(d, ctx):
    img = ctx.work / "analysis" / "title_block.png"
    fig = plt.figure(figsize=(14, 5))
    if img.is_file():
        ax = fig.add_axes([0.01, 0.02, 0.55, 0.86])
        ax.imshow(plt.imread(img))
        ax.axis("off")
        ax.set_title("OCR 모델에 넣은 그림 (analysis/title_block.png)", fontsize=10)
    text_panel(
        fig.add_axes([0.6, 0.02, 0.39, 0.86]),
        ["OCR 모델이 받아쓴 글자:", "", *str(d.get("text") or "(없음)").splitlines()],
        size=11,
    )
    fig.suptitle(f"03 title_ocr: {d.get('model')}", fontsize=13)
    return fig


def f04(d, ctx):
    regex = (ctx.stage(2) or {}).get("title_block", {})
    fields = d.get("fields") or {}
    final = d.get("title_block", {})
    truth = truth_title(ctx)
    rows, colors = [], []
    for k in TITLE_FIELDS:
        t = truth.get(k, [None])[0]
        ok_final = same(final.get(k), t) if truth else None
        ok_model = (
            same(fields.get(k), t) if truth and fields.get(k) is not None else None
        )
        src = (final.get("sources") or {}).get(k, "")
        rows.append(
            [
                k,
                regex.get(k),
                fields.get(k),
                final.get(k),
                "모델" if "vlm" in src else ("정규식" if src else ""),
                t if truth else "",
            ]
        )
        colors.append(
            [
                "white",
                "white",
                match_color(ok_model),
                match_color(ok_final),
                "white",
                "white",
            ]
        )
    fig = plt.figure(figsize=(13, 3.6))
    table_panel(
        fig.add_axes([0.02, 0.02, 0.96, 0.82]),
        rows,
        ["필드", "02 정규식", "04 모델 답", "최종", "최종 출처", "정답"],
        colors,
    )
    fig.suptitle(
        f"04 title_fields: {d.get('model')} 이 OCR 글자를 필드로 정리. 최종 = 정규식 값이 있으면 그것, 없으면 모델 답",
        fontsize=12,
    )
    return fig


def f05(d, ctx):
    ents = (ctx.stage(1) or {}).get("entities", [])
    bbox = sheet_bbox(ctx, ents)
    fig = figure_for_sheet(bbox)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.9])
    faded(ctx, ax, ents)
    for b in d.get("frames") or []:
        box(ax, b, "#1f77b4", "", lw=1.2, ls="--")
    for b in d.get("excluded_regions") or []:
        box(ax, b, "#7f7f7f", "", lw=1, fill="#7f7f7f33")
    for v in d.get("views", []):
        box(ax, v["bbox"], "#ff7f0e", f"뷰 {v['id']}")
    sheet_axes(ax, bbox)
    ev = d.get("sheet_type_evidence") or {}
    fig.suptitle(
        f"05 views: 뷰 후보 {len(d.get('views', []))}개 (주황), 제외 영역 (회색), 도면 틀 (파란 점선)   도면 종류: {d.get('sheet_type')}  "
        f"(도형 묶음 {ev.get('clusters')}, 정면과 축이 맞는 묶음 {ev.get('aligned_axes_at_best_front')})",
        fontsize=12,
    )
    return fig


def f06(d, ctx):
    ents = (ctx.stage(1) or {}).get("entities", [])
    bbox = sheet_bbox(ctx, ents)
    lab = ctx.label or {}
    dec = d.get("decision") or {}
    fig = figure_for_sheet(bbox, extra=4)
    ax = fig.add_axes([0.01, 0.01, 0.68, 0.9])
    faded(ctx, ax, ents)
    for v in d.get("views", []):
        name = v.get("label")
        truth = label_view(ctx, v.get("bbox")) if lab else None
        tag = f"{v['id']} {name} {v.get('confidence', 0):.2f}"
        if truth and truth != name:
            tag += f"  (정답 {truth})"
        box(ax, v["bbox"], VIEW_COLORS.get(name, "#7f7f7f"), tag)
    sheet_axes(ax, bbox)
    px = fig.add_axes([0.74, 0.45, 0.24, 0.42])
    probs = dec.get("part_class_probabilities") or {}
    if dec.get("used") and probs:
        names = list(probs)
        bars = px.barh(
            names,
            [probs[n] for n in names],
            color=["#2ca02c" if n == lab.get("class") else "#1f77b4" for n in names],
        )
        px.set_xlim(0, 1)
        px.invert_yaxis()
        px.set_title(
            "형상(part_class) 확률" + ("  초록 = 정답" if lab else ""), fontsize=10
        )
        for b, n in zip(bars, names):
            px.text(
                min(b.get_width() + 0.02, 0.8),
                b.get_y() + b.get_height() / 2,
                f"{probs[n]:.1%}",
                va="center",
                fontsize=8,
            )
    else:
        px.axis("off")
        px.text(0, 0.5, "모델을 쓰지 않아\n형상을 정하지 않았다", fontsize=12)
    lines = [
        f"모델 판단: {'사용' if dec.get('used') else '안 씀 (위치 규칙)'}",
        f"형상: {dec.get('part_class')}"
        + (f"   정답 {lab.get('class')}" if lab else ""),
        f"투상법: {d.get('projection')}"
        + (f"   정답 {lab.get('sheet', {}).get('projection')}" if lab else ""),
        f"3D 복원 가능: {dec.get('reconstructable')}"
        + (f"   정답 {lab.get('wireframe_reconstructable')}" if lab else ""),
    ]
    if dec.get("error"):
        lines.append(f"모델 답 오류: {dec['error']}")
    text_panel(fig.add_axes([0.72, 0.02, 0.27, 0.38]), lines, size=10)
    fig.suptitle(
        "06 view_labels: 뷰 라벨 (front 빨강, top 파랑, right 초록, 그 밖 회색)과 형상 판단",
        fontsize=13,
    )
    return fig


def f08(d, ctx):
    doc = d.get("document") or {}
    views = doc.get("views") or []
    if not views:
        return None
    fig, axes = plt.subplots(
        1, len(views), figsize=(5 * len(views), 5.5), squeeze=False
    )
    style = {
        "visible": ("#222", "-"),
        "hidden": ("#1f77b4", "--"),
        "center": ("#2ca02c", "-."),
    }
    for ax, v in zip(axes[0], views):
        segs, cols, ls = [], [], []
        for p in v.get("primitives", []):
            c, s = style.get(p.get("line_type"), ("#222", "-"))
            if p.get("kind") == "line" and len(p.get("points") or []) >= 2:
                for a, b in zip(p["points"], p["points"][1:]):
                    segs.append([a, b])
                    cols.append(c)
                    ls.append(s)
            elif p.get("kind") == "circle" and p.get("center"):
                r = p["radius"]
                ax.add_patch(Arc(p["center"], 2 * r, 2 * r, color=c, ls=s, lw=1))
        if segs:
            ax.add_collection(
                LineCollection(segs, colors=cols, linestyles=ls, linewidths=1)
            )
        for a in v.get("annotations", []):
            if a.get("position"):
                txt = (
                    f"{a['value']:g}"
                    if a.get("value") is not None
                    else a.get("text", "")
                )
                ax.text(
                    *a["position"],
                    txt,
                    color="#d62728" if a.get("kind") == "dimension" else "#555",
                    fontsize=9,
                )
        pos = [a["position"] for a in v.get("annotations", []) if a.get("position")]
        if pos:
            ax.update_datalim(pos)
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.margins(0.08)
        ax.set_title(
            v.get("name"),
            color=VIEW_COLORS.get(v.get("name"), "black"),
            fontsize=12,
            fontweight="bold",
        )
    meta = doc.get("metadata") or {}
    dims = meta.get("dimensions") or {}
    t = f"08 document: 3D 복원에 넘기는 front/top/right 뷰 (left 등은 미러해 바꾼다).  전체 치수 x={dims.get('x')} y={dims.get('y')} z={dims.get('z')}  판 두께 {meta.get('sheet_thickness')}"
    if ctx.label:
        t += f"   정답 {ctx.label.get('extents')}"
    fig.suptitle(
        t + "\n검정 = 외형선, 파란 점선 = 숨은선, 초록 = 중심선, 빨강 = 치수",
        fontsize=11,
    )
    return fig


def f09(d, ctx):
    rec = d.get("record") or {}
    params, sources = rec.get("params") or {}, rec.get("sources") or {}
    rows = [
        [
            k,
            v,
            "모델"
            if "vlm" in str(sources.get(k))
            else "코드 (전체 치수로 채움)"
            if sources.get(k) == "overall_dimensions"
            else sources.get(k),
        ]
        for k, v in params.items()
    ]
    colors = [
        ["white", "white", "#dbe9f6" if r[2] == "모델" else "#fde6cf"] for r in rows
    ]
    fig = plt.figure(figsize=(13, 2.4 + 0.3 * len(rows)))
    table_panel(
        fig.add_axes([0.02, 0.42, 0.96, 0.45]),
        rows,
        ["파라미터", "값", "누가 채웠나"],
        colors,
    )
    lines = [f"전개 종류: {rec.get('part_type')}   확신도: {rec.get('confidence')}"]
    if ctx.label:
        lines.append(
            f"정답 params: {json.dumps(ctx.label.get('params'), ensure_ascii=False)}   두께 {ctx.label.get('thickness')}"
        )
    for n in rec.get("fallback_notes") or []:
        lines.append(f"코드 보충: {n}")
    text_panel(fig.add_axes([0.02, 0.02, 0.96, 0.36]), lines, size=10)
    fig.suptitle(
        "09 unfold_params: 전개 파라미터 (파랑 = 모델이 읽음, 주황 = 코드가 채움)",
        fontsize=13,
    )
    return fig


def blank_shape(ax, vals: dict, color: str, ls: str, label: str) -> bool:
    """전개 결과 하나를 그린다. 부채꼴(원뿔), 직사각형(원통·평판·절곡), 원(경판) 을 안다."""
    outer = vals.get("outer_radius", vals.get("sector_outer_radius"))
    inner = vals.get("inner_radius", vals.get("sector_inner_radius"))
    angle = vals.get("angle_deg", vals.get("sector_angle_deg"))
    if outer and inner is not None and angle:
        a1, a2 = 90 - angle / 2, 90 + angle / 2
        for r in (outer, inner):
            ax.add_patch(
                Arc(
                    (0, 0),
                    2 * r,
                    2 * r,
                    theta1=a1,
                    theta2=a2,
                    color=color,
                    ls=ls,
                    lw=1.6,
                )
            )
        for a in (a1, a2):
            t = math.radians(a)
            ax.plot(
                [inner * math.cos(t), outer * math.cos(t)],
                [inner * math.sin(t), outer * math.sin(t)],
                color=color,
                ls=ls,
                lw=1.6,
                label=label if a == a1 else None,
            )
        ax.update_datalim(
            [
                (outer * math.cos(math.radians(a)), outer * math.sin(math.radians(a)))
                for a in (a1, 90, a2)
            ]
            + [(0, inner * math.sin(math.radians(a1)))]
        )
        return True
    if vals.get("length") and vals.get("width"):
        w, h = vals["length"], vals["width"]
        ax.add_patch(
            Rectangle((0, 0), w, h, fill=False, ec=color, ls=ls, lw=1.6, label=label)
        )
        for x in vals.get("bend_lines") or []:
            ax.plot([x, x], [0, h], color=color, ls=":", lw=1)
        ax.update_datalim([(0, 0), (w, h)])
        return True
    if vals.get("blank_diameter"):
        r = vals["blank_diameter"] / 2
        ax.add_patch(Arc((0, 0), 2 * r, 2 * r, color=color, ls=ls, lw=1.6, label=label))
        ax.update_datalim([(-r, -r), (r, r)])
        return True
    return False


def f10(d, ctx):
    rec = d.get("record") or {}
    blank = rec.get("blank") or {}
    truth = (ctx.label or {}).get("flat_pattern") or {}
    fig = plt.figure(figsize=(15, 6))
    ax = fig.add_axes([0.04, 0.08, 0.42, 0.78])
    drawn = blank_shape(ax, blank, "#222", "-", "계산 결과")
    if truth and blank_shape(ax, truth, "#2ca02c", "--", "정답"):
        drawn = True
    if drawn:
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.margins(0.08)
        ax.legend(loc="upper right")
        ax.set_title(
            "계산 결과 (검정) 와 정답 (초록 점선) 을 같은 축척으로", fontsize=10
        )
    else:
        ax.axis("off")
    rows = [
        [k, round(v, 2) if isinstance(v, float) else v]
        for k, v in blank.items()
        if k != "formula"
    ]
    table_panel(fig.add_axes([0.52, 0.45, 0.46, 0.42]), rows, ["계산 결과", "값"])
    lines = [f"공식: {blank.get('formula', '-')}"]
    if truth:
        lines += ["", "정답 flat_pattern:"] + [f"  {k}: {v}" for k, v in truth.items()]
    lines += [f"경고: {w}" for w in rec.get("warnings") or []]
    text_panel(fig.add_axes([0.52, 0.02, 0.46, 0.4]), lines, size=10)
    fig.suptitle(
        f"10 develop: {rec.get('part_type')} 전개 계산 (코드). 단계가 그린 flat_pattern.png 는 HTML 에 있다",
        fontsize=13,
    )
    return fig


def f11(d, ctx):
    res = d.get("result") or {}
    cands = (res.get("candidates") or [])[:4]
    evals = {e.get("candidate_id"): e for e in res.get("evaluations") or []}
    if not cands:
        fig = plt.figure(figsize=(12, 4))
        rr = res.get("review_request") or {}
        lines = ["3D 후보를 만들지 못했다.", ""] + [
            f"- {a.get('kind')}: {a.get('message', '')}"
            for a in rr.get("ambiguities") or []
        ]
        text_panel(fig.add_axes([0.02, 0.02, 0.96, 0.85]), lines, size=11)
        fig.suptitle("11 reconstruct: 후보 0개", fontsize=13)
        return fig
    fig = plt.figure(figsize=(5 * len(cands), 5.5))
    for i, c in enumerate(cands):
        ax = fig.add_subplot(1, len(cands), i + 1, projection="3d")
        vs = c.get("vertices") or []
        for a, b in c.get("edges") or []:
            ax.plot(*zip(vs[a], vs[b]), color="#222", lw=0.8)
        if vs:
            span = (
                max(max(p[k] for p in vs) - min(p[k] for p in vs) for k in range(3))
                or 1
            )
            mid = [
                (max(p[k] for p in vs) + min(p[k] for p in vs)) / 2 for k in range(3)
            ]
            ax.set_xlim(mid[0] - span / 2, mid[0] + span / 2)
            ax.set_ylim(mid[1] - span / 2, mid[1] + span / 2)
            ax.set_zlim(mid[2] - span / 2, mid[2] + span / 2)
        e = evals.get(c.get("id"), {})
        ax.set_title(
            f"{c.get('id')}\n통과 {e.get('valid')}  점수 {e.get('score')}", fontsize=10
        )
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("z")
    fig.suptitle(
        f"11 reconstruct: 3D 와이어프레임 후보 {len(res.get('candidates') or [])}개",
        fontsize=13,
    )
    return fig


DRAW = {
    1: f01,
    2: f02,
    3: f03,
    4: f04,
    5: f05,
    6: f06,
    8: f08,
    9: f09,
    10: f10,
    11: f11,
}
# 단계가 직접 남긴 그림. HTML 에 함께 보여 준다
OWN = {
    3: ["analysis/title_block.png"],
    6: ["analysis/sheet_labeled.png"],
    7: ["analysis/sheet.png"],
    10: ["flat_pattern.png"],
    12: ["analysis/candidates.png"],
}
CSS = """
body{font-family:'Nanum Gothic','Noto Sans KR',sans-serif;margin:24px;background:#fafafa;color:#222}
section{background:#fff;border:1px solid #ddd;border-radius:8px;padding:16px;margin-bottom:24px}
h2{margin:0 0 8px}.done{color:#2a7a2a}.skipped{color:#a66b00}.failed{color:#c0392b}
img{max-width:100%;border:1px solid #eee;margin:6px 0}pre{background:#f4f4f4;padding:10px;overflow-x:auto;font-size:12px}
nav a{margin-right:10px}
"""


def draw_step(step: int, ctx: Ctx, dpi: int) -> Path | None:
    """단계 그림을 figures/NN_<단계>.png 로 쓴다. 그릴 것이 없으면 옛 그림을 지우고 None."""
    d = ctx.stage(step)
    png = ctx.work / "figures" / f"{step:02d}_{d.get('stage')}.png"
    png.parent.mkdir(exist_ok=True)
    png.unlink(missing_ok=True)
    if d.get("status") != "done" or step not in DRAW:
        return None
    fig = DRAW[step](d, ctx)
    if fig is None:
        return None
    fig.savefig(png, dpi=dpi, facecolor="white")
    plt.close(fig)
    return png


def own_images(step: int, ctx: Ctx) -> list[str]:
    """단계가 직접 남긴 그림 (작업 폴더 기준 경로)."""
    if (ctx.stage(step) or {}).get("status") != "done":
        return []
    return [p for p in OWN.get(step, []) if (ctx.work / p).is_file()]


def write_index(ctx: Ctx) -> Path:
    """figures/index.html: 모든 단계의 그림과 표를 한 페이지에."""
    out = ctx.work / "figures"
    out.mkdir(exist_ok=True)
    sections = []
    for step in sorted(ctx.files):
        d = ctx.stage(step)
        name = f"{step:02d}_{d.get('stage')}"
        imgs = [f"{name}.png"] if (out / f"{name}.png").is_file() else []
        imgs += [f"../{p}" for p in own_images(step, ctx)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            show(step, ctx)
        body = "".join(
            f'<img src="{html.escape(i)}" alt="{html.escape(i)}">' for i in imgs
        )
        sections.append(
            f'<section id="{name}"><h2>{name} <span class="{d.get("status")}">{d.get("status")}</span></h2>'
            f"{body}<pre>{html.escape(buf.getvalue().strip())}</pre></section>"
        )
    nav = " ".join(f'<a href="#{f.stem}">{f.stem[:2]}</a>' for f in ctx.files.values())
    label = (
        f"정답 label.json: {ctx.label.get('id')}"
        if ctx.label
        else "정답 label.json 없음"
    )
    source = (ctx.stage(1) or {}).get("source", "")
    title = html.escape(ctx.work.name)
    page = (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title} 판독 단계</title>'
        f"<style>{CSS}</style></head><body><h1>{title} 판독 단계</h1>"
        f"<p>{html.escape(source)} · {html.escape(label)}</p><nav>{nav}</nav>{''.join(sections)}</body></html>"
    )
    index = out / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def report(
    work: Path,
    steps: list[int] | None = None,
    *,
    raw: bool = False,
    limit: int = 30,
    figures: bool = True,
    dpi: int = 110,
) -> None:
    """고른 단계(없으면 전부)의 표를 출력하고, figures 이면 그림과 index.html 을 쓴다."""
    ctx = Ctx(Path(work), limit, raw)
    if not ctx.files:
        raise SystemExit(f"단계 파일이 없다: {Path(work) / 'stages'}")
    print(f"작업 폴더: {work}")
    print(
        f"정답 label.json: {'있음 (' + ctx.label.get('id', '') + ')' if ctx.label else '없음'}"
    )
    for step in steps or sorted(ctx.files):
        if step not in ctx.files:
            print(f"\n=== {step:02d} {stage_name(step)}: 아직 실행하지 않았다 ===")
            continue
        show(step, ctx)
        if figures:
            png = draw_step(step, ctx, dpi)
            pics = ([str(png)] if png else []) + [
                str(ctx.work / p) for p in own_images(step, ctx)
            ]
            if pics:
                print("\n  [그림]")
                for p in pics:
                    print(f"    {p}")
    if figures:
        print(f"\n단계 전체 그림과 표: {write_index(ctx)}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("work", type=Path, help="작업 폴더 (stages/ 가 있는 폴더)")
    ap.add_argument("steps", nargs="*", help="단계 번호, 이름, 범위(6-9). 없으면 전부")
    ap.add_argument("--raw", action="store_true", help="모델 원문 응답도 출력")
    ap.add_argument(
        "--limit", type=int, default=30, help="목록 최대 줄 수 (0 이면 전부)"
    )
    ap.add_argument("--no-figures", action="store_true", help="표만 출력")
    ap.add_argument("--dpi", type=int, default=110, help="그림 해상도")
    a = ap.parse_args()
    report(
        a.work,
        parse_steps(a.steps),
        raw=a.raw,
        limit=a.limit,
        figures=not a.no_figures,
        dpi=a.dpi,
    )


if __name__ == "__main__":
    main()
