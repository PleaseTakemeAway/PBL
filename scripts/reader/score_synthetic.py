"""reader 배치 출력을 합성 도면 정답(label.json)과 단계별로 대조해 점수를 낸다.

사용 (레포 루트에서):
  uv run python scripts/reader/score_synthetic.py <배치 출력 폴더> [--out <score.md>]

  배치 출력 폴더 아래에서 <도면>/prediction.json 을 모두 찾는다 (하위 폴더 여러 개에
  나눠 돌린 결과도 된다). 정답은 prediction.json 의 source 옆 label.json 이다.
  --out 을 주지 않으면 <배치 출력 폴더>/score.md 와 score.json 을 쓴다.

항목은 docs/v3_upgrade.md 2절의 "완벽하게" 기준이다.
  단계    01~10 단계 파일이 모두 done
  표제란  도면 번호, 축척, 재질, 두께가 정답과 같다
  뷰      뷰 이름 집합이 정답과 같다 (front, top, right)
  형상    final_part_class 가 정답 class 와 같다
  치수    전개 파라미터(09)가 정답 params 와 같다. reader 는 안지름을 쓰므로 외경 − 2t 로 바꿔 비교한다
  전개    전개 값이 정답과 1% 이내 (reader 의 evaluate_against_label)
단계 파일만 읽고 cutplan_agent 를 import 하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

STAGES = [
    "01_read",
    "02_title_regex",
    "03_title_ocr",
    "04_title_fields",
    "05_views",
    "06_view_labels",
    "07_sheet",
    "08_document",
    "09_unfold_params",
    "10_develop",
]
ITEMS = ["단계", "표제란", "뷰", "형상", "치수", "전개"]
CLASSES = ["flat", "bent_sheet", "cylinder", "cone", "press_formed"]
TOL_MM = 0.5


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _close(pred, true) -> bool:
    try:
        return abs(float(pred) - float(true)) <= max(TOL_MM, 0.005 * abs(float(true)))
    except (TypeError, ValueError):
        return False


def score_stages(stages: Path) -> tuple[bool, str]:
    bad = []
    for name in STAGES:
        status = _load(stages / f"{name}.json").get("status")
        if status != "done":
            bad.append(f"{name[:2]} {status or 'missing'}")
    return not bad, ", ".join(bad)


def score_title(stages: Path, label: dict) -> tuple[bool, str]:
    tb = _load(stages / "06_view_labels.json").get("title_block") or _load(
        stages / "04_title_fields.json"
    ).get("title_block", {})
    sheet = label.get("sheet", {})
    material = str(tb.get("material") or "").split(",")[0].strip().upper()
    checks = {
        "도면 번호": tb.get("drawing_no") == sheet.get("drawing_no"),
        "축척": tb.get("scale_text") == sheet.get("scale_text"),
        "재질": material == str(sheet.get("material", "")).upper(),
        "두께": _close(tb.get("thickness_mm"), label.get("thickness")),
    }
    bad = [k for k, ok in checks.items() if not ok]
    return not bad, ", ".join(bad)


def score_views(pred: dict, label: dict) -> tuple[bool, str]:
    got = sorted(str(v.get("label")) for v in pred.get("views") or [])
    want = sorted(label.get("views") or [])
    return got == want, "" if got == want else f"{got} ≠ {want}"


def expected_params(label: dict) -> dict:
    """정답 params 를 reader 의 전개 파라미터 이름과 값(안지름)으로 바꾼다."""
    p, t = label.get("params", {}), label.get("thickness")
    cls = label.get("class")
    if cls == "cylinder":
        return {"inner_dia": p["outer_diameter"] - 2 * t, "length": p["length"]}
    if cls == "cone":
        # 지름은 끝면에서 가로로 잰다. 기운 벽의 두께는 가로로 t / cos α 다 (docs/v3_upgrade.md 5.4절)
        big, small, h = (
            p["large_outer_diameter"],
            p["small_outer_diameter"],
            p["height"],
        )
        across = t / math.cos(math.atan((big - small) / 2 / h))
        return {
            "large_inner_dia": big - 2 * across,
            "small_inner_dia": small - 2 * across,
            "cone_height": h,
        }
    if cls == "press_formed":
        return {"inner_dia": p["outer_diameter"] - 2 * t}
    if cls == "bent_sheet":
        return {
            "width": p["width"],
            "segments": [p["leg_a"], p["leg_b"]],
            "bend_angles": [90],
            "bend_radii": [p["bend_radius"]],
        }
    if cls == "flat":
        return {"outline_size": sorted([p["length"], p["width"]])}
    return {}


def score_params(stages: Path, label: dict) -> tuple[bool, str]:
    params = _load(stages / "09_unfold_params.json").get("record", {}).get("params")
    if not params:
        return False, "params 없음"
    got = dict(params)
    outline = got.get("outline")
    if outline:
        xs = [float(q[0]) for q in outline]
        ys = [float(q[1]) for q in outline]
        got["outline_size"] = sorted([max(xs) - min(xs), max(ys) - min(ys)])
    want = expected_params(label)
    want["thickness"] = label.get("thickness")
    bad = []
    for key, true in want.items():
        if key == "thickness" and label.get("class") == "flat":
            continue  # flat 의 전개 파라미터에는 두께가 없다 (outline 만)
        pred = got.get(key)
        if key == "segments" and isinstance(pred, list):
            # 다리 순서(수평판·수직판)는 전개 길이를 바꾸지 않는다
            pred, true = sorted(pred, key=float), sorted(true)
        if isinstance(true, list):
            ok = (
                isinstance(pred, list)
                and len(pred) == len(true)
                and all(_close(a, b) for a, b in zip(pred, true))
            )
        else:
            ok = _close(pred, true)
        if not ok:
            bad.append(f"{key} {pred} ≠ {true}")
    return not bad, "; ".join(bad)


def score_flat(record: dict) -> tuple[bool, str]:
    fp = record.get("flat_pattern") or {}
    ev = fp.get("evaluation") or {}
    if ev.get("within_1pct"):
        return True, ""
    if fp.get("status") != "developed":
        return False, f"{fp.get('status')}: {fp.get('reason') or ''}".strip()
    err = ev.get("max_rel_error")
    return False, f"오차 {err:.1%}" if isinstance(err, (int, float)) else "평가 없음"


def score_drawing(pred_path: Path) -> dict:
    record = _load(pred_path)
    label = _load(Path(record["source"]).parent / "label.json")
    stages = pred_path.parent / "stages"
    pred = record.get("prediction", {})
    got_class = pred.get("final_part_class") or pred.get("part_class")
    results = {
        "단계": score_stages(stages),
        "표제란": score_title(stages, label),
        "뷰": score_views(pred, label),
        "형상": (
            got_class == label.get("class"),
            "" if got_class == label.get("class") else f"{got_class}",
        ),
        "치수": score_params(stages, label),
        "전개": score_flat(record),
    }
    return {
        "id": record.get("id"),
        "class": label.get("class"),
        "ok": {k: v[0] for k, v in results.items()},
        "why": {k: v[1] for k, v in results.items() if not v[0]},
    }


def render(rows: list[dict], root: Path) -> str:
    n = len(rows)
    lines = [
        f"# 단계별 점수: `{root}`",
        "",
        f"도면 {n}장. 기준은 docs/v3_upgrade.md 2절.",
        "",
    ]
    lines += ["| 항목 | 맞음 | " + " | ".join(CLASSES) + " |"]
    lines += ["|---|---:|" + "---:|" * len(CLASSES)]
    by_class = defaultdict(list)
    for r in rows:
        by_class[r["class"]].append(r)
    for item in ITEMS + ["전부"]:

        def ok(r):
            return all(r["ok"].values()) if item == "전부" else r["ok"][item]

        cells = [
            f"{sum(ok(r) for r in by_class[c])}/{len(by_class[c])}" for c in CLASSES
        ]
        lines.append(
            f"| {item} | {sum(ok(r) for r in rows)}/{n} | " + " | ".join(cells) + " |"
        )
    lines += ["", "## 도면별", "", "| 도면 | " + " | ".join(ITEMS) + " | 틀린 이유 |"]
    lines += ["|---|" + ":-:|" * len(ITEMS) + "---|"]
    for r in rows:
        marks = " | ".join("O" if r["ok"][k] else "X" for k in ITEMS)
        why = "<br>".join(f"{k}: {v}" for k, v in r["why"].items())
        lines.append(f"| {r['id']} | {marks} | {why} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path, help="reader --batch 출력 폴더")
    ap.add_argument("--out", type=Path, help="점수 표 (기본 <root>/score.md)")
    args = ap.parse_args()
    preds = sorted(args.root.glob("**/prediction.json"), key=lambda p: p.parent.name)
    rows = [score_drawing(p) for p in preds]
    out = args.out or args.root / "score.md"
    out.write_text(render(rows, args.root), encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(out.read_text(encoding="utf-8").split("## 도면별")[0].rstrip())
    print(f"-> {out}")


if __name__ == "__main__":
    main()
