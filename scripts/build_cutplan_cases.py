"""
회사 담당자에게 받은 커팅플랜 폴더로 테스트셋을 만든다.

    PYTHONPATH=. uv run python scripts/build_cutplan_cases.py [--src <받은 폴더>] [--out <출력 폴더>]

기본값은 --src test_data/cutting_plan, --out test_data/cases 다 (cutplan_agent.config 의 TEST_DATA 기준).
받은 폴더 하나가 설비 하나다 (예: test_data/cutting_plan/S-2120/). 그 안에 설계 도면 dwg·pdf, 커팅플랜
CP.dwg (D-1203 은 백업 CP.bak 도), 워크오더 번호 한 줄을 적은 note.md 가 있다. 받은 폴더는 건드리지 않는다.

출력 (설비마다):
  <out>/<설비>/
    input_drawings/        설계 도면 dwg·pdf. 받은 그대로 복사
    output_cutting_plan/   CP.dwg (받은 그대로), CP.dxf (dwg2dxf 변환), CP.png (사람이 보는 그림),
                           qc.png (읽은 조각을 색으로 칠한 그림),
                           sheets.csv, parts.csv, pieces.csv (cutplan_agent/eval/cp_parse.py 가 읽은 정답)
    output_unfold/         조각마다 외곽 DXF (P<piece_id>.dxf, 좌하단을 원점으로 옮김). 목록은 pieces.csv
    source.csv             받은 파일마다 크기·sha256·역할. Data/dataset 의 같은 워크오더에 같은 이름 파일이
                           있으면 sha256 이 같은지 (old_dataset 열), 입력 DWG 를 이 환경에서 읽을 수
                           있는지 (readable 열)
    coverage.csv           정답 부품이 가리키는 설계 도면이 input_drawings 에 있는지
  <out>/index.csv          설비별 요약
  <out>/README.md

정답을 읽는 규칙과 한계는 cutplan_agent/eval/cp_parse.py 에 있다. 결과는 qc.png 로 확인한다.
CP.png 는 scripts/render_drawings.py 로 그린다. 한글 폰트가 없으면 한글이 네모로 나온다.
"""

import argparse
import csv
import hashlib
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf

from cutplan_agent.config import DATASET, DWG2DXF, PROJECT_ROOT, TEST_DATA
from cutplan_agent.eval.cp_parse import as_rows, read_cp, read_geometry
from cutplan_agent.eval.drawing_refs import find_drawings

