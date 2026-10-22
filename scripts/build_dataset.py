"""
Data/dataset/ 구축 스크립트.

워크오더(KDxxxxx) 단위로 입력 도면 / 커팅플랜 / 전개도 / 정답 CSV를 한 폴더에 모은다.

    Data/dataset/
      README.md
      manifest.csv
      KDM/<year>/<workorder>/
          input/          <- Google Drive POR PDF (ingest_drive_inputs.py 로 채움)
          cutting_plan/   <- *_CP.dwg + png + dxf (로컬 복사)
          unfold/         <- 커팅플랜에서 잘라낸 부품별 전개 외곽 DXF (extract_part_unfolds.py)
          gt/             <- sheets/parts/part_tags CSV 부분집합 + scorecard.json
      HCE/76K3-40022/
          input/          <- 스캔 PDF + BOM xlsx
          unfold/         <- 고객 제공 정답 DXF + 생성 flat DXF
          cutting_plan/   <- TruTops TAF + nesting_dataset.json + sheets/parts csv

원본 폴더는 건드리지 않는다(복사만).
"""

import collections
import csv
import json
import os
import re
import shutil

import openpyxl

from cutplan_agent.config import DATA_DIR, DATASET

BASE = DATA_DIR
OUT = DATASET
YEAR_DIR = {
    "2023": "2023년 cutting plan",
    "2024": "2024년 cutting plan",
    "2025": "2025년 cutting plan",
}
WO_RE = re.compile(r"(KD\d{5})")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    if not rows and not fields:
        return
    fields = fields or list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)


def build_kdm():
    wb = openpyxl.load_workbook(
        os.path.join(BASE, "KD_CP_파일목록.xlsx"), read_only=True
    )
    rows = list(wb.worksheets[0].iter_rows(values_only=True))[1:]
    sheets = read_csv(os.path.join(BASE, "_dataset", "sheets.csv"))
    parts = read_csv(os.path.join(BASE, "_dataset", "parts.csv"))
    tags = read_csv(os.path.join(BASE, "_dataset", "part_tags.csv"))
    score = {
        r["drawing"]: r
        for r in read_csv(os.path.join(BASE, "_dataset", "scorecard.csv"))
    }
    by_drawing = lambda rows_: collections.defaultdict(
        list,
        {
            k: [r for r in rows_ if r["drawing"] == k]
            for k in {r["drawing"] for r in rows_}
        },
    )
    sheets_by, parts_by, tags_by = (
        by_drawing(sheets),
        by_drawing(parts),
        by_drawing(tags),
    )

    manifest = []
    workorders = collections.OrderedDict()
    for _, year, cp_name in rows:
        year, cp_name = str(year), str(cp_name)
        wo = WO_RE.match(cp_name).group(1)
        workorders.setdefault((year, wo), []).append(cp_name)

    for (year, wo), cp_names in workorders.items():
        root = os.path.join(OUT, "KDM", year, wo)
        for sub in ("input", "cutting_plan", "unfold", "gt"):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        src_dir = os.path.join(BASE, YEAR_DIR[year])
        gt_sheets, gt_parts, gt_tags, sc = [], [], [], {}
        for cp in cp_names:
            copy(
                os.path.join(src_dir, cp + ".dwg"),
                os.path.join(root, "cutting_plan", cp + ".dwg"),
            )
            for ext, sub in (
                (".png", "images"),
                (".dxf", os.path.join("images", "_dxf")),
            ):
                p = os.path.join(src_dir, sub, cp + ext)
                if os.path.exists(p):
                    copy(p, os.path.join(root, "cutting_plan", cp + ext))
            gt_sheets += sheets_by[cp]
            gt_parts += parts_by[cp]
            gt_tags += tags_by[cp]
            if cp in score:
                sc[cp] = score[cp]
        write_csv(
            os.path.join(root, "gt", "sheets.csv"), gt_sheets, list(sheets[0].keys())
        )
        write_csv(
            os.path.join(root, "gt", "parts.csv"), gt_parts, list(parts[0].keys())
        )
        write_csv(
            os.path.join(root, "gt", "part_tags.csv"), gt_tags, list(tags[0].keys())
        )
        with open(
            os.path.join(root, "gt", "scorecard.json"), "w", encoding="utf8"
        ) as f:
            json.dump(sc, f, ensure_ascii=False, indent=1)
        n_ok = sum(1 for s in gt_sheets if s["quality"] == "ok")
        grades = sorted({v["grade"] for v in sc.values()})
        manifest.append(
            {
                "source": "KDM",
                "year": year,
                "workorder": wo,
                "cp_files": len(cp_names),
                "cp_names": " | ".join(cp_names),
                "n_sheets": len(gt_sheets),
                "n_sheets_ok": n_ok,
                "n_parts": len(gt_parts),
                "n_tags": len(gt_tags),
                "grade": "/".join(grades),
                "input_drawings": len(
                    [
                        f
                        for f in os.listdir(os.path.join(root, "input"))
                        if not f.startswith(".")
                    ]
                ),
                "unfold_files": len(os.listdir(os.path.join(root, "unfold"))),
                "path": os.path.relpath(root, OUT).replace(
                    os.sep, "/"
                ),  # OS 와 무관하게 슬래시로 기록
            }
        )
    return manifest


