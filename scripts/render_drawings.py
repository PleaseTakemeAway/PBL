"""
DWG·DXF 도면을 사람이 보는 PDF·PNG 로 바꾼다. 에이전트(v2·v3)와 따로 돈다.

    uv run python scripts/render_drawings.py <DWG·DXF 파일 또는 폴더> ... [-o 출력 폴더]

  예) uv run python scripts/render_drawings.py "Data/2025년 cutting plan"
      -> runs/render_drawings/2025년 cutting plan/KD25003_CP.pdf, KD25003_CP.png, ...

- DWG 는 GNU LibreDWG 의 dwg2dxf 로 DXF 를 만든 뒤 그린다. 그리는 라이브러리(ezdxf)가 DWG 를
  읽지 못하기 때문이다. 이 DXF 는 임시 파일이고, --keep-dxf 를 주면 결과 옆에 남긴다.
- dwg2dxf 는 --dwg2dxf, 환경변수 DWG2DXF, PATH, 툴킷 tools/dwg2png/libredwg/ 순서로 찾는다.
  Linux 는 scripts/install_libredwg.sh 로 설치하고, Windows 는 툴킷의 dwg2dxf.exe 를 쓴다.
- 그리기는 v2 의 l1_perception._render_dxf 를 바탕으로 했다 (ezdxf matplotlib 백엔드, 흰 배경에
  검은 선, 한글 글자는 설치된 한글 폰트로 바꿔 그림). 에이전트 코드와 엮이지 않게 이 파일에 따로 둔다.
- 그리는 범위에서 무한선과 본체에서 동떨어진 엔티티 몇 개는 빼고 (view_box), 실제로 그려진 곳으로
  좁힌다 (ink_box). DWG 변환에서 깨진 엔티티 때문에 도면이 점처럼 작아지는 것을 막는다.
- LibreDWG 0.14 는 R2007 DWG 일부를 읽지 못하고 빈 DXF 를 쓴다. 이런 도면은 실패로 보고한다.
  AutoCAD 나 DWG TrueView 로 열어야 한다.
- 출력은 입력 폴더 구조를 따라 만든다. 이미 있으면 건너뛰고, --force 면 다시 만든다.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(os.environ.get("CUTPLAN_ROOT") or Path(__file__).resolve().parents[1])
DEFAULT_OUT = ROOT / "runs" / "render_drawings"
TOOLKIT_LIBREDWG = ROOT / "tools" / "dwg2png" / "libredwg"
# 앞에서부터 설치된 것을 쓴다. Windows, Linux(fonts-noto-cjk / fonts-nanum), macOS 순
HANGUL_FONT_FAMILIES = [
    "Malgun Gothic",
    "Noto Sans CJK KR",
    "NanumGothic",
    "Apple SD Gothic Neo",
]
HANGUL = re.compile(r"[가-힣]")
SUFFIXES = {".dwg", ".dxf"}
DPI = 200
MARGIN = 0.01  # 그림 가장자리 여백 (긴 변 대비)
INK_DPI = 50  # 실제로 그려진 범위를 찾을 때 쓰는 해상도
OUTLIER_SHARE = 0.02  # view_box 가 뺄 수 있는 동떨어진 엔티티 비율
OUTLIER_GAP = 0.1  # 본체 크기 대비 이만큼 넘게 떨어져야 뺀다


def find_dwg2dxf(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit) if Path(explicit).is_file() else None
    for cand in (os.environ.get("DWG2DXF"), shutil.which("dwg2dxf")):
        if cand and Path(cand).is_file():
            return Path(cand)
    for name in ("dwg2dxf.exe", "dwg2dxf"):
        if (TOOLKIT_LIBREDWG / name).is_file():
            return TOOLKIT_LIBREDWG / name
    return None


def find_hangul_font() -> str | None:
    """설치된 한글 폰트의 파일 이름. ezdxf 는 글꼴 스타일의 폰트를 파일 이름으로 찾는다."""
    from ezdxf.fonts import fonts
    from matplotlib import font_manager

    for family in HANGUL_FONT_FAMILIES:
        try:
            path = font_manager.findfont(
                font_manager.FontProperties(family=family), fallback_to_default=False
            )
        except ValueError:
            continue
        name = Path(path).name
        # ezdxf 의 폰트 캐시에 없으면 다른 폰트로 바꿔 그리므로 한글이 네모가 된다
        if fonts.font_manager.get_font_face(name).filename == name:
            return name
    return None


def dwg_to_dxf(dwg2dxf: Path, dwg: Path, dxf: Path, opts: list[str]) -> str:
    """dwg2dxf 를 실행하고 stderr 를 돌려준다. 읽기 오류가 나도 종료 코드 0 으로 빈 DXF 를 쓸 때가 있다."""
    proc = subprocess.run(
        [str(dwg2dxf), "-y", *opts, "-o", str(dxf), str(dwg)],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
    )
    if not dxf.is_file() or dxf.stat().st_size == 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise RuntimeError(
            f"dwg2dxf 실패 (종료 코드 {proc.returncode}): " + " / ".join(tail)
        )
    return proc.stderr


def load_dwg(dwg2dxf: Path, dwg: Path, dxf: Path):
    """DWG -> DXF -> ezdxf 문서. ezdxf 가 못 읽는 DXF 가 나오면 R2000 DXF 로 바꿔 보고
    (KDM 입력 도면 3개가 이렇게 읽힌다), 그래도 안 되면 처음 방식으로 한 번 더 바꾼다.
    LibreDWG 는 일부 도면의 글자 뒤에 실행마다 다른 쓰레기 바이트를 붙여서, 같은 DWG 도
    어떤 실행에서는 못 읽는 DXF 가 나온다."""
    from ezdxf import recover

    first_error = None
    for opts in ([], ["--as", "r2000"], []):
        stderr = dwg_to_dxf(dwg2dxf, dwg, dxf, opts)
        try:
            doc, _ = recover.readfile(str(dxf))
        except Exception as exc:
            first_error = first_error or exc
            continue
        if not any(len(doc.layouts.get(name)) for name in doc.layouts.names()):
            errors = [line for line in stderr.splitlines() if line.startswith("ERROR")]
            raise RuntimeError(
                "LibreDWG 가 이 DWG 를 읽지 못했다 (엔티티 0). "
                + " / ".join(errors[:3])
            )
        return doc
    raise first_error


def view_box(msp) -> tuple[float, float, float, float] | None:
    """모델 공간에서 그릴 범위 (x0, y0, x1, y1).

    무한선(RAY, XLINE)은 범위에 넣지 않는다. 본체와 본체 크기의 10% 넘는 빈틈을 두고 떨어진
    엔티티 몇 개(엔티티 수의 2% 이하)도 뺀다. DWG 변환에서 깨진 해치나 빈 MTEXT, 떨어진 점
    하나 때문에 도면 전체가 점처럼 작아지는 것을 막는다. 도면 테두리처럼 본체 바로 바깥에
    있는 것은 빈틈이 작아 남는다.
    """
    from ezdxf import bbox

    boxes = [b for b in bbox.multi_flat(msp, fast=True) if b.has_data]
    if not boxes:
        return None
    k = int(len(boxes) * OUTLIER_SHARE)
    x0s, y0s = sorted(b.extmin.x for b in boxes), sorted(b.extmin.y for b in boxes)
    x1s, y1s = sorted(b.extmax.x for b in boxes), sorted(b.extmax.y for b in boxes)
    tol_x = OUTLIER_GAP * (x1s[-1 - k] - x0s[k])
    tol_y = OUTLIER_GAP * (y1s[-1 - k] - y0s[k])
    return (
        _low_edge(x0s, k, tol_x),
        _low_edge(y0s, k, tol_y),
        -_low_edge([-v for v in reversed(x1s)], k, tol_x),
        -_low_edge([-v for v in reversed(y1s)], k, tol_y),
    )


def _low_edge(values: list[float], k: int, tol: float) -> float:
    """오름차순 values 의 k 번째 값에서 아래로, 이웃과의 간격이 tol 이하인 동안 이어 간 끝값."""
    i = k
    while i > 0 and values[i] - values[i - 1] <= tol:
        i -= 1
    return values[i]


def set_frame(fig, ax, box, px: int) -> None:
    """box 에 여백을 붙여 축 범위로 잡고, 그림 크기를 그 비율에 맞춘다 (긴 변 px 픽셀)."""
    x0, y0, x1, y1 = box
    m = MARGIN * max(x1 - x0, y1 - y0, 1e-9)
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    ar = (x1 - x0) / (y1 - y0)
    fw, fh = (px / DPI, px / DPI / ar) if ar >= 1 else (px / DPI * ar, px / DPI)
    fig.set_size_inches(max(fw, 2), max(fh, 2), forward=True)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def ink_box(fig, ax) -> tuple[float, float, float, float] | None:
    """낮은 해상도로 그려 완전한 흰색(255)이 아닌 픽셀의 범위를 데이터 좌표로 돌려준다. 빈 그림이면 None."""
    import numpy as np

    dpi = fig.get_dpi()
    fig.set_dpi(INK_DPI)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].min(axis=2) < 255
    h = img.shape[0]
    rows, cols = np.nonzero(img.any(axis=1))[0], np.nonzero(img.any(axis=0))[0]
    corners = None
    if len(rows):
        # 화면 좌표는 아래가 0, 이미지 행은 위가 0
        corners = ax.transData.inverted().transform(
            [(cols[0], h - rows[-1] - 1), (cols[-1] + 1, h - rows[0])]
        )
    fig.set_dpi(dpi)
    if corners is None:
        return None
    (x0, y0), (x1, y1) = corners
    return x0, y0, x1, y1


def covers(inner, outer, share: float = 0.9) -> bool:
    """inner 가 outer 의 가로·세로를 모두 share 이상 채우는가."""
    return (inner[2] - inner[0]) >= share * (outer[2] - outer[0]) and (
        inner[3] - inner[1]
    ) >= share * (outer[3] - outer[1])


def render(doc, outputs: list[Path], px: int, hangul_font: str | None) -> None:
    """모델 공간을 긴 변 px 픽셀(PNG 기준) 크기로 그려 outputs 의 형식마다 저장한다."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.lldxf.encoding import decode_mif_to_unicode, has_mif_encoding

    if hangul_font and "KO_HANGUL" not in doc.styles:
        doc.styles.add("KO_HANGUL", font=hangul_font)
    for e in doc.entitydb.values():
        t = e.dxftype()
        if t == "MTEXT":
            txt = e.text
        elif t in ("TEXT", "ATTRIB", "ATTDEF"):
            txt = e.dxf.get("text", "")
        else:
            continue
        # 옛 DWG 의 CP949 한글은 \M+3XXXX 로 나온다. ezdxf 는 읽을 때 풀지만, LibreDWG 가 그 뒤에
        # 실행마다 다른 쓰레기 바이트를 붙이면 못 풀 때가 있어 여기서 한 번 더 푼다
        if has_mif_encoding(txt):
            txt = decode_mif_to_unicode(txt)
            if t == "MTEXT":
                e.text = txt
            else:
                e.dxf.text = txt
        # CAD 의 한글 폰트(SHX 등)가 없으면 한글이 네모로 나오므로 한글이 든 글자만 바꾼다
        if hangul_font and HANGUL.search(txt):
            e.dxf.style = "KO_HANGUL"
    msp = doc.modelspace()
    box = view_box(msp)
    if box is None:
        raise RuntimeError("모델 공간에 그릴 엔티티가 없다")
    fig = plt.figure(dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    cfg = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.BLACK,
        lineweight_scaling=0.7,
    )
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        msp, finalize=True
    )
    # finalize 는 무한선까지 담도록 범위를 잡고 그림 크기도 바꾸므로 다시 정한다
    set_frame(fig, ax, box, px)
    # 범위는 있는데 그려지지 않는 엔티티(DWG 변환에서 깨진 것)가 있으면 그림이 한가운데 작게
    # 몰리므로, 실제로 그려진 곳으로 범위를 좁힌다
    for _ in range(3):
        ink = ink_box(fig, ax)
        if ink is None or covers(ink, box):
            break
        box = ink
        set_frame(fig, ax, box, px)
    for out in outputs:
        tmp = out.with_name(out.name + ".part")  # 중간에 끊겨도 완성본으로 보이지 않게
        fig.savefig(str(tmp), format=out.suffix[1:], dpi=DPI, facecolor="white")
        os.replace(tmp, out)
    plt.close(fig)


