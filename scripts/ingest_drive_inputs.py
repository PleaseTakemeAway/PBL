# -*- coding: utf-8 -*-
"""
Google Drive 공유폴더('8. Data') 내려받은 것을 워크오더별 input/ 폴더로 분류.

사용:  PYTHONPATH=. uv run python scripts/ingest_drive_inputs.py [스테이징폴더]   (기본 Data/drive/8. Data)
       여러 번 실행해도 안전 (이미 복사된 파일은 건너뜀). zip 파트를 추가로 풀 때마다 다시 실행.

Drive 구조 (2026-10-01 확인):
  8. Data/기술부/KDM기술부 20YY년 자료(대외비)/<KDxxxxx - 고객명>/<DWG|CAL|DOC ...>/파일
      하위 폴더명 변형: DWG, 4. DWG, 4. Drawings, Drawings, dwg, '81653 PKG 1' / CAL, 3. CAL, 3. Calculation, Calculation / DOC, 1. DOC, Documents
      KD23079 는 DWG/동은, DWG/신우 처럼 협력사별 하위 폴더 있음
  8. Data/구매부/POR/**/#23002/#23002PR-01 TUBE.pdf     -> 워크오더 KD23002 의 구매요구서
  8. Data/구매부/타사 POR 자료/타사_테스트자료/기술_0406/[프로젝트]/05. 도면|07. PR, MPS  -> 타사 자료, 복사하지 않고 index 만

복사 규칙:
  drawings (dwg/pdf)  -> dataset/KDM/<year>/<wo>/input/drawings/   (하위 경로 유지)
  calculation         -> dataset/KDM/<year>/<wo>/input/calculation/
  por                 -> dataset/KDM/<year>/<wo>/input/por/
  documents(절차서 등)  -> 복사 안 함 (용량 큼). index.csv 에만 기록
  모든 파일은 dataset/KDM/<year>/<wo>/input/index.csv 에 (category, copied, source, size) 로 기록
"""

import collections
import csv
import os
import re
import shutil
import sys

from cutplan_agent.config import DATASET, DRIVE_STAGING

OUT = DATASET
DEFAULT_STAGING = DRIVE_STAGING
WO_RE = re.compile(r"KD(\d{2})(\d{3})(?:-\d)?", re.I)
POR_RE = re.compile(r"#(\d{2})(\d{3})")

CATEGORY_RULES = [  # (category, 폴더명 regex, 복사 여부)
    ("drawings", re.compile(r"dwg|draw|도면|pkg", re.I), True),
    ("calculation", re.compile(r"cal", re.I), True),
    ("documents", re.compile(r"doc", re.I), False),
]


def categorize(top_folder):
    for cat, rx, copy_it in CATEGORY_RULES:
        if rx.search(top_folder):
            return cat, copy_it
    return "other", False


def copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        return False
    shutil.copy2(src, dst)
    return True


def wo_dir(yy, num):
    return os.path.join(OUT, "KDM", "20" + yy, f"KD{yy}{num}")


def ingest_tech(staging, index, stats):
    tech = os.path.join(staging, "기술부")
    if not os.path.isdir(tech):
        return
    for ydir in sorted(os.listdir(tech)):
        for folder in sorted(os.listdir(os.path.join(tech, ydir))):
            wp = os.path.join(tech, ydir, folder)
            m = WO_RE.search(folder)
            if not os.path.isdir(wp) or not m:
                stats["unmatched_folders"].append(os.path.relpath(wp, staging))
                continue
            yy, num = m.group(1), m.group(2)
            wo = f"KD{yy}{num}"
            for r, _, fs in os.walk(wp):
                for f in fs:
                    src = os.path.join(r, f)
                    rel = os.path.relpath(src, wp).replace("\\", "/")
                    top = rel.split("/")[0] if "/" in rel else "(root)"
                    cat, copy_it = categorize(top)
                    sub = "/".join(rel.split("/")[1:]) if "/" in rel else rel
                    copied = ""
                    if copy_it:
                        dst = os.path.join(
                            wo_dir(yy, num), "input", cat, *sub.split("/")
                        )
                        new = copy_file(src, dst)
                        copied = os.path.relpath(dst, wo_dir(yy, num)).replace(
                            "\\", "/"
                        )
                        stats["copied" if new else "skipped"] += 1
                    index[wo].append(
                        {
                            "workorder": wo,
                            "category": cat,
                            "copied_to": copied,
                            "source": os.path.relpath(src, staging).replace("\\", "/"),
                            "size_mb": round(os.path.getsize(src) / 1e6, 2),
                            "customer": folder,
                        }
                    )


def ingest_por(staging, index, stats):
    por = os.path.join(staging, "구매부", "POR")
    if not os.path.isdir(por):
        return
    for r, _, fs in os.walk(por):
        for f in fs:
            src = os.path.join(r, f)
            m = POR_RE.search(os.path.relpath(src, por))
            if not m:
                stats["unmatched_files"].append(os.path.relpath(src, staging))
                continue
            yy, num = m.group(1), m.group(2)
            wo = f"KD{yy}{num}"
            dst = os.path.join(wo_dir(yy, num), "input", "por", f)
            new = copy_file(src, dst)
            stats["copied" if new else "skipped"] += 1
            index[wo].append(
                {
                    "workorder": wo,
                    "category": "por",
                    "copied_to": os.path.relpath(dst, wo_dir(yy, num)).replace(
                        "\\", "/"
                    ),
                    "source": os.path.relpath(src, staging).replace("\\", "/"),
                    "size_mb": round(os.path.getsize(src) / 1e6, 2),
                    "customer": "",
                }
            )