def build_hce():
    src = os.path.join(BASE, "data_v2")
    root = os.path.join(OUT, "HCE", "76K3-40022")
    for sub in (
        "input",
        "unfold",
        "unfold/generated_flat",
        "unfold/generated_flat_dim",
        "cutting_plan",
        "gt",
    ):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    copy(
        os.path.join(src, "76K3-40022.pdf"),
        os.path.join(root, "input", "76K3-40022.pdf"),
    )
    copy(
        os.path.join(src, "76K3-40022BOM.xlsx"),
        os.path.join(root, "input", "76K3-40022BOM.xlsx"),
    )
    # 페이지별 트레이스 DXF도 입력 보조자료로
    for f in os.listdir(os.path.join(src, "_dxf_from_pdf")):
        copy(
            os.path.join(src, "_dxf_from_pdf", f),
            os.path.join(root, "input", "page_trace_dxf", f),
        )
    n_cust = 0
    for f in os.listdir(src):
        if f.lower().endswith(".dxf") and "／" in f:  # 고객 제공 정답 전개 DXF
            copy(os.path.join(src, f), os.path.join(root, "unfold", f))
            n_cust += 1
    for sub, dst in (
        ("_flat_by_page", "generated_flat"),
        ("_flat_by_page_dim", "generated_flat_dim"),
    ):
        for f in os.listdir(os.path.join(src, sub)):
            copy(os.path.join(src, sub, f), os.path.join(root, "unfold", dst, f))
    copy(
        os.path.join(src, "76K3_40022_4T_2.TAF"),
        os.path.join(root, "cutting_plan", "76K3_40022_4T_2.TAF"),
    )
    for f in os.listdir(os.path.join(src, "_dataset")):
        dst = "cutting_plan" if f in ("nesting_dataset.json",) else "gt"
        copy(os.path.join(src, "_dataset", f), os.path.join(root, dst, f))
    parts = read_csv(os.path.join(root, "gt", "parts.csv"))
    return [
        {
            "source": "HCE",
            "year": "2022",
            "workorder": "76K3-40022",
            "cp_files": 1,
            "cp_names": "76K3_40022_4T_2.TAF",
            "n_sheets": 1,
            "n_sheets_ok": 1,
            "n_parts": len(parts),
            "n_tags": 22,
            "grade": "성공",
            "input_drawings": 2,
            "unfold_files": n_cust,
            "path": os.path.relpath(root, OUT).replace(os.sep, "/"),
        }
    ]


