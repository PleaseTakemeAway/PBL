# -*- coding: utf-8 -*-
"""
test_data/ 구축: 워크오더마다 (입력 도면, 출력 전개도, 출력 커팅플랜) 3종이 모두 있는 것만 모은다.

    test_data/
      README.md
      index.csv                      워크오더별 파일 수·품질·제외 사유 (제외된 것도 기록)
      <workorder>/
        input_drawings/              설계도면 dwg + pdf  (dataset/.../input/drawings 그대로, 협력사 하위폴더 유지)
        output_unfold/               부품별 전개 외곽 DXF + index.csv (match 열: ok/diff/none)
        output_cutting_plan/         *_CP.dwg + png + dxf  +  sheets.csv / parts.csv / part_tags.csv (판재·배치·부품표 정답)
      HCE_76K3-40022/                현대건설기계 판금 샘플 (정답 완비)

사용:  uv run python scripts/build_test_data.py [--link]    --link 이면 복사 대신 하드링크(같은 드라이브, 용량 절약)
원본(Data/dataset)은 건드리지 않는다.
"""
import csv, os, shutil, sys

from cutplan_agent.config import DATASET, TEST_DATA

BASE = DATASET
OUT = TEST_DATA
LINK = "--link" in sys.argv


def put(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        return 0
    if LINK:
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.link(src, dst)
            return 1
        except OSError:
            pass
    shutil.copy2(src, dst)
    return 1


def copy_tree(src, dst, exts=None):
    n = 0
    if not os.path.isdir(src):
        return 0
    for r, _, fs in os.walk(src):
        for f in fs:
            if exts and os.path.splitext(f)[1].lower() not in exts:
                continue
            n += put(os.path.join(r, f), os.path.join(dst, os.path.relpath(os.path.join(r, f), src)))
    return n


def count(d, exts=None):
    return sum(1 for r, _, fs in os.walk(d) for f in fs if not exts or os.path.splitext(f)[1].lower() in exts) if os.path.isdir(d) else 0


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = list(csv.DictReader(open(os.path.join(BASE, "manifest.csv"), encoding="utf-8-sig")))
    rows = []
    for r in manifest:
        src = os.path.join(BASE, *r["path"].replace("\\", "/").split("/"))   # Windows 에서 만든 manifest 는 역슬래시 경로
        wo = r["workorder"]
        if r["source"] == "HCE":
            dst = os.path.join(OUT, "HCE_" + wo)
            copy_tree(os.path.join(src, "input"), os.path.join(dst, "input_drawings"))
            copy_tree(os.path.join(src, "unfold"), os.path.join(dst, "output_unfold"))
            copy_tree(os.path.join(src, "cutting_plan"), os.path.join(dst, "output_cutting_plan"))
            copy_tree(os.path.join(src, "gt"), os.path.join(dst, "output_cutting_plan"))
            rows.append({"workorder": "HCE_" + wo, "year": r["year"], "customer": "현대건설기계 (판금)", "included": "yes", "reason": "",
                         "input_drawings": count(os.path.join(dst, "input_drawings"), {".pdf", ".dwg", ".dxf", ".xlsx"}),
                         "unfold_dxf": count(os.path.join(dst, "output_unfold"), {".dxf"}),
                         "unfold_match_ok": "", "cp_files": count(os.path.join(dst, "output_cutting_plan"), {".taf", ".json"}),
                         "gt_sheets": 1, "gt_sheets_ok": 1, "grade": r["grade"]})
            continue
        n_in = int(r["input_drawings"] or 0); n_cp = int(r["cp_files"] or 0); n_unf = int(r["unfold_files"] or 0)
        reason = []
        if n_in == 0:
            reason.append("입력 도면 없음(Drive zip 파트 미확보)")
        if n_cp == 0:
            reason.append("커팅플랜 없음")
        if n_cp > 0 and n_unf == 0:
            reason.append("전개도 추출 0 (chain_path 판재)")
        included = not reason
        row = {"workorder": wo, "year": r["year"], "customer": r.get("customer", ""), "included": "yes" if included else "no",
               "reason": "; ".join(reason), "input_drawings": n_in, "unfold_dxf": n_unf, "unfold_match_ok": "",
               "cp_files": n_cp, "gt_sheets": r["n_sheets"], "gt_sheets_ok": r["n_sheets_ok"], "grade": r["grade"]}
        if included:
            dst = os.path.join(OUT, wo)
            copy_tree(os.path.join(src, "input", "drawings"), os.path.join(dst, "input_drawings"))
            copy_tree(os.path.join(src, "unfold"), os.path.join(dst, "output_unfold"))
            copy_tree(os.path.join(src, "cutting_plan"), os.path.join(dst, "output_cutting_plan"))
            copy_tree(os.path.join(src, "gt"), os.path.join(dst, "output_cutting_plan"), {".csv"})
            idx = os.path.join(dst, "output_unfold", "index.csv")
            if os.path.exists(idx):
                row["unfold_match_ok"] = sum(1 for x in csv.DictReader(open(idx, encoding="utf-8-sig")) if x["match"] == "ok")
        rows.append(row)
    rows.sort(key=lambda x: (x["included"] != "yes", x["workorder"]))
    with open(os.path.join(OUT, "index.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    inc = [x for x in rows if x["included"] == "yes"]
    readme = f"""# test_data — 입력 도면 → 전개도 → 커팅플랜 3종이 모두 갖춰진 워크오더 {len(inc)}개

각 폴더:
```
<workorder>/
  input_drawings/        설계도면 (GA, DETAIL OF BODY/NOZZLE/SADDLE/BUNDLE ...). dwg(벡터) + pdf(이미지). 협력사 하위폴더(동은/신우) 유지
  output_unfold/         부품별 전개 외곽 DXF (커팅플랜에서 잘라낸 평판 형상, 좌하단 원점). index.csv 의 match=ok 행만 평가에 사용
  output_cutting_plan/   *_CP.dwg(원본) + .png + .dxf, sheets.csv(판재 규격·수량), parts.csv(부품 배치 좌표), part_tags.csv(부품표)
```
HCE_76K3-40022 는 현대건설기계 판금 샘플: input_drawings(스캔 PDF 10p + BOM xlsx + 페이지 트레이스 DXF), output_unfold(고객 제공 정답 DXF 5개 + 생성본),
output_cutting_plan(TruTops TAF + nesting_dataset.json + sheets/parts/bom csv).

index.csv: 전체 {len(rows)} 워크오더. included=no 인 것은 reason 열에 빠진 이유. 입력 도면이 없는 것은 Drive zip 나머지 파트를 풀고
`scripts/ingest_drive_inputs.py` → `scripts/build_test_data.py` 를 다시 돌리면 추가된다.

권장 사용 순서: grade=성공, gt_sheets_ok 큰 순. 평가 지표는 cutplan_agent/README.md 참조.
시각화: 같은 폴더의 README.html (브라우저에서 열기, 썸네일 내장). 갱신은 `scripts/build_test_data_html.py`.
원본: Data/dataset (여기는 그 부분집합의 {'하드링크' if LINK else '복사본'}).
"""
    open(os.path.join(OUT, "README.md"), "w", encoding="utf8").write(readme)
    n_files = sum(len(fs) for _, _, fs in os.walk(OUT))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs) / 1e6
    print(f"included={len(inc)} excluded={len(rows)-len(inc)} files={n_files} size={size:.0f}MB -> {OUT}")
    for x in rows:
        if x["included"] != "yes":
            print(f"  제외 {x['workorder']}: {x['reason']}")


if __name__ == "__main__":
    main()