DRAWING_EXTS = {".dwg", ".pdf"}
CP_NAMES = {"cp.dwg", "cp.bak"}
LINK_COLORS = {
    "label": "#2e7d32",
    "face": "#1565c0",
    "near": "#ef6c00",
    "copy": "#81c784",
    "row": "#81c784",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_csv(path: Path, rows, fields=None):
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def read_workorder(case_dir: Path) -> str:
    note = case_dir / "note.md"
    if not note.exists():
        return ""
    m = re.search(r"KD\d{5}", note.read_text(encoding="utf-8"))
    return m.group() if m else ""


def dwg_to_dxf(src: Path, dst: Path) -> str:
    """LibreDWG 로 DXF 를 만든다. 확장자가 .dwg 가 아니면 (CP.bak) 임시 이름으로 복사해 넘긴다.
    실패하면 이유를, 성공하면 빈 문자열을 돌려준다."""
    tmp = dst.with_suffix(".src.dwg")
    shutil.copyfile(src, tmp)
    try:
        r = subprocess.run(
            [str(DWG2DXF), "-y", "-o", str(dst), str(tmp)],
            capture_output=True,
            text=True,
        )
    finally:
        tmp.unlink(missing_ok=True)
    if r.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        return f"dwg2dxf 종료 코드 {r.returncode}"
    return ""


def dwg_readable(src: Path, work: Path) -> str:
    """입력 DWG 를 이 환경의 dwg2dxf + ezdxf 로 읽을 수 있는지. 에이전트가 DWG 를 입력으로 쓸 수 있는가."""
    tmp = work / "_readable.dxf"
    err = dwg_to_dxf(src, tmp)
    try:
        if err:
            return f"no: {err}"
        try:
            n = len(ezdxf.readfile(tmp).modelspace())
        except (ezdxf.DXFError, OSError) as e:
            return f"no: dwg2dxf 가 쓴 DXF 를 ezdxf 가 열지 못함 ({type(e).__name__})"
        return f"yes: 모델 공간 엔티티 {n}" if n else "no: 모델 공간이 비었다"
    finally:
        tmp.unlink(missing_ok=True)


def dxf_summary(path: Path) -> tuple:
    msp = ezdxf.readfile(path).modelspace()
    types = Counter(e.dxftype() for e in msp)
    texts = sorted(
        e.dxf.text if e.dxftype() == "TEXT" else e.text for e in msp.query("TEXT MTEXT")
    )
    return types, texts


def old_dataset_files(wo: str) -> dict:
    """Data/dataset 의 같은 워크오더 입력 도면과 커팅플랜. 파일 이름 -> 경로."""
    out = {}
    if not wo:
        return out
    for root in DATASET.glob(f"KDM/*/{wo}"):
        for p in root.rglob("*"):
            if p.is_file():
                out.setdefault(p.name, p)
    return out


def render_cp_png(dxf: Path, out_png: Path) -> None:
    tmp = out_png.parent / "_render"
    r = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "render_drawings.py"),
            str(dxf),
            "-o",
            str(tmp),
            "--format",
            "png",
            "--px",
            "4000",
            "--force",
        ],
        capture_output=True,
        text=True,
    )
    png = tmp / (dxf.stem + ".png")
    if r.returncode == 0 and png.exists():
        shutil.move(png, out_png)
    else:
        print(f"  주의: CP.png 를 그리지 못했다\n{r.stdout[-1000:]}{r.stderr[-1000:]}")
    shutil.rmtree(tmp, ignore_errors=True)


def render_qc(dxf: Path, cp, out_png: Path) -> None:
    """읽은 조각을 link 별 색으로 칠하고 부품 번호를 적는다. 빨간 테두리 = 부품에 묶이지 않은 조각."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _, lines = read_geometry(ezdxf.readfile(dxf).modelspace())
    xs = [b for p in cp.pieces for b in (p.bounds[0], p.bounds[2])]
    ys = [b for p in cp.pieces for b in (p.bounds[1], p.bounds[3])]
    for s in cp.sheets:
        if s.box:
            xs += [s.box[0], s.box[2]]
            ys += [s.box[1], s.box[3]]
    if not xs:
        return
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pad = 0.03 * max(x1 - x0, y1 - y0)
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
    aspect = (y1 - y0) / max(x1 - x0, 1e-9)
    fig = plt.figure(figsize=(20, max(4, 20 * aspect)), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    for ln in lines:
        lx, ly = ln.xy
        if max(lx) < x0 or min(lx) > x1 or max(ly) < y0 or min(ly) > y1:
            continue
        ax.plot(lx, ly, color="#9e9e9e", lw=0.3)
    for s in cp.sheets:
        if s.box:
            bx0, by0, bx1, by1 = s.box
            ax.plot([bx0, bx1, bx1, bx0, bx0], [by0, by0, by1, by1, by0], "k-", lw=0.8)
            ax.text(bx0, by1, f" S{s.sheet_id}", va="bottom", fontsize=7)
    fs = 6 if len(cp.pieces) < 80 else 4
    for p in cp.pieces:
        ex, ey = p.poly.exterior.xy
        if p.part_no is None:
            ax.plot(ex, ey, color="#d32f2f", lw=0.9)
            continue
        ax.fill(ex, ey, color=LINK_COLORS.get(p.link, "#bdbdbd"), alpha=0.45, lw=0)
        cx, cy = p.center
        ax.text(cx, cy, str(p.part_no), ha="center", va="center", fontsize=fs)
    fig.savefig(out_png)
    plt.close(fig)


def write_piece_dxfs(cp, out_dir: Path) -> None:
    """조각마다 바깥 외곽과 구멍을 닫힌 LWPOLYLINE 으로 쓴다. 곡선은 0.5 mm 오차로 편 점이다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {p.piece_id: p for p in cp.pieces}
    for p in cp.pieces:
        doc = ezdxf.new("R2010")
        doc.units = ezdxf.units.MM
        msp = doc.modelspace()
        bx, by = p.bounds[0], p.bounds[1]
        rings = [p.poly.exterior] + [
            by_id[h].poly.exterior for h in p.hole_ids if h in by_id
        ]
        for ring in rings:
            pts = [(x - bx, y - by) for x, y in ring.coords]
            msp.add_lwpolyline(pts, close=True)
        doc.saveas(out_dir / f"P{p.piece_id}.dxf")


