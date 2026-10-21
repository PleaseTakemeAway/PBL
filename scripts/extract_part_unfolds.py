# -*- coding: utf-8 -*-
"""
커팅플랜 DXF에서 부품별 전개 외곽을 잘라내어 dataset/KDM/<year>/<wo>/unfold/ 에 개별 DXF로 저장.

좌표 규약 (nesting_dataset.json, 검증됨):
    sheet.origin = 판재 좌하단 모델좌표
    part 절대 bbox = origin + (rel_x, rel_y) ~ + (w, h)
부품 bbox 안에 완전히 들어오는 기하 엔티티만 취해 (0,0) 기준으로 평행이동해 저장한다.
parts.csv 의 n_ents 와 잘라낸 엔티티 수를 비교해 index.csv 에 기록 (불일치 = 이웃 부품 혼입 또는 누락).
quality == chain_path 판재는 부품 분리가 불가하므로 건너뛴다.

알려진 한계 (2026-10-01 점검):
  - parts.csv 의 w/h 는 곡선을 꼭짓점 기준으로 근사한 값이라 ARC 가 큰 부품은 실제 외곽보다 작게 잡혀 있음
    → 해당 부품은 ARC 가 잘려 나가고 match=diff/none 으로 표시됨. 평가에는 match=ok 행만 사용할 것.
  - 근본 해결은 닫힌 루프(연결성) 기반 재추출. TODO.
"""
import csv, json, os, re, sys, collections
import numpy as np
import ezdxf
from ezdxf import bbox
from ezdxf.math import Vec3

from cutplan_agent.config import DATA_DIR, DATASET

BASE = DATA_DIR
OUT = DATASET
YEAR_DIR = {"23": "2023년 cutting plan", "24": "2024년 cutting plan", "25": "2025년 cutting plan"}
GEOM = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE"}
EXCLUDE_LAYERS = {"부재번호"}   # 부재번호 풍선 원 등 주석용 레이어 (레이어 census 로 확인)
TOL = 1.0  # mm


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s))[:40] or "x"


def entity_boxes(msp):
    ents, boxes = [], []
    for e in msp:
        if e.dxftype() not in GEOM or e.dxf.layer in EXCLUDE_LAYERS:
            continue
        try:
            ex = bbox.extents([e], fast=True)
        except Exception:
            continue
        if not ex.has_data:
            continue
        ents.append(e)
        boxes.append((ex.extmin.x, ex.extmin.y, ex.extmax.x, ex.extmax.y))
    return ents, np.array(boxes, dtype=float).reshape(-1, 4)


def main():
    data = json.load(open(os.path.join(BASE, "_dataset", "nesting_dataset.json"), encoding="utf8"))
    by_drawing = collections.defaultdict(list)
    for sh in data:
        by_drawing[sh["drawing"]].append(sh)

    total_parts = total_written = mismatch = 0
    for drawing, sheets in by_drawing.items():
        yy = drawing[2:4]
        wo = re.match(r"(KD\d{5})", drawing).group(1)
        src = os.path.join(BASE, YEAR_DIR[yy], "images", "_dxf", drawing + ".dxf")
        out_dir = os.path.join(OUT, "KDM", "20" + yy, wo, "unfold")
        os.makedirs(out_dir, exist_ok=True)
        doc = ezdxf.readfile(src)
        msp = doc.modelspace()
        ents, boxes = entity_boxes(msp)
        index_rows = []
        for sh in sheets:
            if sh["quality"] == "chain_path":
                continue
            ox, oy = sh["origin"]
            for i, p in enumerate(sh["parts"]):
                total_parts += 1
                x0, y0 = ox + p["rel_x"], oy + p["rel_y"]
                x1, y1 = x0 + p["w"], y0 + p["h"]
                m = (boxes[:, 0] >= x0 - TOL) & (boxes[:, 1] >= y0 - TOL) & (boxes[:, 2] <= x1 + TOL) & (boxes[:, 3] <= y1 + TOL)
                # 판재 전체 크기의 엔티티(판 외곽선)는 제외
                m &= ~((boxes[:, 2] - boxes[:, 0] >= sh["sheet_w"] - TOL) & (boxes[:, 3] - boxes[:, 1] >= sh["sheet_h"] - TOL))
                idx = np.nonzero(m)[0]
                if len(idx) == 0:
                    index_rows.append({**_row(drawing, sh, i, p), "file": "", "n_ents_cut": 0, "match": "none"})
                    continue
                new = ezdxf.new("R2010")
                nmsp = new.modelspace()
                new.layers.add("BLANK")
                for k in idx:
                    e = ents[k].copy()
                    e.translate(-x0, -y0, 0)
                    e.dxf.layer = "BLANK"
                    nmsp.add_entity(e)
                fname = f"{safe_name(drawing)}_S{sh['sheet_id']:02d}_P{i:03d}_{safe_name(p['label'])}.dxf"
                new.saveas(os.path.join(out_dir, fname))
                total_written += 1
                ok = (len(idx) == p["n_ents"])
                mismatch += (not ok)
                index_rows.append({**_row(drawing, sh, i, p), "file": fname, "n_ents_cut": len(idx), "match": "ok" if ok else "diff"})
        # index.csv 는 워크오더 단위로 누적
        idx_path = os.path.join(out_dir, "index.csv")
        old = []
        if os.path.exists(idx_path):
            with open(idx_path, encoding="utf-8-sig", newline="") as f:
                old = [r for r in csv.DictReader(f) if r["drawing"] != drawing]
        rows = old + index_rows
        if rows:
            with open(idx_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
        print(f"{drawing:45s} sheets={len(sheets):3d} parts={sum(len(s['parts']) for s in sheets):5d} written={sum(1 for r in index_rows if r['file']):5d}")
    print(f"\nparts={total_parts} written={total_written} n_ents mismatch={mismatch} ({mismatch/max(total_written,1):.1%})")


def _row(drawing, sh, i, p):
    tag = p.get("tag") or {}
    return {
        "drawing": drawing, "sheet_id": sh["sheet_id"], "quality": sh["quality"],
        "material": sh["material"], "thickness": sh["thickness"],
        "part_idx": i, "label": p["label"], "w": p["w"], "h": p["h"],
        "rel_x": p["rel_x"], "rel_y": p["rel_y"], "n_ents": p["n_ents"], "holes": p["holes"],
        "tag_name": tag.get("name", ""), "tag_material": tag.get("material", ""),
        "tag_thickness": tag.get("thickness", ""), "tag_size": tag.get("size", ""),
        "tag_qty": tag.get("qty", ""), "tag_dwg_no": tag.get("dwg_no", ""),
    }


if __name__ == "__main__":
    main()
