"""저장된 reader 결과를 오프라인 HTML 보고서와 ZIP으로 내보낸다.

PYTHONPATH=. uv run python scripts/reader/export_report.py <실행 폴더> --out <새 출력 폴더>
모델을 호출하지 않는다. 기존 show_stages 시각화를 생성하고 그림을 HTML에 내장한다.
"""

import argparse
import base64
import html
import io
import json
import re
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from scripts.reader.show_stages import report

CLASS_NAMES = {
    "flat": "평판",
    "bent_sheet": "굽힘판",
    "cylinder": "원통",
    "cone": "콘",
    "press_formed": "경판",
    "other": "기타",
}
STEPS = [
    "읽기",
    "표제란",
    "OCR",
    "필드",
    "뷰",
    "형상",
    "통합",
    "구조화",
    "치수",
    "전개",
]
CSS = """
body{font-family:system-ui,sans-serif;background:#eef3f4;color:#1f2a30;margin:0}
main{max-width:1250px;margin:auto;padding:32px}h1{font-size:30px}
a{color:#24696d} .note{background:#fff;padding:18px;border-left:5px solid #e8743b}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px;margin-top:24px}
.card{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px #0001}
.preview{width:100%;height:210px;object-fit:contain;background:#fafafa}
.statuses{display:flex;flex-wrap:wrap;gap:5px;margin:12px 0}
.badge{padding:6px 8px;border-radius:5px;font-size:13px;background:#e4e7eb}
.done{background:#dcebec;color:#215c37}.failed{background:#fbe7dc;color:#a33219}
.skipped{background:#fff0c7;color:#795c12}small{color:#5f6b73}.big{font-size:24px;font-weight:700}
input{width:90%;max-width:500px;padding:12px;font-size:16px;margin-top:20px}
@media print{input{display:none}.card{break-inside:avoid}}
"""


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def data_uri(path):
    if not path.is_file():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode(
        "ascii"
    )


def inline_images(page, work):
    """show_stages HTML의 로컬 PNG만 내장한다. 작업 폴더 밖은 읽지 않는다."""

    def replace(match):
        target = (work / "figures" / html.unescape(match[1])).resolve()
        if not target.is_relative_to(work.resolve()) or target.suffix.lower() != ".png":
            raise ValueError(f"허용하지 않는 그림 경로: {match[1]}")
        uri = data_uri(target)
        return f'src="{uri}"' if uri else 'alt="그림 파일 없음"'

    return re.sub(r'src="([^"]+)"', replace, page)


def export(source, out, title, dpi):
    works = sorted(
        {
            p.parent.parent
            for pattern in ("stages/00_convert.json", "stages/01_read.json")
            for p in source.rglob(pattern)
        }
    )
    if not works:
        raise ValueError(
            "00_convert.json 또는 01_read.json이 있는 도면 작업 폴더를 찾지 못했습니다"
        )
    if out.exists() or out.with_suffix(".zip").exists():
        raise ValueError(
            "출력 폴더 또는 ZIP이 이미 있습니다. 새로운 --out을 지정하세요"
        )
    (out / "drawings").mkdir(parents=True)
    cards = []
    errors = []
    for i, work in enumerate(works, 1):
        label = str(work.relative_to(source)) if work != source else work.name
        print(f"[{i}/{len(works)}] {label}", flush=True)
        href = f"drawings/{i:03d}.html"
        try:
            with redirect_stdout(io.StringIO()):
                report(work, dpi=dpi)
            page = (work / "figures/index.html").read_text(encoding="utf-8")
            page = inline_images(page, work)
            page = page.replace(
                "<body>", '<body><p><a href="../index.html">← 전체 도면 목록</a></p>', 1
            )
            (out / href).write_text(page, encoding="utf-8")
        except Exception as exc:
            errors.append({"drawing": label, "error": str(exc)})
            page = f'<html lang="ko"><meta charset="utf-8"><a href="../index.html">목록</a><h1>보고서 생성 실패</h1><pre>{html.escape(str(exc))}</pre></html>'
            (out / href).write_text(page, encoding="utf-8")
        stages = {
            n: read(work / "stages" / f"{n:02d}_{name}.json")
            for n, name in enumerate(
                [
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
                ],
                1,
            )
        }
        decision = stages[6].get("decision") or {}
        cls = decision.get("part_class") or stages[7].get("part_class")
        classification = CLASS_NAMES.get(cls, cls or "분류 결과 없음")
        record = stages[10].get("record") or {}
        developed = stages[10].get("status") == "done"
        badges = []
        for n, stage in stages.items():
            status = stage.get("status", "missing")
            color = status if status in ("done", "failed", "skipped") else "missing"
            badges.append(
                f'<span class="badge {color}" title="{html.escape(status)}">{n:02d} {STEPS[n - 1]} · {html.escape(status)}</span>'
            )
        preview = next(
            (
                p
                for p in [
                    work / "figures/06_view_labels.png",
                    work / "analysis/sheet.png",
                    work / "figures/01_read.png",
                ]
                if p.is_file()
            ),
            None,
        )
        image = (
            f'<img class="preview" src="{data_uri(preview)}" alt="뷰와 형상 분류">'
            if preview
            else "<p>미리보기 없음</p>"
        )
        flat = work / "flat_pattern.png"
        flat_image = (
            f'<img class="preview" src="{data_uri(flat)}" alt="개별 부품 전개도">'
            if developed and flat.is_file()
            else ""
        )
        blank = html.escape(
            json.dumps(record.get("blank") or {}, ensure_ascii=False, indent=2)
        )
        cards.append(f'''<article class="card"><small>{html.escape(label)}</small>
<h2><a href="{href}">{html.escape(work.name)}</a></h2>
<p class="big">{html.escape(classification)}</p>{image}
<div class="statuses">{"".join(badges)}</div>
<p>전개: {"생성됨" if developed else "생성되지 않음"}</p>{flat_image}
<details><summary>전개 계산 값</summary><pre>{blank}</pre></details>
<p><a href="{href}">단계별 그림·표 모두 보기 →</a></p></article>''')
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><main><h1>{html.escape(title)}</h1><p>도면 {len(works)}건 · 보고서 생성 오류 {len(errors)}건</p>
<div class="note">초록은 단계 실행 완료이며 정답 판정을 뜻하지 않습니다. 노랑은 건너뛰기, 주황은 실패, 회색은 기록 없음입니다.
최종 이미지는 개별 부품 전개도이며 판재 네스팅 커팅플랜은 포함하지 않습니다.
정답 비교는 입력 경로 옆의 현재 label.json을 사용하므로 실행 당시 정답과 같은 판인지 확인하세요.</div>
<input id="search" type="search" placeholder="도면 이름 또는 형상으로 찾기" aria-label="도면 검색">
<div class="grid">{"".join(cards)}</div><p>그림이 내장된 오프라인 보고서입니다. 모델 서버 없이 열 수 있습니다.</p></main>
<script>document.getElementById('search').addEventListener('input',e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.hidden=!c.textContent.toLowerCase().includes(q));}});</script></body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "export_errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archive = shutil.make_archive(str(out), "zip", out.parent, out.name)
    print(f"HTML: {out / 'index.html'}\nZIP: {archive}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="도면 판독 단계별 결과")
    parser.add_argument("--dpi", type=int, default=140)
    args = parser.parse_args()
    errors = export(args.source.resolve(), args.out.resolve(), args.title, args.dpi)
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