def build_case(case_dir: Path, out_root: Path) -> dict:
    case = case_dir.name
    wo = read_workorder(case_dir)
    out = out_root / case
    if out.exists():
        shutil.rmtree(out)
    (out / "input_drawings").mkdir(parents=True)
    (out / "output_cutting_plan").mkdir()
    old = old_dataset_files(wo)

    sources = []
    for p in sorted(case_dir.iterdir()):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low in CP_NAMES:
            role = "answer" if low == "cp.dwg" else "answer_backup"
        elif p.suffix.lower() in DRAWING_EXTS:
            role = "input"
        elif low == "note.md":
            role = "note"
        else:
            role = "other"
        digest = sha256(p)
        o = old.get(p.name)
        sources.append(
            {
                "file": p.name,
                "role": role,
                "size": p.stat().st_size,
                "sha256": digest,
                "old_dataset": ("same" if sha256(o) == digest else "different")
                if o
                else "absent",
                "old_path": str(o.relative_to(DATASET)) if o else "",
                "readable": dwg_readable(p, out)
                if role == "input" and p.suffix.lower() == ".dwg"
                else "",
                "note": "",
            }
        )
        if role == "input":
            shutil.copy2(p, out / "input_drawings" / p.name)
        if role == "answer":
            shutil.copy2(p, out / "output_cutting_plan" / "CP.dwg")

    cpdir = out / "output_cutting_plan"
    dxf = cpdir / "CP.dxf"
    err = dwg_to_dxf(case_dir / "CP.dwg", dxf)
    if err:
        sys.exit(f"{case}: CP.dwg 를 DXF 로 바꾸지 못했다 ({err})")
    bak = next((s for s in sources if s["role"] == "answer_backup"), None)
    if bak:  # 백업이 본 파일과 같은 내용인지 (엔티티 종류별 수와 글자)
        tmp = cpdir / "_bak.dxf"
        err = dwg_to_dxf(case_dir / bak["file"], tmp)
        if err:
            bak["note"] = f"DXF 로 바꾸지 못함 ({err})"
        elif dxf_summary(tmp) == dxf_summary(dxf):
            bak["note"] = "CP.dwg 와 엔티티 수·글자가 같다"
        else:
            bak["note"] = "CP.dwg 와 내용이 다르다"
        tmp.unlink(missing_ok=True)
    write_csv(out / "source.csv", sources)

    tag = case if re.match(r"^[A-Z]+-\d", case) else ""
    cp = read_cp(str(dxf), tag=tag)
    rows = as_rows(cp)
    for k in ("sheets", "parts", "pieces"):
        write_csv(cpdir / f"{k}.csv", rows[k])
    write_piece_dxfs(cp, out / "output_unfold")
    render_cp_png(dxf, cpdir / "CP.png")
    render_qc(dxf, cp, cpdir / "qc.png")

    names = [p.name for p in (out / "input_drawings").iterdir()]
    by_ref = defaultdict(int)
    for p in cp.parts:
        if p.tag and p.dwg_no:
            by_ref[(p.tag, p.dwg_no)] += 1
    cov = []
    for (t, n), cnt in sorted(by_ref.items()):
        hits = find_drawings(t, n, names)
        cov.append(
            {
                "dwg_ref": f"{t}-{n:03d}",
                "parts": cnt,
                "found": "yes" if hits else "no",
                "files": " | ".join(sorted(hits)),
            }
        )
    write_csv(out / "coverage.csv", cov, ["dwg_ref", "parts", "found", "files"])

    outlines = Counter(p["outline"] for p in rows["parts"])
    return {
        "case": case,
        "workorder": wo,
        "layout": cp.layout,
        "input_files": sum(1 for s in sources if s["role"] == "input"),
        "sheets": len(rows["sheets"]),
        "parts": len(rows["parts"]),
        "pieces": len(rows["pieces"]),
        "pieces_unlinked": sum(1 for p in rows["pieces"] if not p["part_no"]),
        "parts_outline": " ".join(f"{k}={v}" for k, v in sorted(outlines.items())),
        "refs_missing": " ".join(c["dwg_ref"] for c in cov if c["found"] == "no"),
        "dwg_unreadable": sum(1 for s in sources if s["readable"].startswith("no")),
        "old_dataset_same": sum(1 for s in sources if s["old_dataset"] == "same"),
        "old_dataset_different": sum(
            1 for s in sources if s["old_dataset"] == "different"
        ),
    }