README = """# dataset/ 구조

워크오더 단위로 **입력 도면 → 전개도 → 커팅플랜** 을 매칭한 데이터셋.

```
KDM/<year>/<workorder>/     KDM Tech 압력용기 (67개 커팅플랜, 59 워크오더 + 도면만 있는 워크오더)
  input/         Google Drive '8. Data/기술부' 에서 가져온 설계 자료. scripts/ingest_drive_inputs.py 로 채움
    drawings/      GA, Detail of body/tube bundle/saddle/nozzle 등 설계도면 (dwg + pdf). 협력사 하위폴더(동은/신우) 유지
    calculation/   강도계산서 PDF (shell 두께, 압력/온도 등 데이터시트 값의 출처)
    por/           구매부/POR 의 구매요구서 PDF (#23002PR-01 ...). 현재 소수만 확보
    index.csv      원본 경로·분류·복사 여부. documents(절차서) 는 용량 때문에 복사 안 하고 여기만 기록
  cutting_plan/  *_CP.dwg (원본) + .png/.dxf (변환본)  = 최종 출력 정답
  unfold/        커팅플랜에서 잘라낸 부품별 외곽 DXF     = 전개도 정답 (scripts/extract_part_unfolds.py)
  gt/            sheets.csv(판재), parts.csv(부품 배치), part_tags.csv(부품표), scorecard.json(추출 품질)
HCE/76K3-40022/             현대건설기계 판금 브라켓 (정답 완비 샘플)
  input/         스캔 PDF 10p + BOM xlsx + 페이지 트레이스 DXF
  unfold/        고객 제공 정답 전개 DXF 5개 (`76K3-xxxxx／4T／1EA.dxf`), generated_flat*/ 는 이전 세션 생성본
  cutting_plan/  TruTops TAF (네스팅 정답) + nesting_dataset.json
  gt/            sheets.csv, parts.csv, bom.csv
manifest.csv                워크오더별 파일 수·품질 요약. input_drawings=0 이면 Drive 도면 미확보, cp_files=0 이면 커팅플랜 없음(grade=도면만)
_third_party_index.csv      구매부/타사 POR 자료 (타사 프로젝트의 05. 도면 / 07. PR, MPS). 복사하지 않고 목록만
```

Drive 원본은 `Data/drive/8. Data/` 에 푼다 (2026-10-01 기준 zip 파트 007·008 만 해제). 나머지 파트를 풀면 ingest 스크립트를 다시 실행.

## Drive 원본(8. Data) 폴더별 의미와 파이프라인에서의 역할 (2026-10-01 샘플 확인)
| 폴더 | 내용 | 역할 |
|---|---|---|
| 기술부/.../<WO>/DWG | GA(설계조건표·재질표·노즐표·전체치수), Detail of body(쉘 코스·헤드·용접선·BOM), tube bundle(튜브시트·배플), saddle, nozzle(보강패드), test ring, name plate. dwg+pdf | **입력**. 판재 부품 목록과 전개 치수의 출처 |
| 기술부/.../<WO>/CAL | 강도계산서(설계압력·온도·부식여유, 부품별 소요두께, 중량 요약) | 검증. BOM 두께·중량 cross-check, GA에 없는 설계값 보충 |
| 기술부/.../<WO>/DOC | 수압시험·검사·NDE·도장·포장 절차서, WPS/PQR | 미사용 (복사 안 함) |
| 구매부/POR | 구매요구서. `*PR-nn PLATE.pdf` 는 재질·t×W×L·SH'T 수량·중량 표 = 커팅플랜 결과물 | **최종 출력 정답** (STEP 4 구매요구서) |
| 구매부/견적서(발췌본) | 워크오더·자재군별(PLATE, FORGING, TUBE…) 업체 견적 | 참고. PLATE 견적은 POR 판재 목록의 2차 검증 |
| 구매부/타사 POR 자료 | 신화·일진·타사 테스트자료: 타사의 PR, MPS, POS, NESTING.dwg, DEVELOPMENT DWG(전개도) | 추가 학습/평가 데이터 (도면 표기 방식 다양성). `_third_party_index.csv` |
| 영업부 | 입찰(ITB/RFQ)·현설자료·고객 GAD·질의응답. 대부분 배관/건설 공사 | 미사용. 장치 제작건의 고객 GAD 만 STEP 1 입력 후보 |

## 사용 우선순위
- `grade` = 성공 이고 `n_sheets_ok` 가 큰 워크오더부터 (정답 노이즈 적음)
- `quality = chain_path` 판재는 부품 분리 불가 → 네스팅 평가에서 제외
- HCE 샘플은 전개도 IoU 평가의 기준 세트

## unfold/ 사용 시 주의 (2026-10-01 점검 결과)
- `unfold/index.csv` 의 `match` 열: `ok` = 잘라낸 엔티티 수가 parts.csv n_ents 와 일치, `diff` = 불일치, `none` = 해당 bbox 안에 기하 없음
- **평가에는 match=ok 행만 사용**할 것. diff 는 이웃 부품 혼입 또는 ARC 누락 가능성 있음
- parts.csv 의 w/h 는 곡선을 꼭짓점 기준으로 근사한 값이라 큰 ARC 가 있는 부품은 bbox 가 실제보다 작음 → 그런 부품은 diff/none
- parts.csv 에는 부재번호 풍선 원(레이어 `부재번호`, 약 90x90, n_ents=1, holes=0)이 부품으로 잘못 잡힌 행이 약 900개 있음 → none 으로 표시되므로 자동 제외됨
- 근본 해결(닫힌 루프 기반 재추출)은 TODO
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = build_kdm() + build_hce()
    write_csv(os.path.join(OUT, "manifest.csv"), manifest)
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf8") as f:
        f.write(README)
    n_files = sum(len(fs) for _, _, fs in os.walk(OUT))
    size = (
        sum(
            os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs
        )
        / 1e6
    )
    print(f"workorders: {len(manifest)}  files: {n_files}  size: {size:.1f} MB")
    print("grade 분포:", collections.Counter(m["grade"] for m in manifest))


if __name__ == "__main__":
    main()
