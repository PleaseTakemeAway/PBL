# -*- coding: utf-8 -*-
"""
test_data/README.html 생성 — 단일 파일(썸네일 base64 내장), 브라우저에서 바로 열림.

    PYTHONPATH=. uv run python scripts/build_test_data_html.py

내용: KPI 타일 → 파이프라인 → 연도·등급 분포 → 워크오더 표(정렬·필터·행 펼침: 도면/커팅플랜 썸네일, 도면 목록, 판재 그룹)
      → 폴더 구조 → 사용법 → 제외 목록
데이터가 바뀌면 build_test_data.py 다음에 다시 실행.
"""

import base64
import collections
import csv
import io
import json
import re
from pathlib import Path

from cutplan_agent.config import TEST_DATA

ROOT = TEST_DATA
OUT = ROOT / "README.html"
THUMB_LONG = 640
DENSITY = 7.85e-6


def jpeg_b64(img, quality=72) -> str:
    from PIL import Image

    img = img.convert("RGB")
    w, h = img.size
    s = THUMB_LONG / max(w, h)
    if s < 1:
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def pdf_thumb(pdf: Path) -> str:
    import pymupdf
    from PIL import Image

    doc = pymupdf.open(str(pdf))
    pg = doc[0]
    long_pt = max(pg.rect.width, pg.rect.height)
    pix = pg.get_pixmap(dpi=max(36, int(THUMB_LONG / (long_pt / 72))))
    return jpeg_b64(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))


def png_thumb(png: Path) -> str:
    """커팅플랜 PNG 는 여백이 커서 흰 테두리를 잘라낸 뒤 축소한다."""
    from PIL import Image, ImageChops

    img = Image.open(png).convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bbox = ImageChops.difference(img, bg).getbbox()
    if bbox:
        pad = 20
        img = img.crop(
            (
                max(0, bbox[0] - pad),
                max(0, bbox[1] - pad),
                min(img.width, bbox[2] + pad),
                min(img.height, bbox[3] + pad),
            )
        )
    return jpeg_b64(img)


def pick_drawing(files):
    pdfs = [f for f in files if f.suffix.lower() == ".pdf"]
    for key in ("BODY", "GENERAL", "GA-", "_GA", "ASSEMBLY"):
        for f in pdfs:
            if key in f.name.upper():
                return f
    return pdfs[0] if pdfs else None


def sheet_groups(csv_path: Path):
    if not csv_path.exists():
        return [], 0.0, 0
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    g = collections.OrderedDict()
    kg = 0.0
    n = 0
    for r in rows:
        try:
            t = float(r["thickness"])
            w = float(r["sheet_w"])
            h = float(r["sheet_h"])
            q = int(float(r["sheet_qty"] or 1))
        except Exception:
            continue
        key = f"{r['material'] or '재질없음'} t{t:g}"
        g[key] = g.get(key, 0) + q
        n += q
        kg += t * w * h * q * DENSITY
    top = sorted(g.items(), key=lambda kv: -kv[1])[:4]
    return [f"{k} ×{v}" for k, v in top], round(kg), n