README = """# cases — 회사 담당자에게 받은 커팅플랜 테스트셋

`scripts/build_cutplan_cases.py` 가 `{src}` 의 받은 폴더로 만든다. 다시 만들면 이 폴더를 지우고 새로 쓴다.
받은 원본은 `{src}` 에 있고, 이 폴더에서 다시 만들 수 있다.

| 설비 | 워크오더 | 정답 형식 | 입력 파일 | 읽지 못하는 입력 DWG | 판재 | 부품 | 조각 | 부품에 안 묶인 조각 | 부품 외곽 | 입력에 없는 도면 |
|---|---|---|---|---|---|---|---|---|---|---|
{rows}

- 정답 형식 `nesting` 은 판재 배치도다. 판재 목록(sheets.csv)과 판 위 부품(parts.csv)을 비교할 수 있다.
- 정답 형식 `unfold_list` 는 판재 없이 부품 전개도만 모은 도면이다. 부품 목록·전개 크기(parts.csv 의
  size, w, h)와 조각 모양(pieces.csv, output_unfold/)을 비교할 수 있고, 판재 수·중량은 비교할 수 없다.
- 부품 외곽: label = 라벨이 조각 안에 있음, face = 선을 공유한 부품의 면, near = 라벨 옆 조각 (추정),
  none = 못 찾음. 규칙은 `cutplan_agent/eval/cp_parse.py`.
- 확인은 `output_cutting_plan/qc.png` 로 한다. 초록 = 라벨로 찾은 조각, 파랑 = face, 주황 = near,
  연두 = 같은 판의 같은 모양(copy)이나 같은 줄(row) 로 묶은 조각, 빨간 테두리 = 부품에 안 묶인 조각.
- `source.csv` 의 old_dataset: Data/dataset 의 같은 워크오더에 같은 이름 파일이 있으면 sha256 비교 결과
  (same / different), 없으면 absent. readable: 입력 DWG 를 이 환경의 dwg2dxf + ezdxf 로 읽을 수 있는지.
  읽지 못하는 DWG 는 같은 이름의 PDF 를 입력으로 쓴다.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--src", type=Path, default=TEST_DATA / "cutting_plan")
    ap.add_argument("--out", type=Path, default=TEST_DATA / "cases")
    a = ap.parse_args()
    cases = sorted(p for p in a.src.iterdir() if (p / "CP.dwg").exists())
    if not cases:
        sys.exit(f"CP.dwg 가 있는 폴더가 없다: {a.src}")
    a.out.mkdir(parents=True, exist_ok=True)
    summary = []
    for c in cases:
        print(f"[{c.name}]", flush=True)
        s = build_case(c, a.out)
        summary.append(s)
        print("  " + ", ".join(f"{k}={v}" for k, v in s.items() if k != "case"))
    write_csv(a.out / "index.csv", summary)
    rows = "\n".join(
        f"| {s['case']} | {s['workorder']} | {s['layout']} | {s['input_files']} | "
        f"{s['dwg_unreadable']} | "
        f"{s['sheets']} | {s['parts']} | {s['pieces']} | {s['pieces_unlinked']} | "
        f"{s['parts_outline']} | {s['refs_missing'] or '-'} |"
        for s in summary
    )
    src = os.path.relpath(a.src, a.out.parent.parent)
    (a.out / "README.md").write_text(
        README.format(src=src, rows=rows), encoding="utf-8"
    )
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
