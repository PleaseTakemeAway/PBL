"""
docs/data/synthetic.md 의 그림을 그린다. 옛 데이터(동료 생성기)와 새 생성기(scripts/build_synthetic.py)의 차이.

    PYTHONPATH=. uv run python scripts/synthetic_figures.py [--out docs/data/synthetic]

그림의 숫자는 옛 label.json 과 새 생성기의 식에서 계산한다. 데이터 폴더는 읽지 않는다.
  press_profile.png  press_formed_0027 단면: 옛 원호 + 직선부, 새 2:1 반타원
  cone_sector.png    cone_0019 전개 부채꼴: 옛 각도와 새 각도, 바깥 호 길이와 원둘레
"""

import argparse
import importlib.util
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc, Wedge  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "build_synthetic", ROOT / "scripts" / "build_synthetic.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def press_profile(out: Path):
    """press_formed_0027 (외경 200, t 6). 옛 도면: 반지름 125 원호 + 높이 15 직선부. 새 도면: 반축 100, 50 타원."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    # 옛 도면 (DXF 에서 읽은 값: 원호 중심 (100, -60), 반지름 125, 직선부 0..15)
    ax = axes[0]
    ax.plot([0, 200], [0, 0], "k")
    ax.plot([0, 0], [0, 15], "k")
    ax.plot([200, 200], [0, 15], "k")
    ax.add_patch(Arc((100, -60), 250, 250, theta1=36.87, theta2=143.13, color="k"))
    ax.add_patch(
        Arc((100, -60), 238, 238, theta1=37.82, theta2=142.18, color="k", ls="--")
    )
    ax.plot([6, 6], [0, 15], "k--")
    ax.plot([194, 194], [0, 15], "k--")
    for x, sign in ((0, 1), (200, -1)):
        ax.annotate(
            "37° 꺾임",
            (x, 15),
            (x + sign * 30, 40),
            arrowprops={"arrowstyle": "->", "color": "red"},
            color="red",
            ha="center",
        )
    ax.annotate(
        "안쪽 선 2 mm 떨어짐",
        (6, 14),
        (45, -18),
        arrowprops={"arrowstyle": "->", "color": "red"},
        color="red",
    )
    ax.set_title("옛 도면: 원호(R125) + 직선부 15, 높이 65")
    # 새 도면
    ax = axes[1]
    ax.plot([0, 200], [0, 0], "k")
    u = [math.pi * i / 200 for i in range(201)]
    ax.plot([100 + 100 * math.cos(v) for v in u], [50 * math.sin(v) for v in u], "k")
    ax.plot([100 + 94 * math.cos(v) for v in u], [44 * math.sin(v) for v in u], "k--")
    ax.set_title("새 도면: 2:1 반타원 (반축 100, 50), 높이 50")
    for ax in axes:
        ax.set_aspect("equal")
        ax.set_xlim(-25, 225)
        ax.set_ylim(-25, 75)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out / "press_profile.png", dpi=110)
    plt.close(fig)


def cone_sector(out: Path):
    """cone_0019. 부채꼴을 말면 바깥 호가 콘 큰 쪽 원이 된다. 호 길이 = 원둘레 여야 닫힌다."""
    old = {"r1": 456.21, "r2": 304.14, "theta": 19.73}
    fp = gen.cone_blank(
        {
            "large_outer_diameter": 150,
            "small_outer_diameter": 100,
            "height": 150,
            "thickness": 4,
        }
    )
    new = {
        "r1": fp["sector_outer_radius"],
        "r2": fp["sector_inner_radius"],
        "theta": fp["sector_angle_deg"],
    }
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, s, title, need in (
        (axes[0], old, "옛 정답", 2 * math.pi * 75),
        (axes[1], new, "새 정답 (회사 식)", math.pi * fp["mean_diameters"][0]),
    ):
        a0 = 90 - s["theta"] / 2
        ax.add_patch(
            Wedge(
                (0, 0),
                s["r1"],
                a0,
                a0 + s["theta"],
                width=s["r1"] - s["r2"],
                fc="#dde",
                ec="k",
            )
        )
        arc = s["r1"] * math.radians(s["theta"])
        ax.set_title(
            f"{title}: R1 {s['r1']:.2f}, R2 {s['r2']:.2f}, θ {s['theta']:.2f}°\n"
            f"바깥 호 길이 {arc:.1f}  /  감아야 할 원둘레 {need:.1f}"
        )
        ax.set_aspect("equal")
        ax.set_xlim(-300, 300)
        ax.set_ylim(250, 470)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out / "cone_sector.png", dpi=110)
    plt.close(fig)


def use_hangul_font():
    """한글 글꼴을 쓴다. mlic 에는 시스템 한글 폰트가 없어 ~/.local/share/fonts/nanum/ 의 나눔고딕을 직접 등록한다
    (AGENTS.md 6절)."""
    from matplotlib import font_manager

    for path in sorted(
        (Path.home() / ".local/share/fonts").glob("**/NanumGothic*.ttf")
    ):
        font_manager.fontManager.addfont(str(path))
    names = {f.name for f in font_manager.fontManager.ttflist}
    for name in (
        "NanumGothic",
        "Noto Sans CJK KR",
        "Malgun Gothic",
        "Apple SD Gothic Neo",
    ):
        if name in names:
            plt.rcParams["font.family"] = [
                name,
                "DejaVu Sans",
            ]  # θ 같은 기호는 DejaVu 로
            return


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "data" / "synthetic")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    use_hangul_font()
    press_profile(args.out)
    cone_sector(args.out)
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
