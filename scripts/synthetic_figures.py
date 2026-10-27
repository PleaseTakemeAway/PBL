"""
docs/data/synthetic.md 의 그림을 그린다. 옛 데이터(동료 생성기)와 새 생성기(scripts/build_synthetic.py)의 차이.

    PYTHONPATH=. uv run python scripts/synthetic_figures.py [--out docs/data/synthetic]

그림의 숫자는 옛 label.json 과 새 생성기의 식에서 계산한다. 데이터 폴더는 읽지 않는다.
  press_profile.png  press_formed_0027 단면: 옛 원호 + 직선부, 새 2:1 반타원
  cone_sector.png    cone_0019 전개 부채꼴: 옛 각도와 새 각도, 바깥 호 길이와 원둘레
  head_blank.png     현업자 HEAD: 원판 지름 = 두께 가운데 선의 길이 (계산 문서 1.2 × Dm 과 비교)
  cone_wall.png      현업자 CONE: 판 두께를 끝면에서 가로로 재면 t / cos α
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
    """press_formed_0027 (외경 200, t 6). 옛 도면: 반지름 125 원호 + 높이 15 직선부. 새 도면: 안쪽 반축 94, 47 타원."""
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
    ax.plot([100 + 100 * math.cos(v) for v in u], [53 * math.sin(v) for v in u], "k")
    ax.plot([100 + 94 * math.cos(v) for v in u], [47 * math.sin(v) for v in u], "k--")
    ax.set_title("새 도면: 안쪽 2:1 반타원 (반축 94, 47), 높이 53")
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


def head_blank(out: Path):
    """현업자 HEAD (안지름 1000, t 20, 직선부 30). 원판을 눌러 헤드를 만들 때 길이가 변하지 않는 것은 두께 가운데
    선이다. 그래서 원판 반지름 = 꼭대기에서 끝까지의 그 선의 길이, 원판 지름 = 끝에서 끝까지의 길이다."""
    sf, t, di = 30, 20, 1000
    a, b = di / 2, di / 4
    arc = gen.half_ellipse_length(a + t / 2, b + t / 2)
    blank, approx = arc + 2 * sf, 1.2 * (di + t) + 2 * sf
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axes[0]
    u = [math.pi * i / 200 for i in range(201)]
    for (aa, bb), style in (((a, b), "k--"), ((a + t, b + t), "k-")):
        xs = [aa * math.cos(v) for v in u]
        ys = [sf + bb * math.sin(v) for v in u]
        ax.plot([xs[0], xs[0]], [0, sf], style[0] + style[1:])
        ax.plot([xs[-1], xs[-1]], [0, sf], style[0] + style[1:])
        ax.plot(xs, ys, style)
    xs = [(a + t / 2) * math.cos(v) for v in u]
    ys = [sf + (b + t / 2) * math.sin(v) for v in u]
    mid = "#c33"
    ax.plot(xs, ys, color=mid, lw=2.5)
    ax.plot([xs[0], xs[0]], [0, sf], color=mid, lw=2.5)
    ax.plot([xs[-1], xs[-1]], [0, sf], color=mid, lw=2.5)
    ax.axhline(sf, color="#999", lw=0.6, ls=":")
    ax.text(a + t + 15, sf, "TL", va="center", color="#666")
    ax.text(
        0,
        sf + b + t + 30,
        f"빨간 선 = 두께 가운데\n직선부 {sf} + 반타원 {arc:.1f} + 직선부 {sf} = {blank:.1f}",
        ha="center",
        color=mid,
    )
    ax.set_title("HEAD 단면 (안지름 1000, t 20, 직선부 30)")
    ax.set_aspect("equal")
    ax.set_xlim(-620, 620)
    ax.set_ylim(-40, 420)
    ax.axis("off")
    ax = axes[1]
    from matplotlib.patches import Circle

    ax.add_patch(Circle((0, 0), blank / 2, fc="#f3dede", ec=mid, lw=2))
    ax.add_patch(Circle((0, 0), approx / 2, fc="none", ec="k", ls="--"))
    ax.plot([0, blank / 2], [0, 0], color=mid)
    ax.text(
        blank / 4,
        15,
        f"반지름 {blank / 2:.1f}\n= 꼭대기에서 끝까지",
        ha="center",
        va="bottom",
        color=mid,
    )
    ax.set_title(
        f"원판: 현업자 정답 Ø{blank:.1f} (빨강)\n계산 문서 약산식 1.2 × 1020 + 60 = Ø{approx:.1f} (점선, {approx / blank - 1:+.2%})"
    )
    ax.set_aspect("equal")
    ax.set_xlim(-700, 700)
    ax.set_ylim(-700, 700)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out / "head_blank.png", dpi=110)
    plt.close(fig)


def cone_wall(out: Path):
    """현업자 CONE 의 큰 쪽 끝 (안지름 1000, t 20, 반각 30°). 판 두께 20 은 벽에 수직이고, 끝면에서 가로로는
    20 / cos 30° = 23.09 다. 평균지름은 가로로 잰 두께의 가운데: 1000 + 23.09 = 1023.09."""
    t, alpha = 20, math.radians(30)
    across = t / math.cos(alpha)
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    L = 120  # 그림에 보이는 벽 길이
    dx, dy = -math.sin(alpha) * L, math.cos(alpha) * L  # 벽을 따라 위로 (작은 쪽으로)
    x_in = 0.0
    for x0, style in ((x_in, "k-"), (x_in + across, "k-")):
        ax.plot([x0, x0 + dx], [0, dy], style)
    ax.plot([x_in, x_in + across], [0, 0], "k-", lw=1)
    ax.plot([x_in + across / 2, x_in + across / 2 + dx], [0, dy], color="#c33", ls="--")
    nx, ny = math.cos(alpha), math.sin(alpha)  # 벽에 수직
    px, py = x_in + dx / 2, dy / 2
    ax.annotate(
        "", (px + nx * t, py + ny * t), (px, py), arrowprops={"arrowstyle": "<->"}
    )
    ax.text(px - 30, py, "t = 20\n(벽에 수직)", ha="right", va="center")
    ax.annotate(
        "",
        (x_in + across, -6),
        (x_in, -6),
        arrowprops={"arrowstyle": "<->", "color": "#c33"},
    )
    ax.text(
        x_in + across / 2,
        -16,
        f"가로 {across:.2f} = 20 / cos 30°",
        ha="center",
        va="top",
        color="#c33",
    )
    ax.text(x_in - 12, 2, "안지름 끝\n(반지름 500)", ha="right", va="center")
    ax.set_title("CONE 큰 쪽 끝: 평균지름 = 1000 + 23.09 = 1023.09")
    ax.set_aspect("equal")
    ax.set_xlim(-110, 60)
    ax.set_ylim(-35, 115)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out / "cone_wall.png", dpi=110)
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
    head_blank(args.out)
    cone_wall(args.out)
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