def main():
    idx = list(csv.DictReader(open(ROOT / "index.csv", encoding="utf-8-sig")))
    data, excluded = [], []
    for r in idx:
        if r["included"] != "yes":
            excluded.append(
                {"wo": r["workorder"], "reason": r["reason"], "year": r["year"]}
            )
            continue
        wo = r["workorder"]
        d = ROOT / wo
        dfiles = sorted(p for p in (d / "input_drawings").rglob("*") if p.is_file())
        dpick = pick_drawing(dfiles)
        cps = sorted((d / "output_cutting_plan").glob("*.png"))
        groups, kg, _ = sheet_groups(d / "output_cutting_plan" / "sheets.csv")
        if wo.startswith("HCE"):
            groups, kg = ["St37-40 t4 ×1"], round(4 * 2438 * 1219 * DENSITY)
        try:
            dthumb = pdf_thumb(dpick) if dpick else ""
        except Exception:
            dthumb = ""
        try:
            cthumb = png_thumb(cps[0]) if cps else ""
        except Exception:
            cthumb = ""
        grade = r["grade"]
        gclass = (
            "mixed"
            if "/" in grade
            else {"성공": "good", "부분": "warn", "실패": "bad"}.get(grade, "mixed")
        )
        data.append(
            {
                "wo": wo,
                "year": r["year"],
                "customer": re.sub(r"^KD\d{5}(-\d)?\s*-?\s*", "", r["customer"]).strip()
                or r["customer"],
                "grade": grade,
                "gclass": gclass,
                "n_dwg": int(r["input_drawings"] or 0),
                "n_dwgfile": sum(1 for f in dfiles if f.suffix.lower() == ".dwg"),
                "n_pdf": sum(1 for f in dfiles if f.suffix.lower() == ".pdf"),
                "n_unfold": int(r["unfold_dxf"] or 0),
                "n_ok": int(r["unfold_match_ok"] or 0)
                if r["unfold_match_ok"]
                else None,
                "gt_sheets": int(float(r["gt_sheets"] or 0)),
                "gt_ok": int(float(r["gt_sheets_ok"] or 0)),
                "kg": kg,
                "groups": groups,
                "drawings": [
                    p.relative_to(d / "input_drawings").as_posix() for p in dfiles
                ][:60],
                "dthumb": dthumb,
                "cthumb": cthumb,
                "dname": dpick.name if dpick else "",
                "cname": cps[0].name if cps else "",
            }
        )
    tot = {
        "wo": len(data),
        "dwg": sum(x["n_dwg"] for x in data),
        "unfold": sum(x["n_unfold"] for x in data),
        "ok": sum(x["n_ok"] or 0 for x in data),
        "sheets": sum(x["gt_sheets"] for x in data),
        "kg": sum(x["kg"] for x in data),
        "excluded": len(excluded),
    }
    by_year = collections.OrderedDict()
    for x in data:
        by_year.setdefault(x["year"], collections.Counter())[x["gclass"]] += 1

    html = (
        TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__EXCL__", json.dumps(excluded, ensure_ascii=False))
        .replace("__TOT__", json.dumps(tot, ensure_ascii=False))
        .replace(
            "__BYYEAR__",
            json.dumps({k: dict(v) for k, v in by_year.items()}, ensure_ascii=False),
        )
    )
    OUT.write_text(html, encoding="utf8")
    print(
        f"written {OUT}  {OUT.stat().st_size / 1e6:.1f} MB  workorders={len(data)} excluded={len(excluded)}"
    )


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>KDM 커팅플랜 테스트 데이터셋</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* 레이아웃: 좌우 20px 거터의 단일 열. 요약(타일) → 파이프라인 → 분포 → 표 → 참고. 표만 가로 스크롤 허용. */
:root{
  --bg:#f5f6f8; --surface:#ffffff; --surface-2:#eceff3; --line:#d5dae2; --fg:#15202b; --fg-2:#4a5664; --fg-3:#7a8694;
  --accent:#1f5f8b; --accent-soft:#dbe8f3; --accent-ink:#ffffff;
  --good:#0ca30c; --warn:#fab219; --bad:#d03b3b; --mixed:#8a93a0;
  --seq-1:#cde2fb; --seq-2:#86b6ef; --seq-3:#3987e5; --seq-4:#1c5cab;
  --font:"IBM Plex Sans KR","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;
  --mono:"IBM Plex Mono","Consolas","D2Coding",monospace;
  --radius:6px; --shadow:0 1px 2px rgba(21,32,43,.06),0 4px 14px rgba(21,32,43,.05);
  color-scheme:light;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#141a21; --surface:#1b232c; --surface-2:#232d38; --line:#2f3b48; --fg:#e8edf2; --fg-2:#b4bfcb; --fg-3:#8392a2;
  --accent:#5fa3d6; --accent-soft:#1f3447; --accent-ink:#0f1a24; --mixed:#8a93a0;
  --seq-1:#1c3a5c; --seq-2:#1c5cab; --seq-3:#3987e5; --seq-4:#86b6ef; --shadow:none; color-scheme:dark; } }
:root[data-theme="dark"]{
  --bg:#141a21; --surface:#1b232c; --surface-2:#232d38; --line:#2f3b48; --fg:#e8edf2; --fg-2:#b4bfcb; --fg-3:#8392a2;
  --accent:#5fa3d6; --accent-soft:#1f3447; --accent-ink:#0f1a24; --mixed:#8a93a0;
  --seq-1:#1c3a5c; --seq-2:#1c5cab; --seq-3:#3987e5; --seq-4:#86b6ef; --shadow:none; color-scheme:dark; }
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--fg);font-family:var(--font);font-size:15px;line-height:1.55;padding-block:28px 60px;padding-inline:20px}
.wrap{max-width:1240px;margin:0 auto;display:grid;gap:34px}
h1{font-size:clamp(24px,3.2vw,34px);line-height:1.2;margin:0 0 6px;font-weight:700;text-wrap:balance;letter-spacing:-.01em}
h2{font-size:18px;margin:0 0 12px;font-weight:600;letter-spacing:-.005em}
h3{font-size:15px;margin:0 0 6px;font-weight:600}
p{margin:0;max-width:72ch}
.lead{color:var(--fg-2);max-width:78ch}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--fg-3);font-weight:600;margin-bottom:6px}
.mono{font-family:var(--mono);font-size:.92em}
code{font-family:var(--mono);font-size:.9em;background:var(--surface-2);padding:1px 5px;border-radius:4px}
a{color:var(--accent)}
/* KPI */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow)}
.tile .l{font-size:12.5px;color:var(--fg-3);margin-bottom:4px}
.tile .v{font-size:30px;font-weight:600;line-height:1.1;letter-spacing:-.02em}
.tile .s{font-size:12.5px;color:var(--fg-2);margin-top:6px}
.tile.hero .v{color:var(--accent);font-size:42px}
/* 파이프라인 */
.pipe{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:16px;overflow-x:auto}
.pipe svg{display:block;min-width:720px;width:100%;height:auto}
.pipe text{font-family:var(--font);fill:var(--fg)}
.pipe .sub{fill:var(--fg-3);font-size:11.5px;font-family:var(--mono)}
.pipe .box{fill:var(--surface-2);stroke:var(--line)}
.pipe .box.out{fill:var(--accent-soft);stroke:var(--accent)}
.pipe .arrow{stroke:var(--fg-3);fill:none;stroke-width:1.6}
.pipe .ah{fill:var(--fg-3)}
/* 두 열 */
.two{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:18px}
@media (max-width:820px){.two{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;min-width:0}
/* 차트 */
.chart{width:100%;height:auto;display:block}
.chart text{font-family:var(--font);font-size:12px;fill:var(--fg-2)}
.chart .lbl{fill:var(--fg);font-weight:500}
.chart .grid{stroke:var(--line);stroke-width:1}
.legend{display:flex;flex-wrap:wrap;gap:12px 18px;font-size:12.5px;color:var(--fg-2);margin-top:8px}
.legend span i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
ol.prio{margin:8px 0 0;padding-left:20px;color:var(--fg-2)}
ol.prio li{margin:4px 0}
/* 표 */
.toolbar{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center;margin-bottom:10px}
.toolbar input,.toolbar select{font:inherit;font-size:14px;padding:6px 9px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);color:var(--fg)}
.toolbar input{min-width:200px}
.toolbar .count{margin-left:auto;color:var(--fg-3);font-size:13px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}
table{border-collapse:collapse;width:100%;min-width:900px;font-size:14px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle;white-space:nowrap}
th{font-size:12.5px;color:var(--fg-3);font-weight:600;background:var(--surface-2);cursor:pointer;user-select:none;position:sticky;top:0}
th .dir{color:var(--accent);margin-left:4px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.row{cursor:pointer}
tr.row:hover td{background:var(--surface-2)}
tr.row.open td{background:var(--accent-soft)}
tr.detail td{white-space:normal;background:var(--surface);padding:14px 16px 18px}
tr.detail[hidden]{display:none}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--surface-2);color:var(--fg-2)}
.pill i{width:8px;height:8px;border-radius:50%;display:inline-block}
.pill.good i{background:var(--good)} .pill.warn i{background:var(--warn)} .pill.bad i{background:var(--bad)} .pill.mixed i{background:var(--mixed)}
.bar{display:inline-block;height:9px;border-radius:2px;background:var(--seq-3);vertical-align:middle;margin-right:8px}
.bar.t{background:var(--seq-1)}
.cust{color:var(--fg-2);max-width:260px;overflow:hidden;text-overflow:ellipsis}
.detail-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,.9fr);gap:16px}
@media (max-width:900px){.detail-grid{grid-template-columns:1fr}}
.thumb{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--radius);padding:8px}
.thumb img{width:100%;height:auto;display:block;border-radius:3px;background:#fff}
.thumb .cap{font-size:12px;color:var(--fg-3);margin-top:6px;font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.flist{font-family:var(--mono);font-size:12px;color:var(--fg-2);max-height:220px;overflow:auto;margin:6px 0 0;padding-left:0;list-style:none}
.flist li{padding:2px 0;border-bottom:1px dashed var(--line);white-space:normal;word-break:break-all}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13.5px;margin-top:6px}
.kv b{color:var(--fg-3);font-weight:500}
/* 구조 / 사용법 */
pre{font-family:var(--mono);font-size:13px;line-height:1.6;background:var(--surface-2);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;overflow-x:auto;margin:0}
pre .c{color:var(--fg-3)}
ul.notes{margin:8px 0 0;padding-left:20px;color:var(--fg-2)}
ul.notes li{margin:5px 0;max-width:80ch}
.excl{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px 14px;font-size:13.5px;margin-top:8px}
.excl div{display:flex;gap:8px;align-items:baseline;min-width:0}
.excl b{font-family:var(--mono);font-weight:500;flex:0 0 auto}
.excl span{color:var(--fg-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
footer{color:var(--fg-3);font-size:12.5px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:no-preference){tr.row td{transition:background .15s}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="eyebrow">노바투스 PBL 3팀 · 케이디엠텍 압력용기 판재</div>
  <h1>KDM 커팅플랜 테스트 데이터셋</h1>
  <p class="lead">워크오더 하나가 <b>입력 도면 → 전개도 → 커팅플랜</b> 한 세트다. 설계도면(DWG·PDF)을 넣으면 판재 부품의 전개 외곽과
  판재별 배치(커팅플랜), 구매요구서(POR)의 판재 목록이 나와야 한다. 이 페이지는 <code>test_data/</code> 폴더의 목록이고, 행을 누르면 도면과 커팅플랜 썸네일이 열린다.</p>
</header>

<section>
  <div class="tiles" id="tiles"></div>
</section>

<section>
  <h2>파이프라인과 폴더의 대응</h2>
  <div class="pipe">
    <svg viewBox="0 0 980 150" role="img" aria-label="입력 도면에서 전개도, 커팅플랜, 구매요구서로 이어지는 파이프라인">
      <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ah"/></marker></defs>
      <g transform="translate(10,22)">
        <rect class="box" x="0" y="0" width="210" height="96" rx="6"/>
        <text x="16" y="30" font-size="15" font-weight="600">① 입력 도면</text>
        <text x="16" y="52" font-size="12.5">GA · Detail of body · nozzle · saddle</text>
        <text x="16" y="72" class="sub">input_drawings/  *.dwg *.pdf</text>
      </g>
      <path class="arrow" d="M225,70 L262,70" marker-end="url(#ah)"/>
      <g transform="translate(268,22)">
        <rect class="box out" x="0" y="0" width="210" height="96" rx="6"/>
        <text x="16" y="30" font-size="15" font-weight="600">② 전개도 (출력)</text>
        <text x="16" y="52" font-size="12.5">판재 부품별 평판 외곽 DXF</text>
        <text x="16" y="72" class="sub">output_unfold/  + index.csv</text>
      </g>
      <path class="arrow" d="M483,70 L520,70" marker-end="url(#ah)"/>
      <g transform="translate(526,22)">
        <rect class="box out" x="0" y="0" width="210" height="96" rx="6"/>
        <text x="16" y="30" font-size="15" font-weight="600">③ 커팅플랜 (출력)</text>
        <text x="16" y="52" font-size="12.5">재질·두께별 판재 + 배치 좌표</text>
        <text x="16" y="72" class="sub">output_cutting_plan/  *_CP.dwg</text>
      </g>
      <path class="arrow" d="M741,70 L778,70" marker-end="url(#ah)"/>
      <g transform="translate(784,22)">
        <rect class="box" x="0" y="0" width="186" height="96" rx="6" stroke-dasharray="5 4"/>
        <text x="16" y="30" font-size="15" font-weight="600">④ POR 판재 행</text>
        <text x="16" y="52" font-size="12.5">t × W × L · SH'T · kg</text>
        <text x="16" y="72" class="sub">sheets.csv 에서 산출</text>
      </g>
      <text x="10" y="140" class="sub">전개도와 커팅플랜은 KDM 설계자가 그린 실제 CP 도면에서 추출한 정답. 중량 = t × W × L × 7.85e-6 kg</text>
    </svg>
  </div>
</section>

<section class="two">
  <div class="card">
    <h2>연도별 워크오더와 추출 품질</h2>
    <svg id="yearChart" class="chart" viewBox="0 0 520 190" role="img" aria-label="연도별 워크오더 수, 등급별 적층 막대"></svg>
    <div class="legend">
      <span><i style="background:var(--good)"></i>성공 · 판재 대부분 정상 추출</span>
      <span><i style="background:var(--warn)"></i>부분 · 일부 판재 미분리</span>
      <span><i style="background:var(--bad)"></i>실패</span>
      <span><i style="background:var(--mixed)"></i>혼합 · CP 도면이 여러 장</span>
    </div>
  </div>
  <div class="card">
    <h2>어떤 워크오더부터 쓸까</h2>
    <p class="lead">정답(커팅플랜 추출) 품질이 좋은 것부터. 등급은 scorecard 의 판재 추출 성공률이다.</p>
    <ol class="prio">
      <li><b>성공 등급 + 정답 판재가 많은 것</b>: KD23002, KD23022, KD24043, KD25003 …</li>
      <li>전개도는 <code>output_unfold/index.csv</code> 의 <code>match=ok</code> 행만 평가에 쓴다. diff 는 이웃 부품 혼입이나 ARC 누락 가능성.</li>
      <li><code>sheets.csv</code> 의 <code>quality=chain_path</code> 판재는 부품 분리가 안 된 것이라 네스팅 평가에서 제외.</li>
      <li>HCE 샘플은 판금(굽힘 전개) 도메인. 압력용기와 공식이 다르니 섞어 평가하지 않는다.</li>
    </ol>
  </div>
</section>

<section>
  <h2>워크오더 목록</h2>
  <div class="toolbar">
    <input id="q" type="search" placeholder="워크오더 · 고객 검색" aria-label="검색">
    <select id="fy" aria-label="연도"><option value="">전체 연도</option></select>
    <select id="fg" aria-label="등급"><option value="">전체 등급</option><option value="good">성공</option><option value="warn">부분</option><option value="bad">실패</option><option value="mixed">혼합</option></select>
    <span class="count" id="count"></span>
  </div>
  <div class="tablewrap">
    <table id="tbl">
      <thead><tr>
        <th data-k="wo">워크오더</th><th data-k="customer">고객 · 기기</th><th data-k="gclass">등급</th>
        <th class="num" data-k="n_dwg">입력 도면</th><th class="num" data-k="n_unfold">전개도 DXF</th><th class="num" data-k="n_ok">match ok</th>
        <th class="num" data-k="gt_sheets">정답 판재</th><th class="num" data-k="kg">판재 중량 kg</th><th data-k="groups">주요 재질·두께</th>
      </tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
</section>

<section class="two">
  <div class="card">
    <h2>폴더 구조</h2>
<pre>test_data/
├─ README.html / index.csv
├─ KD23002/                        <span class="c">← 워크오더 (SK에너지 열교환기)</span>
│  ├─ input_drawings/              <span class="c">설계도면. dwg 는 벡터(치수·텍스트 추출 가능), pdf 는 이미지(VLM 입력)</span>
│  │   VP-DS-E1593AB-DWG-001_R2_General assembly.dwg
│  │   VP-DS-E1593AB-DWG-002_R1_Detail of body.pdf   …
│  ├─ output_unfold/               <span class="c">부품별 전개 외곽 DXF, 좌하단 원점, 레이어 BLANK</span>
│  │   index.csv                   <span class="c">sheet_id · label · w · h · holes · tag_* · match</span>
│  │   KD23002_CP_S02_P000_…SHELL….dxf  …
│  └─ output_cutting_plan/
│      KD23002_CP.dwg / .dxf / .png <span class="c">KDM 설계자가 그린 커팅플랜 원본</span>
│      sheets.csv                  <span class="c">판재 규격·수량·라벨 ("SA516-70 12t x 2990 x 5650 - 2 SH'T")</span>
│      parts.csv                   <span class="c">판 위 부품 배치 (rel_x, rel_y, w, h)</span>
│      part_tags.csv               <span class="c">부품표 (dwg_no, part_name, material, t, size, qty)</span>
├─ KD23079/input_drawings/동은/, 신우/   <span class="c">협력사별 하위폴더 유지</span>
└─ HCE_76K3-40022/                 <span class="c">판금 샘플: 스캔 PDF + 정답 전개 DXF 5개 + TruTops TAF</span></pre>
  </div>
  <div class="card">
    <h2>사용법과 주의</h2>
    <ul class="notes">
      <li><b>다시 만들기</b>: Drive zip 나머지 파트를 <code>Data/drive/8. Data/</code> 에 풀고 <code>PYTHONPATH=. uv run python scripts/ingest_drive_inputs.py</code> → <code>PYTHONPATH=. uv run python scripts/build_test_data.py</code> → <code>PYTHONPATH=. uv run python scripts/build_test_data_html.py</code>.</li>
      <li><b>원본</b>은 <code>Data\dataset\</code>. 여기는 그 중 3종이 모두 있는 워크오더의 복사본이다. 강도계산서·POR PDF 는 원본의 <code>input/calculation</code>, <code>input/por</code> 에 있다.</li>
      <li><b>전개 공식</b>: 쉘 L = π(ID+t) (KDM 태그 44건 역산). 헤드 블랭크 ≈ 1.25×ID 는 경험계수. 콘은 중립면 기준 부채꼴.</li>
      <li><b>정답의 한계</b>: parts.csv 의 부품 bbox 는 곡선을 꼭짓점 기준으로 근사해 ARC 가 큰 부품은 작게 잡혀 있다. 풍선 원(부재번호)이 부품으로 잡힌 행은 none 으로 자동 제외됨.</li>
      <li><b>평가 지표</b>: 전개도 외곽 IoU · W/H 오차 · 구멍 수, 네스팅 판 수 · gross 중량 비율 · 활용률, POR 행 일치. 에이전트 코드는 <code>cutplan_agent/</code>.</li>
    </ul>
  </div>
</section>

<section>
  <h2>제외된 워크오더 <span id="exclN" class="mono" style="color:var(--fg-3);font-weight:400"></span></h2>
  <p class="lead">3종 중 하나라도 없는 것. 입력 도면이 없는 것은 Drive zip 파트가 더 풀리면 자동으로 들어온다.</p>
  <div class="excl" id="excl"></div>
</section>

<footer>생성: scripts/build_test_data_html.py · 원본 데이터: 케이디엠텍 2023~2025 커팅플랜 + 기술부 도면 (대외비) · 현대건설기계 76K3-40022</footer>
</div>

<script>
const DATA = __DATA__;
const EXCL = __EXCL__;
const TOT = __TOT__;
const BYYEAR = __BYYEAR__;
const fmt = n => n.toLocaleString('ko-KR');
const GL = {good:'성공', warn:'부분', bad:'실패', mixed:'혼합'};

// KPI
document.getElementById('tiles').innerHTML = [
  ['워크오더', fmt(TOT.wo), '입력·전개도·커팅플랜 3종 완비', 'hero'],
  ['입력 도면', fmt(TOT.dwg), 'dwg + pdf 파일'],
  ['전개도 DXF', fmt(TOT.unfold), 'match ok ' + fmt(TOT.ok) + '개 (' + Math.round(100*TOT.ok/Math.max(TOT.unfold,1)) + '%)'],
  ['정답 판재', fmt(TOT.sheets) + '장', '커팅플랜의 판재 수량 합'],
  ['판재 중량', (TOT.kg/1000).toFixed(1) + ' t', 't × W × L × 7.85e-6'],
  ['제외', fmt(TOT.excluded), '도면 또는 커팅플랜 없음'],
].map(([l,v,s,c]) => `<div class="tile ${c||''}"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join('');

// 연도 차트 (적층 막대, 등급 = 상태색)
(function(){
  const svg = document.getElementById('yearChart');
  const years = Object.keys(BYYEAR).sort();
  const order = ['good','warn','bad','mixed'];
  const col = {good:'var(--good)', warn:'var(--warn)', bad:'var(--bad)', mixed:'var(--mixed)'};
  const max = Math.max(...years.map(y => order.reduce((a,k)=>a+(BYYEAR[y][k]||0),0)));
  const W=520,H=190,L=40,R=16,T=16,B=34, pw=W-L-R, ph=H-T-B;
  const step = max<=10?2:5; const top = Math.ceil(max/step)*step;
  let s='';
  for(let v=0; v<=top; v+=step){ const y=T+ph-ph*v/top; s+=`<line class="grid" x1="${L}" x2="${W-R}" y1="${y}" y2="${y}"/><text x="${L-8}" y="${y+4}" text-anchor="end">${v}</text>`; }
  const bw = Math.min(70, pw/years.length*0.5);
  years.forEach((y,i)=>{
    const cx = L + pw*(i+0.5)/years.length; let acc=0;
    order.forEach(k=>{ const v=BYYEAR[y][k]||0; if(!v) return;
      const y1=T+ph-ph*(acc+v)/top, hh=ph*v/top-2;
      s+=`<rect x="${cx-bw/2}" y="${y1}" width="${bw}" height="${Math.max(hh,0)}" rx="2" fill="${col[k]}"><title>${y} ${GL[k]} ${v}</title></rect>`;
      if(hh>14) s+=`<text x="${cx}" y="${y1+hh/2+4}" text-anchor="middle" fill="#fff" style="fill:#fff;font-weight:600">${v}</text>`;
      acc+=v; });
    s+=`<text class="lbl" x="${cx}" y="${H-12}" text-anchor="middle">${y}년 · ${acc}</text>`;
  });
  svg.innerHTML = s;
})();

// 표
const tb=document.getElementById('tb'), q=document.getElementById('q'), fy=document.getElementById('fy'), fg=document.getElementById('fg');
[...new Set(DATA.map(d=>d.year))].sort().forEach(y=>fy.insertAdjacentHTML('beforeend',`<option value="${y}">${y}</option>`));
let sortK='gt_sheets', sortDir=-1, openWo=null;
const maxSheets = Math.max(...DATA.map(d=>d.gt_sheets));
function rows(){
  const t=q.value.trim().toLowerCase();
  return DATA.filter(d=>(!t||(d.wo+' '+d.customer).toLowerCase().includes(t))&&(!fy.value||d.year===fy.value)&&(!fg.value||d.gclass===fg.value))
    .sort((a,b)=>{ let x=a[sortK],y=b[sortK]; if(Array.isArray(x)){x=x.join();y=y.join();} if(x==null)x=-1; if(y==null)y=-1;
      return (x>y?1:x<y?-1:0)*sortDir || a.wo.localeCompare(b.wo); });
}
function render(){
  const rs=rows();
  document.getElementById('count').textContent = rs.length+' / '+DATA.length+' 워크오더';
  document.querySelectorAll('th').forEach(th=>{ th.innerHTML = th.textContent.replace(/[▲▼]/g,'').trim() + (th.dataset.k===sortK?`<span class="dir">${sortDir>0?'▲':'▼'}</span>`:''); });
  tb.innerHTML = rs.map(d=>`
    <tr class="row ${d.wo===openWo?'open':''}" data-wo="${d.wo}" tabindex="0">
      <td class="mono"><b>${d.wo}</b></td>
      <td class="cust" title="${d.customer}">${d.customer}</td>
      <td><span class="pill ${d.gclass}"><i></i>${d.grade}</span></td>
      <td class="num">${d.n_dwg} <span style="color:var(--fg-3);font-size:12px">(dwg ${d.n_dwgfile})</span></td>
      <td class="num">${fmt(d.n_unfold)}</td>
      <td class="num">${d.n_ok==null?'<span style="color:var(--fg-3)">–</span>':fmt(d.n_ok)}</td>
      <td class="num"><span class="bar" style="width:${Math.max(4,70*d.gt_sheets/maxSheets)}px"></span>${d.gt_sheets}<span style="color:var(--fg-3);font-size:12px"> (ok ${d.gt_ok})</span></td>
      <td class="num">${fmt(d.kg)}</td>
      <td style="font-size:12.5px;color:var(--fg-2)">${d.groups.slice(0,3).join(' · ')}</td>
    </tr>
    <tr class="detail" data-for="${d.wo}" ${d.wo===openWo?'':'hidden'}><td colspan="9">${detail(d)}</td></tr>`).join('');
}
function detail(d){
  return `<div class="detail-grid">
    <div class="thumb">${d.dthumb?`<img src="${d.dthumb}" alt="${d.wo} 입력 도면 첫 페이지" loading="lazy">`:'<div style="padding:30px;text-align:center;color:var(--fg-3)">PDF 없음 (dwg 만 있음)</div>'}<div class="cap">입력: ${d.dname||'–'}</div></div>
    <div class="thumb">${d.cthumb?`<img src="${d.cthumb}" alt="${d.wo} 커팅플랜" loading="lazy">`:''}<div class="cap">커팅플랜: ${d.cname||'–'}</div></div>
    <div>
      <h3>정답 요약</h3>
      <div class="kv"><b>판재</b><span>${d.gt_sheets}장 (정상 ${d.gt_ok}), ${fmt(d.kg)} kg</span><b>재질·두께</b><span>${d.groups.join(', ')||'–'}</span><b>전개도</b><span>${fmt(d.n_unfold)}개, match ok ${d.n_ok==null?'–':fmt(d.n_ok)}</span></div>
      <h3 style="margin-top:12px">입력 도면 ${d.n_dwg}개</h3>
      <ul class="flist">${d.drawings.map(f=>`<li>${f}</li>`).join('')}${d.n_dwg>d.drawings.length?`<li>… +${d.n_dwg-d.drawings.length}</li>`:''}</ul>
    </div></div>`;
}
tb.addEventListener('click',e=>{ const tr=e.target.closest('tr.row'); if(!tr) return; toggle(tr.dataset.wo); });
tb.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ const tr=e.target.closest('tr.row'); if(tr){ e.preventDefault(); toggle(tr.dataset.wo);} } });
function toggle(wo){ openWo = openWo===wo?null:wo; render(); try{localStorage.setItem('td_open',openWo||'')}catch(e){} }
document.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{ const k=th.dataset.k; if(sortK===k) sortDir*=-1; else {sortK=k; sortDir = ['wo','customer','gclass','groups'].includes(k)?1:-1;} render(); }));
[q,fy,fg].forEach(el=>el.addEventListener('input',render));
try{ openWo = localStorage.getItem('td_open')||null; if(openWo && !DATA.some(d=>d.wo===openWo)) openWo=null; }catch(e){}
render();

// 제외 목록
document.getElementById('exclN').textContent = EXCL.length+'개';
document.getElementById('excl').innerHTML = EXCL.map(e=>`<div><b>${e.wo}</b><span title="${e.reason}">${e.reason}</span></div>`).join('');
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
