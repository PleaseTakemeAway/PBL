# -*- coding: utf-8 -*-
"""
도면 페이지를 고해상도 타일로 잘라 사람이 읽을 수 있게 한다.

    uv run python -m cutplan_agent.eval.tiles --job KD23022_manual [--only "GENERAL,BELLOWS"] [--rows 2 --cols 3] [--px 6000]

출력: runs/<job>/tiles/<도면stem>_r{i}c{j}.png, <stem>_bom.png (우측 BOM 영역), <stem>_full.png (고해상 전체)
벡터(DXF)는 ezdxf 로 px 해상도로 다시 렌더, 래스터(PDF)는 300dpi 로 렌더.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from cutplan_agent.config import RUNS_DIR
from cutplan_agent.skills.l1_perception import _render_dxf


def page_image(rec: dict, px: int, out_dir: Path):
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    stem = re.sub(r"[^A-Za-z0-9가-힣_.-]+", "_", Path(rec["name"]).stem)[:60]
    if len(rec.get("pages", [])) > 1:
        stem = f"{stem}_p{rec.get('page', 0) + 1:02d}"  # 다중 페이지 PDF 는 페이지별로 캐시
    full = out_dir / f"{stem}_full.png"
    if full.exists():
        return Image.open(full), stem
    if rec.get("dxf_text"):
        dxf = (
            Path(rec["dxf_text"]).parent.parent
            / "dxf"
            / (Path(rec["name"]).stem + ".dxf")
        )
        if not dxf.exists():
            dxf = (
                Path(rec["path"])
                if rec.get("path", "").lower().endswith(".dxf")
                else dxf
            )
        _render_dxf(dxf, full, px)
    else:
        import pymupdf

        src = Path(rec["path"]) if rec.get("path") else None
        if src and src.suffix.lower() == ".pdf":
            doc = pymupdf.open(str(src))
            pg = doc[rec.get("page", 0)]
            long_pt = max(pg.rect.width, pg.rect.height) / 72.0
            pg.get_pixmap(dpi=int(px / long_pt)).save(str(full))
        else:
            Image.open(rec["pages"][0]).save(full)
    return Image.open(full), stem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--rows", type=int, default=2)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--px", type=int, default=6000)
    a = ap.parse_args()
    d = RUNS_DIR / a.job
    ing = json.loads((d / "ingest.json").read_text(encoding="utf8"))
    st = json.loads((d / "state.json").read_text(encoding="utf8"))
    paths = {x["name"]: x["path"] for x in st["drawings"]}
    out = d / "tiles"
    out.mkdir(exist_ok=True)
    keys = [k.strip().upper() for k in a.only.split(",") if k.strip()]
    for rec in ing:
        if keys and not any(k in rec["name"].upper() for k in keys):
            continue
        rec["path"] = paths.get(rec["name"], "")
        pages = rec["pages"] if not rec.get("dxf_text") else rec["pages"][:1]
        for pi, _ in enumerate(pages):
            rec["page"] = pi
            img, stem = page_image(rec, a.px, out)
            W, H = img.size
            ov = 0.06
            for i in range(a.rows):
                for j in range(a.cols):
                    x0 = int(max(0, (j / a.cols - ov) * W))
                    x1 = int(min(W, ((j + 1) / a.cols + ov) * W))
                    y0 = int(max(0, (i / a.rows - ov) * H))
                    y1 = int(min(H, ((i + 1) / a.rows + ov) * H))
                    img.crop((x0, y0, x1, y1)).save(out / f"{stem}_r{i}c{j}.png")
            img.crop(
                (int(W * 0.72), int(H * 0.30), int(W * 0.985), int(H * 0.78))
            ).save(out / f"{stem}_bom.png")
            print(f"{stem}: {W}x{H} → {a.rows}x{a.cols} tiles + bom")


if __name__ == "__main__":
    main()