def convert_one(
    src: Path,
    base: Path,
    formats: list[str],
    px: int,
    keep_dxf: bool,
    dwg2dxf: Path | None,
    hangul_font: str | None,
) -> str | None:
    """src 하나를 base.<형식> 으로 그린다. 실패하면 이유를 돌려준다."""
    try:
        base.parent.mkdir(parents=True, exist_ok=True)
        outputs = [base.with_name(f"{base.name}.{fmt}") for fmt in formats]
        if src.suffix.lower() == ".dxf":
            from ezdxf import recover

            render(recover.readfile(str(src))[0], outputs, px, hangul_font)
            return None
        with tempfile.TemporaryDirectory() as tmp:
            dxf = (
                base.with_name(base.name + ".dxf")
                if keep_dxf
                else Path(tmp) / (src.stem + ".dxf")
            )
            render(load_dwg(dwg2dxf, src, dxf), outputs, px, hangul_font)
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def collect(inputs: list[Path], out: Path) -> dict[Path, Path]:
    """출력 경로(확장자 없음) -> 입력 파일. 같은 폴더에 같은 이름의 DWG 와 DXF 가 있으면 DWG 를 쓴다.

    출력 폴더 구조는 입력들의 공통 상위 폴더 기준이다. 폴더 하나를 주면 out/<그 폴더 이름>/...,
    파일 하나를 주면 out/<파일 이름>.
    """
    inputs = [p.resolve() for p in inputs]
    top = Path(os.path.commonpath([p.parent for p in inputs]))
    jobs: dict[Path, Path] = {}
    for inp in inputs:
        files = (
            [inp]
            if inp.is_file()
            else sorted(
                p
                for p in inp.rglob("*")
                if p.suffix.lower() in SUFFIXES and p.is_file()
            )
        )
        for f in files:
            base = out / f.relative_to(top).parent / f.stem
            if base in jobs and jobs[base].suffix.lower() == ".dwg":
                continue
            jobs[base] = f
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="DWG·DXF 를 사람이 보는 PDF·PNG 로 바꾼다")
    ap.add_argument("inputs", nargs="+", type=Path, help="DWG·DXF 파일 또는 폴더")
    ap.add_argument(
        "-o", "--out", type=Path, default=DEFAULT_OUT, help=f"기본 {DEFAULT_OUT}"
    )
    ap.add_argument(
        "--format", default="pdf,png", help="pdf, png 중 쉼표로 (기본 둘 다)"
    )
    ap.add_argument(
        "--px", type=int, default=3200, help="PNG 긴 변 픽셀. PDF 는 같은 비율의 벡터"
    )
    ap.add_argument(
        "--keep-dxf", action="store_true", help="DWG 에서 만든 DXF 를 결과 옆에 남긴다"
    )
    ap.add_argument("--force", action="store_true", help="이미 있는 결과도 다시 만든다")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="동시에 처리할 파일 수")
    ap.add_argument("--dwg2dxf", help="dwg2dxf 실행 파일 경로")
    args = ap.parse_args()

    formats = [f.strip().lower() for f in args.format.split(",") if f.strip()]
    if not formats or set(formats) - {"pdf", "png"}:
        ap.error("--format 은 pdf, png 중에서 고른다")
    missing = [str(p) for p in args.inputs if not p.exists()]
    if missing:
        ap.error("입력이 없다: " + ", ".join(missing))

    jobs = collect(args.inputs, args.out)
    todo = {
        base: src
        for base, src in jobs.items()
        if args.force
        or not all(base.with_name(f"{base.name}.{f}").exists() for f in formats)
    }
    print(
        f"도면 {len(jobs)}개 중 {len(todo)}개를 그린다 (이미 있음 {len(jobs) - len(todo)}) -> {args.out}"
    )
    if not todo:
        return 0

    dwg2dxf = None
    if any(src.suffix.lower() == ".dwg" for src in todo.values()):
        dwg2dxf = find_dwg2dxf(args.dwg2dxf)
        if dwg2dxf is None:
            print(
                "dwg2dxf 를 찾지 못했다. Linux 는 scripts/install_libredwg.sh 로 설치하고, "
                "Windows 는 툴킷의 dwg2dxf.exe 를 --dwg2dxf 또는 환경변수 DWG2DXF 로 지정한다.",
                file=sys.stderr,
            )
            return 2
        print(f"dwg2dxf: {dwg2dxf}")
    hangul_font = find_hangul_font()
    if hangul_font is None:
        print(
            "주의: 한글 폰트를 찾지 못해 한글이 네모로 나올 수 있다. "
            f"{', '.join(HANGUL_FONT_FAMILIES)} 중 하나를 설치한다 "
            "(Ubuntu: fonts-noto-cjk). 설치 뒤에는 `uv run ezdxf --fonts` 로 ezdxf 폰트 캐시를 다시 만든다.",
            file=sys.stderr,
        )
    else:
        print(f"한글 폰트: {hangul_font}")

    failures = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(
                convert_one,
                src,
                base,
                formats,
                args.px,
                args.keep_dxf,
                dwg2dxf,
                hangul_font,
            ): (base, src)
            for base, src in todo.items()
        }
        for i, fut in enumerate(as_completed(futures), 1):
            base, src = futures[fut]
            err = fut.result()
            if err:
                failures.append((src, err))
                print(f"[{i}/{len(todo)}] 실패 {src}: {err}", flush=True)
            else:
                print(f"[{i}/{len(todo)}] {base}", flush=True)

    print(f"완료 {len(todo) - len(failures)}, 실패 {len(failures)}")
    for src, err in failures:
        print(f"  {src}: {err}", file=sys.stderr)
    report = (
        args.out / "render_failures.txt"
    )  # 이번 실행에서 실패한 도면 (없으면 지운다)
    if failures:
        report.write_text(
            "".join(f"{src}\t{err}\n" for src, err in sorted(failures)),
            encoding="utf-8",
        )
        print(f"실패 목록: {report}")
    elif report.exists():
        report.unlink()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