def index_third_party(staging):
    """타사 테스트자료는 복사하지 않고 dataset/_third_party_index.csv 로만 남긴다."""
    tp = os.path.join(staging, "구매부", "타사 POR 자료")
    if not os.path.isdir(tp):
        return 0
    rows = []
    for r, _, fs in os.walk(tp):
        for f in fs:
            src = os.path.join(r, f)
            rel = os.path.relpath(src, tp).replace("\\", "/")
            parts = rel.split("/")
            rows.append(
                {
                    "vendor": parts[0],
                    "project": parts[2] if len(parts) > 3 else "",
                    "subfolder": parts[-2],
                    "file": f,
                    "source": os.path.relpath(src, staging).replace("\\", "/"),
                    "size_mb": round(os.path.getsize(src) / 1e6, 2),
                }
            )
    with open(
        os.path.join(OUT, "_third_party_index.csv"),
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def write_indexes(index):
    fields = ["workorder", "category", "copied_to", "source", "size_mb", "customer"]
    for wo, rows in index.items():
        d = os.path.join(OUT, "KDM", "20" + wo[2:4], wo, "input")
        os.makedirs(d, exist_ok=True)
        with open(
            os.path.join(d, "index.csv"), "w", encoding="utf-8-sig", newline=""
        ) as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: (r["category"], r["source"])))


def refresh_manifest(new_wo=()):
    path = os.path.join(OUT, "manifest.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    for col in (
        "input_drawings",
        "input_calc",
        "input_por",
        "input_docs_indexed",
        "customer",
    ):
        if col not in fields:
            fields.append(col)
    known = {r["workorder"] for r in rows}
    # dataset/KDM 아래에 새로 생긴 워크오더(커팅플랜 없음) 추가
    for ydir in sorted(os.listdir(os.path.join(OUT, "KDM"))):
        for wo in sorted(os.listdir(os.path.join(OUT, "KDM", ydir))):
            if wo not in known:
                rows.append(
                    {k: "" for k in fields}
                    | {
                        "source": "KDM",
                        "year": ydir,
                        "workorder": wo,
                        "cp_files": 0,
                        "grade": "도면만",
                        "path": f"KDM/{ydir}/{wo}",
                    }
                )
                known.add(wo)
    for r in rows:
        root = os.path.join(
            OUT, *r["path"].replace("\\", "/").split("/")
        )  # Windows 에서 만든 manifest 는 역슬래시 경로
        inp = os.path.join(root, "input")
        cnt = lambda sub: (
            sum(len(fs) for _, _, fs in os.walk(os.path.join(inp, sub)))
            if os.path.isdir(os.path.join(inp, sub))
            else 0
        )
        r["input_drawings"], r["input_calc"], r["input_por"] = (
            cnt("drawings"),
            cnt("calculation"),
            cnt("por"),
        )
        r["input_docs_indexed"], r["customer"] = 0, r.get("customer", "")
        idx = os.path.join(inp, "index.csv")
        if os.path.exists(idx):
            with open(idx, encoding="utf-8-sig", newline="") as f:
                irows = list(csv.DictReader(f))
            r["input_docs_indexed"] = sum(
                1 for x in irows if x["category"] in ("documents", "other")
            )
            cust = next((x["customer"] for x in irows if x["customer"]), "")
            if cust:
                r["customer"] = cust
        unf = os.path.join(root, "unfold")
        r["unfold_files"] = (
            sum(1 for f in os.listdir(unf) if f.lower().endswith(".dxf"))
            if os.path.isdir(unf)
            else 0
        )
    rows.sort(key=lambda r: (r["source"] != "KDM", r["year"], r["workorder"]))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    have = [r for r in rows if int(r["input_drawings"] or 0) > 0]
    both = [r for r in have if int(r["cp_files"] or 0) > 0]
    print(
        f"manifest.csv 갱신: 워크오더 {len(rows)}개, 도면 있음 {len(have)}개, 도면+커팅플랜 모두 있음 {len(both)}개"
    )


def main():
    staging = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STAGING
    if not os.path.isdir(staging):
        sys.exit(f"스테이징 폴더 없음: {staging}")
    index = collections.defaultdict(list)
    stats = collections.Counter()
    stats["unmatched_folders"] = []
    stats["unmatched_files"] = []
    ingest_tech(staging, index, stats)
    ingest_por(staging, index, stats)
    write_indexes(index)
    n_tp = index_third_party(staging)
    print(
        f"copied={stats['copied']} skipped(existing)={stats['skipped']} workorders_with_input={len(index)} third_party_indexed={n_tp}"
    )
    if stats["unmatched_folders"]:
        print("워크오더 번호 없는 폴더:", stats["unmatched_folders"])
    if stats["unmatched_files"]:
        print("워크오더 번호 없는 POR 파일:", stats["unmatched_files"])
    refresh_manifest()


if __name__ == "__main__":
    main()
