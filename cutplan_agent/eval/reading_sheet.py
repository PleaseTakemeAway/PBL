# -*- coding: utf-8 -*-
"""
수동 판독용 '판독 시트' 생성: ingest 로 만든 DXF 텍스트 덤프에서 BOM 행(판재만)과 치수 후보를 자동으로 뽑아 markdown 으로.

    uv run python -m cutplan_agent.eval.reading_sheet --job KD23022_manual

출력: runs/<job>/reading_sheet.md
  - 도면별: 세트 수 문구, BOM 판재 행 (품번 | 품명 | 재질 | 수량 | 단위 | SIZE), 전개 판정(키워드)
  - 치수 후보: I.D / O.D / Ø 값, T.L, 용접선 라벨(SA/SB/CA/HA-xx) 과 그 근처 치수 오버라이드, 2:1 ELLIP, CONE 각도
  - 래스터(PDF) 도면: 눈으로 읽어야 할 파일 목록 + BOM 영역 크롭 PNG 생성
사람이 이 시트를 보고 spec.json 을 쓴다.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from cutplan_agent.config import RUNS_DIR, UNFOLD_CLASS

PLATE_MAT = re.compile(
    r"^(SA|A)\s?(516|283|285|240|387|36|204|537)|^SS\s?400|^S(S|US)\s?3\d{2}|^B168|^SPCC|^SPHC|^St\s?37|^SB\s?\d",
    re.I,
)
NON_PLATE = re.compile(
    r"SA\s?106|SA\s?105|SA\s?182|SA\s?193|SA\s?194|SA\s?312|SA\s?403|SA\s?234|SA\s?266|SA\s?179|SA\s?213|S20C|SCH\s?\d|NUT|BOLT|GASKET|PIPE|FLANGE|STUD|PLUG|SOCKET|TEFLON|NOTE \d|TUBE$|SPACER|TIE ROD|WASHER",
    re.I,
)
SETS = re.compile(r"(ONE|TWO|THREE|FOUR|FIVE|SIX)\s*\((\d)\)\s*SETS?", re.I)


def unfold_class(name: str) -> str:
    n = name.upper()
    for cls, keys in UNFOLD_CLASS.items():
        if any(k in n for k in keys):
            if cls == "pad_ring" and any(
                x in n for x in ("LEG", "LUG", "WEAR", "SUPPORT", "SADDLE")
            ):
                return "flat"
            return cls
    return "?"


def bom_rows(t: dict, xfrac: float = 0.72):
    texts = t["texts"]
    if not texts:
        return [], 1
    xs = [x["x"] for x in texts]
    x0, x1 = min(xs), max(xs)
    rows = {}
    for x in texts:
        if (x["x"] - x0) / max(x1 - x0, 1) < xfrac:
            continue
        rows.setdefault(round(x["y"] / 3) * 3, []).append(x)
    out = []
    mult = 1
    for k in sorted(rows, reverse=True):
        cells = [x["text"] for x in sorted(rows[k], key=lambda z: z["x"])]
        line = " | ".join(cells)
        m = SETS.search(line)
        if m:
            mult = int(m.group(2))
        if not re.search(r"\|\s*(EA|SET|SH'?T)\s*\|", line, re.I):
            continue
        # 열 추정: ... | NAME | MATERIAL | QTY | [spare] | UNIT | SIZE
        try:
            ui = next(
                i
                for i, c in enumerate(cells)
                if re.fullmatch(r"(EA|SET|SH'?T)", c.strip(), re.I)
            )
        except StopIteration:
            continue
        size = " ".join(cells[ui + 1 :]).strip()
        qty_i = None
        for i in range(ui - 1, -1, -1):
            if re.fullmatch(r"\d+", cells[i].strip()):
                qty_i = i
                break
        if qty_i is None:
            continue
        # 재질은 qty 앞 비숫자 셀, 이름은 그 앞
        mat_i = qty_i - 1
        while mat_i > 0 and re.fullmatch(r"\d+", cells[mat_i].strip()):
            mat_i -= 1
        material = cells[mat_i].strip() if mat_i >= 0 else ""
        name = cells[mat_i - 1].strip() if mat_i - 1 >= 0 else ""
        item = " ".join(c.strip() for c in cells[: max(mat_i - 1, 0)])
        qty = int(cells[qty_i])
        is_plate = bool(PLATE_MAT.search(material)) and not NON_PLATE.search(
            f"{material} {size} {name}"
        )
        thk = None
        mm = re.search(
            r"(?:^|[^\d.])t\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*[tT](?![a-zA-Z])",
            size + " " + material,
        )
        if mm:
            thk = float(next(g for g in mm.groups() if g))
        out.append(
            {
                "item": item,
                "name": name,
                "material": material,
                "qty": qty,
                "unit": cells[ui].strip(),
                "size": size,
                "is_plate": is_plate,
                "t": thk,
                "cls": unfold_class(name) if is_plate else "",
            }
        )
    return out, mult


def dim_candidates(t: dict):
    txt = t["texts"]
    dims = t["dims"]
    ids = [
        x["text"]
        for x in txt
        if re.search(
            r"\b[IO]\.?D\.?\s*\d{3,5}|%%C\s?\d{3,5}|Ø\s?\d{3,5}|SHELL O\.?D",
            x["text"],
            re.I,
        )
    ]
    seams = [
        x
        for x in txt
        if re.fullmatch(
            r"(SA|SB|CA|CB|HA|HB|NA)-?\d{2}[a-z]?(,.*)?", x["text"].strip(), re.I
        )
    ]
    seam_dims = []
    for s in seams:
        near = [
            d
            for d in dims
            if d["x"] is not None
            and abs(d["x"] - s["x"]) < 400
            and abs(d["y"] - s["y"]) < 400
            and d["text_override"]
        ]
        seam_dims.append((s["text"], [d["text_override"] for d in near][:4]))
    heads = [
        x["text"]
        for x in txt
        if re.search(
            r"ELLIP|TORISPH|HEMI|HEAD.*THK|USED THK|AFTER FORMING|CONE|REDUCER|T\.L|TAN",
            x["text"],
            re.I,
        )
    ]
    big = sorted(
        {
            float(d["text_override"])
            for d in dims
            if d["text_override"]
            and re.fullmatch(r"\d{3,5}(\.\d+)?", d["text_override"])
            and 150 <= float(d["text_override"]) <= 14000
        },
        reverse=True,
    )
    # 치수가 TEXT 로 분해된 도면: 숫자만 있는 텍스트도 후보로 (큰 값부터)
    num_txt = sorted(
        {
            float(x["text"])
            for x in txt
            if re.fullmatch(r"\d{3,5}(\.\d+)?", x["text"].strip())
            and 150 <= float(x["text"]) <= 14000
        },
        reverse=True,
    )
    return {
        "id_od": sorted(set(ids))[:25],
        "seams": seam_dims[:20],
        "head_cone": sorted(set(heads))[:15],
        "big_dims": big[:40],
        "num_texts": num_txt[:40],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    a = ap.parse_args()
    d = RUNS_DIR / a.job
    ing = json.loads((d / "ingest.json").read_text(encoding="utf8"))
    L = [f"# 판독 시트 — {a.job}", ""]
    all_plates = []
    for rec in ing:
        L.append(f"## [{rec['index']}] {rec['name']}  ({rec['kind']})")
        if rec.get("dxf_text"):
            t = json.loads(Path(rec["dxf_text"]).read_text(encoding="utf8"))
            rows, mult = bom_rows(t)
            L.append(
                f"세트 수: ×{mult}   BOM 행 {len(rows)}개 (판재 {sum(1 for r in rows if r['is_plate'])})"
            )
            L.append("| 품번 | 품명 | 재질 | 수량 | 단위 | SIZE | t | 판정 |")
            L.append("|---|---|---|---|---|---|---|---|")
            for r in rows:
                if r["is_plate"]:
                    L.append(
                        f"| {r['item']} | {r['name']} | {r['material']} | {r['qty']}×{mult} | {r['unit']} | {r['size']} | {r['t']} | {r['cls']} |"
                    )
                    all_plates.append({**r, "mult": mult, "drawing": rec["name"]})
            others = [
                f"{r['name']}({r['material']})" for r in rows if not r["is_plate"]
            ]
            if others:
                L.append(
                    f"비판재: {', '.join(others[:14])}{' …' if len(others) > 14 else ''}"
                )
            c = dim_candidates(t)
            L.append(f"\n치수 후보 — I.D/O.D/Ø: {c['id_od']}")
            L.append(f"용접선: {c['seams']}")
            L.append(f"헤드/콘/TL: {c['head_cone']}")
            L.append(f"큰 치수(오버라이드): {c['big_dims']}")
            L.append(f"숫자 텍스트: {c['num_texts']}")
        else:
            L.append(f"래스터 → 눈으로 읽을 것: {rec['pages'][0]}")
        L.append("")
    L.append(
        f"## 판재 합계: {len(all_plates)}행, 수량 {sum(r['qty'] * r['mult'] for r in all_plates)}개"
    )
    (d / "reading_sheet.md").write_text("\n".join(L), encoding="utf8")
    (d / "bom_plates.json").write_text(
        json.dumps(all_plates, ensure_ascii=False, indent=1), encoding="utf8"
    )
    print(f"written {d / 'reading_sheet.md'}  plates={len(all_plates)}")


if __name__ == "__main__":
    main()
