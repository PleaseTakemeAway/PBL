"""
reader 평가용 합성 도면 30장(형상 5종 × 6장)을 DXF·PNG·label.json 으로 만든다.

    PYTHONPATH=. uv run python scripts/build_synthetic.py [--out data_v3/generated] [--compare data_v3/synthetic]
        [--only <id 일부>] [--no-png] [-q]

도면 1장에는 부품 하나를 3면도(3각법, 정면도·평면도·우측면도)로 그리고 A3 틀과 표제란을 넣는다.
정답(label.json)의 전개 값은 회사 기준으로 계산한다. 회사 현업자가 그려 준 정답 전개도(data_v3/20261027example,
2026-10-27)가 계산 문서와 다른 곳은 현업자 정답을 따른다 (docs/v3_upgrade.md 5절).

  - 원통: skills/01_core_knowledge/shell_cone_head_unfold.md 2.1 (평균지름 = 외경 − 두께)
  - 콘: 같은 문서 3.1.1. 평균지름은 끝면에서 가로로 잰다: 외경 − t / cos α (현업자 정답)
  - 헤드: 두께 가운데 반타원의 길이 + 2 × 직선부 (현업자 정답. 계산 문서 4.2 의 1.2 × Dm 대신)
  - 굽힘판 K 계수: skills/01_core_knowledge/unfold_rules.md 30행

식은 이 파일에 직접 썼다. reader(cutplan_agent/reader/unfold.py)의 식을 가져다 쓰지 않는다. 그래야 reader 와
정답이 같은 실수를 해도 서로 맞아 보이는 일이 없다. PNG 만 reader 의 렌더러로 그린다.

출력:
  <out>/<id>/<id>.dxf      도면 (R2000, mm)
  <out>/<id>/<id>.png      도면 그림 (reader 렌더러, 선 종류는 그리지 않는다)
  <out>/<id>/label.json    정답. 키는 docs/data/synthetic.md 3절
  <out>/index.csv          도면마다 형상, 주요 치수, 전개 값
  <out>/compare.md         --compare 를 주면 옛 정답과 전개 값을 나란히 적은 표

같은 입력이면 DXF·label.json 은 매번 바이트까지 같다. 옛 데이터(동료 생성기, data_v3/synthetic)에서 무엇이 왜
바뀌었는지는 docs/data/synthetic.md 에 있다.
"""

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

# ----------------------------------------------------------------------------- 도면 30장
# 형상·치수·재질·축척은 옛 데이터(data_v3/synthetic)와 같다. 바뀐 것은 그리는 법과 정답 식이다.
# press_formed 는 2:1 반타원 헤드로 바꾸면서 직선부(flange)와 크라운 높이를 뺐다. 2:1 은 안쪽 면 기준이다
# (안쪽 깊이 = 안지름/4, 높이 = 안지름/4 + t).
# 구멍: (축, 지름, (x, y, z)) — 중심은 부품 좌표(mm). 축 z 는 수평판, 축 x 는 수직판(굽힘판의 세운 쪽)을 뚫는다.
SPECS: list[dict] = [
    # flat: length(x), width(y), thickness(z)
    dict(id="flat_0001", cls="flat", p=dict(length=100, width=120, thickness=9),
         holes=[("z", 13, (25, 60, 4.5)), ("z", 13, (75, 60, 4.5))], mat="SUS304", scale=2),
    dict(id="flat_0002", cls="flat", p=dict(length=80, width=120, thickness=2),
         holes=[("z", 13, (25, 15, 1)), ("z", 13, (25, 105, 1)), ("z", 13, (55, 15, 1)),
                ("z", 13, (55, 105, 1))], mat="SPCC", scale=2),
    dict(id="flat_0003", cls="flat", p=dict(length=220, width=100, thickness=9),
         holes=[("z", 13.7, (25, 15, 4.5)), ("z", 13.7, (25, 85, 4.5)), ("z", 13.7, (195, 15, 4.5)),
                ("z", 13.7, (195, 85, 4.5))], mat="SPCC", scale=2),
    dict(id="flat_0004", cls="flat", p=dict(length=220, width=60, thickness=9),
         holes=[("z", 18, (15, 25, 4.5)), ("z", 18, (15, 35, 4.5)), ("z", 18, (205, 25, 4.5)),
                ("z", 18, (205, 35, 4.5))], mat="SS400", scale=2),
    dict(id="flat_0005", cls="flat", p=dict(length=100, width=120, thickness=2),
         holes=[("z", 9, (20, 60, 1)), ("z", 9, (80, 60, 1))], mat="SUS304", scale=2),
    dict(id="flat_0006", cls="flat", p=dict(length=220, width=100, thickness=12),
         holes=[("z", 13.7, (25, 25, 6)), ("z", 13.7, (25, 75, 6)), ("z", 13.7, (195, 25, 6)),
                ("z", 13.7, (195, 75, 6))], mat="SA516-70", scale=2),
    # bent_sheet: L 자 90° 굽힘. leg_a = 수평판 바깥 길이(x), leg_b = 수직판 바깥 높이(z), width(y),
    # bend_radius = 안쪽 굽힘 반경
    dict(id="bent_sheet_0007", cls="bent_sheet",
         p=dict(leg_a=100, leg_b=100, width=30, thickness=2, bend_radius=0),
         holes=[("x", 11, (1, 15, 80)), ("x", 11, (1, 15, 20))], mat="SA516-70", scale=2),
    dict(id="bent_sheet_0008", cls="bent_sheet",
         p=dict(leg_a=120, leg_b=150, width=100, thickness=6, bend_radius=0),
         holes=[("x", 13, (3, 35, 130)), ("x", 13, (3, 65, 130)), ("x", 13, (3, 35, 70)),
                ("x", 13, (3, 65, 70)), ("z", 13, (100, 35, 3)), ("z", 13, (100, 65, 3)),
                ("z", 13, (40, 35, 3)), ("z", 13, (40, 65, 3))], mat="SS400", scale=2),
    dict(id="bent_sheet_0009", cls="bent_sheet",
         p=dict(leg_a=120, leg_b=220, width=60, thickness=3, bend_radius=0),
         holes=[("z", 15, (100, 15, 1.5)), ("z", 15, (100, 45, 1.5)), ("z", 15, (60, 15, 1.5)),
                ("z", 15, (60, 45, 1.5))], mat="SUS304", scale=2),
    dict(id="bent_sheet_0010", cls="bent_sheet",
         p=dict(leg_a=120, leg_b=100, width=30, thickness=2, bend_radius=0),
         holes=[], mat="SS400", scale=2),
    dict(id="bent_sheet_0011", cls="bent_sheet",
         p=dict(leg_a=120, leg_b=60, width=40, thickness=6, bend_radius=0),
         holes=[("x", 9, (3, 20, 40))], mat="SS400", scale=1),
    dict(id="bent_sheet_0012", cls="bent_sheet",
         p=dict(leg_a=80, leg_b=220, width=80, thickness=2, bend_radius=0),
         holes=[("x", 15, (1, 25, 200)), ("x", 15, (1, 55, 200)), ("x", 15, (1, 25, 140)),
                ("x", 15, (1, 55, 140)), ("z", 15, (60, 25, 1)), ("z", 15, (60, 55, 1))],
         mat="SS400", scale=2),
    # cylinder: 축 x. outer_diameter, length(x), thickness
    dict(id="cylinder_0013", cls="cylinder", p=dict(outer_diameter=100, length=100, thickness=3),
         holes=[], mat="SS400", scale=2),
    dict(id="cylinder_0014", cls="cylinder", p=dict(outer_diameter=200, length=400, thickness=3),
         holes=[], mat="SPCC", scale=4),
    dict(id="cylinder_0015", cls="cylinder", p=dict(outer_diameter=150, length=200, thickness=6),
         holes=[], mat="SPCC", scale=2),
    dict(id="cylinder_0016", cls="cylinder", p=dict(outer_diameter=300, length=100, thickness=6),
         holes=[], mat="SPHC", scale=4),
    dict(id="cylinder_0017", cls="cylinder", p=dict(outer_diameter=100, length=150, thickness=9),
         holes=[], mat="SA516-70", scale=2),
    dict(id="cylinder_0018", cls="cylinder", p=dict(outer_diameter=150, length=400, thickness=9),
         holes=[], mat="SUS304", scale=4),
    # cone: 축 z, 큰 쪽이 아래. large/small_outer_diameter, height, thickness
    dict(id="cone_0019", cls="cone",
         p=dict(large_outer_diameter=150, small_outer_diameter=100, height=150, thickness=4),
         holes=[], mat="SPCC", scale=2),
    dict(id="cone_0020", cls="cone",
         p=dict(large_outer_diameter=300, small_outer_diameter=200, height=200, thickness=4),
         holes=[], mat="SPHC", scale=4),
    dict(id="cone_0021", cls="cone",
         p=dict(large_outer_diameter=300, small_outer_diameter=200, height=80, thickness=4),
         holes=[], mat="SPHC", scale=4),
    dict(id="cone_0022", cls="cone",
         p=dict(large_outer_diameter=150, small_outer_diameter=100, height=200, thickness=6),
         holes=[], mat="SPCC", scale=4),
    dict(id="cone_0023", cls="cone",
         p=dict(large_outer_diameter=150, small_outer_diameter=80, height=150, thickness=4),
         holes=[], mat="SPHC", scale=2),
    dict(id="cone_0024", cls="cone",
         p=dict(large_outer_diameter=300, small_outer_diameter=200, height=200, thickness=3),
         holes=[], mat="SS400", scale=4),
    # press_formed: 2:1 반타원 헤드, 축 z, 열린 쪽이 아래. outer_diameter, thickness
    dict(id="press_formed_0025", cls="press_formed", p=dict(outer_diameter=150, thickness=6),
         holes=[], mat="SA516-70", scale=2),
    dict(id="press_formed_0026", cls="press_formed", p=dict(outer_diameter=300, thickness=6),
         holes=[], mat="SPHC", scale=4),
    dict(id="press_formed_0027", cls="press_formed", p=dict(outer_diameter=200, thickness=6),
         holes=[], mat="SUS304", scale=2),
    dict(id="press_formed_0028", cls="press_formed", p=dict(outer_diameter=300, thickness=6),
         holes=[], mat="SS400", scale=4),
    dict(id="press_formed_0029", cls="press_formed", p=dict(outer_diameter=150, thickness=4),
         holes=[], mat="SUS304", scale=2),
    dict(id="press_formed_0030", cls="press_formed", p=dict(outer_diameter=200, thickness=6),
         holes=[], mat="SPHC", scale=2),
]  # fmt: skip

# ----------------------------------------------------------------------------- 정답 식


def mean_diameter(outer: float, t: float) -> float:
    """평균지름 = 외경 − 두께. 판을 말거나 성형해도 길이가 변하지 않는 곳은 두께 중앙(중립면)이다
    (shell_cone_head_unfold.md 1.1)."""
    return outer - t


def k_factor(r: float, t: float) -> float:
    """굽힘 K 계수: R/t < 1 이면 0.33, 1~3 이면 0.40, 3 이상이면 0.50 (unfold_rules.md 30행)."""
    ratio = r / t
    return 0.33 if ratio < 1 else (0.40 if ratio < 3 else 0.50)


def flat_blank(p: dict) -> dict:
    return {
        "formula": "판 그대로: length × width",
        "length": p["length"],
        "width": p["width"],
    }


def bent_blank(p: dict) -> dict:
    """90° 굽힘 1곳. 바깥 치수에서 직선부 = 바깥 길이 − (R + t), 굽힘부 BA = (π/2)(R + K·t).
    전개 길이 = 두 직선부 + BA. 굽힘선은 굽힘부의 가운데다 (unfold_rules.md 30행: setback = (R+t)·tan45°)."""
    a, b, t, r = p["leg_a"], p["leg_b"], p["thickness"], p["bend_radius"]
    k = k_factor(r, t)
    ba = math.pi / 2 * (r + k * t)
    straight_a, straight_b = a - (r + t), b - (r + t)
    return {
        "formula": "L = (leg_a − (R+t)) + (leg_b − (R+t)) + (π/2)(R + K·t)",
        "k_factor": k,
        "bend_allowance": round(ba, 3),
        "length": round(straight_a + straight_b + ba, 2),
        "width": p["width"],
        "bend_lines": [round(straight_a + ba / 2, 2)],
    }


def cylinder_blank(p: dict) -> dict:
    """원통 쉘: 전개 길이 = π × 평균지름, 폭 = 원통 길이 (shell_cone_head_unfold.md 2.1)."""
    dm = mean_diameter(p["outer_diameter"], p["thickness"])
    return {
        "formula": "length = π × Dm, Dm = OD − t; width = 원통 길이",
        "mean_diameter": dm,
        "length": round(math.pi * dm, 2),
        "width": p["length"],
    }


def cone_blank(p: dict) -> dict:
    """동심 콘: 평균지름 D1, D2 와 높이 H 로 sin α = (D1 − D2) / 2S, R1 = D1 / (2 sin α),
    R2 = D2 / (2 sin α), θ = 360° × sin α (shell_cone_head_unfold.md 3.1.1).
    평균지름은 끝면에서 가로로 잰 두께 가운데다. 판 두께 t 는 면에 수직이라 가로로는 t / cos α 이고,
    평균지름 = 외경 − t / cos α 다 (현업자 정답 CONE: 안지름 1000, t 20, α 30° → D1 = 1023.09).
    검산: 바깥 호 길이 R1·θ = π·D1 (콘 대경 쪽 평균 원둘레)."""
    t, h = p["thickness"], p["height"]
    big, small = p["large_outer_diameter"], p["small_outer_diameter"]
    across = t / math.cos(math.atan((big - small) / 2 / h))  # 가로로 잰 판 두께
    d1, d2 = big - across, small - across
    s = math.hypot(h, (d1 - d2) / 2)
    sin_a = (d1 - d2) / (2 * s)
    r1, r2 = d1 / (2 * sin_a), d2 / (2 * sin_a)
    theta = 360 * sin_a
    assert abs(r1 * math.radians(theta) - math.pi * d1) < 1e-6
    return {
        "formula": "D = OD − t/cos α; sin α = (D1 − D2)/2S, R1 = D1/(2 sin α), R2 = D2/(2 sin α), θ = 360° sin α",
        "mean_diameters": [round(d1, 3), round(d2, 3)],
        "slant": round(s, 2),
        "sector_outer_radius": round(r1, 2),
        "sector_inner_radius": round(r2, 2),
        "sector_angle_deg": round(theta, 2),
    }


def half_ellipse_length(a: float, b: float, n: int = 20000) -> float:
    """반축 a, b 인 타원의 반 둘레. ds = √(a² sin² u + b² cos² u) du 를 u = 0..π 에서 중점법으로 적분한다."""
    du = math.pi / n
    return du * sum(
        math.hypot(a * math.sin((i + 0.5) * du), b * math.cos((i + 0.5) * du))
        for i in range(n)
    )


def head_blank(p: dict) -> dict:
    """2:1 반타원 헤드 원판 지름 = 두께 가운데 반타원의 길이(꼭대기를 지나 한쪽 끝에서 반대쪽 끝까지) + 2 × 직선부.
    현업자 정답 HEAD (안지름 1000, t 20, 직선부 30): 반축 510, 260 → 1241.6 + 30 + 30 = 1301.6.
    두께 가운데 타원은 안쪽 타원(반축 ID/2, ID/4)에서 t/2 바깥이다. 이 도면들은 직선부가 없어 + 2·SF 는 0 이고,
    트림 여유는 넣지 않는다. 계산 문서 4.2 의 약산식 1.2 × Dm 과의 차이는 docs/v3_upgrade.md 5절."""
    t = p["thickness"]
    di = p["outer_diameter"] - 2 * t
    a, b = (di + t) / 2, di / 4 + t / 2
    arc = half_ellipse_length(a, b)
    return {
        "formula": "Db = 두께 가운데 반타원의 길이 + 2 × SF, 반축 (ID + t)/2, ID/4 + t/2 (직선부 없음, 트림 여유 없음)",
        "mean_diameter": di + t,
        "meridian_length": round(arc, 2),
        "blank_diameter": round(arc, 2),
    }


# ----------------------------------------------------------------------------- 3면도


@dataclass
class View:
    """한 뷰의 선. 좌표는 부품 mm, 원점은 뷰 바운딩 박스의 왼쪽 아래."""

    width: float
    height: float
    prims: list[tuple] = field(default_factory=list)
    holes: list[float] = field(default_factory=list)  # 이 뷰에 원으로 보이는 구멍 지름

    def line(self, layer, p, q):
        self.prims.append(("line", layer, p, q))

    def rect(self, layer, x0, y0, x1, y1):
        for p, q in (
            ((x0, y0), (x1, y0)),
            ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)),
            ((x0, y1), (x0, y0)),
        ):
            self.line(layer, p, q)

    def circle(self, layer, c, r):
        self.prims.append(("circle", layer, c, r))

    def arc(self, layer, c, r, a0, a1):
        self.prims.append(("arc", layer, c, r, a0, a1))

    def ellipse(self, layer, c, a, b, u0, u1):
        """가로 반축 a, 세로 반축 b 인 타원의 매개변수 u0..u1 (라디안) 구간."""
        self.prims.append(("ellipse", layer, c, a, b, u0, u1))

    def hole(self, c, d, cross):
        """원으로 보이는 구멍과 중심선 십자."""
        self.circle("OUTLINE", c, d / 2)
        self.cross(c, d / 2 + cross)
        self.holes.append(d)

    def cross(self, c, half):
        self.line("CENTER", (c[0] - half, c[1]), (c[0] + half, c[1]))
        self.line("CENTER", (c[0], c[1] - half), (c[0], c[1] + half))

    def dedup(self):
        """같은 선이 두 번 들어가지 않게 한다. 구멍 여러 개가 옆에서 겹쳐 보일 때 생긴다."""
        seen, out = set(), []
        for pr in self.prims:
            key = tuple(
                tuple(round(v, 6) for v in x) if isinstance(x, tuple) else x for x in pr
            )
            if pr[0] == "line":  # 방향만 다른 같은 선
                key = (pr[0], pr[1], *sorted([key[2], key[3]]))
            if key not in seen:
                seen.add(key)
                out.append(pr)
        self.prims = out


def hidden_hole(
    view: View, along_x: bool, at: float, d: float, lo: float, hi: float, ext
):
    """옆에서 본 관통 구멍: 숨은선 두 줄과 중심선. along_x 이면 구멍 축이 뷰의 가로 방향이다."""
    for off in (-d / 2, d / 2):
        if along_x:
            view.line("HIDDEN", (lo, at + off), (hi, at + off))
        else:
            view.line("HIDDEN", (at + off, lo), (at + off, hi))
    if along_x:
        view.line("CENTER", (lo - ext, at), (hi + ext, at))
    else:
        view.line("CENTER", (at, lo - ext), (at, hi + ext))


def draw_flat(p, holes, k):
    L, W, t = p["length"], p["width"], p["thickness"]
    ext, cross = 1.5 * k, 1.5 * k
    front, top, right = View(L, t), View(L, W), View(W, t)
    for v in (front, top, right):
        v.rect("OUTLINE", 0, 0, v.width, v.height)
    for _, d, (x, y, _z) in holes:
        top.hole((x, y), d, cross)
        hidden_hole(front, False, x, d, 0, t, ext)
        hidden_hole(right, False, y, d, 0, t, ext)
    return {"front": front, "top": top, "right": right}, (L, W, t)


def draw_bent(p, holes, k):
    """L 자 굽힘판. 정면도에서 수평판은 아래(z 0..t), 수직판은 왼쪽(x 0..t)이다. 바깥 모서리는 반경 R + t 의
    호, 안쪽 모서리는 반경 R 의 호다 (R = 0 이면 안쪽은 꺾인 모서리)."""
    a, b, W = p["leg_a"], p["leg_b"], p["width"]
    t, r = p["thickness"], p["bend_radius"]
    ext, cross = 1.5 * k, 1.5 * k
    c = (r + t, r + t)  # 굽힘 중심
    front = View(a, b)
    front.line("OUTLINE", (c[0], 0), (a, 0))
    front.line("OUTLINE", (a, 0), (a, t))
    front.line("OUTLINE", (a, t), (c[0], t))
    front.line("OUTLINE", (t, c[1]), (t, b))
    front.line("OUTLINE", (t, b), (0, b))
    front.line("OUTLINE", (0, b), (0, c[1]))
    front.arc("OUTLINE", c, r + t, 180, 270)
    if r > 0:
        front.arc("OUTLINE", c, r, 180, 270)
    top = View(a, W)
    top.rect("OUTLINE", 0, 0, a, W)
    top.line("OUTLINE", (t, 0), (t, W))  # 수직판 안쪽 면과 수평판 윗면이 만나는 모서리
    right = View(W, b)
    right.rect("OUTLINE", 0, 0, W, b)
    right.line("OUTLINE", (0, t), (W, t))  # 수평판 윗면 (끝에서 보면 선)
    for axis, d, (x, y, z) in holes:
        if axis == "z":  # 수평판
            top.hole((x, y), d, cross)
            hidden_hole(front, False, x, d, 0, t, ext)
            hidden_hole(right, False, y, d, 0, t, ext)
        else:  # 수직판
            right.hole((y, z), d, cross)
            hidden_hole(front, True, z, d, 0, t, ext)
            hidden_hole(top, True, y, d, 0, t, ext)  # 위에서 보면 수직판 두께 안
    return {"front": front, "top": top, "right": right}, (a, W, b)


def draw_cylinder(p, holes, k):
    """축 x. 정면도와 평면도는 같은 직사각형(안지름은 숨은선), 우측면도는 끝에서 본 두 원."""
    od, L, t = p["outer_diameter"], p["length"], p["thickness"]
    ext = 2.5 * k
    views = {}
    for name in ("front", "top"):
        v = View(L, od)
        v.rect("OUTLINE", 0, 0, L, od)
        v.line("HIDDEN", (0, t), (L, t))
        v.line("HIDDEN", (0, od - t), (L, od - t))
        v.line("CENTER", (-ext, od / 2), (L + ext, od / 2))
        views[name] = v
    right = View(od, od)
    right.circle("OUTLINE", (od / 2, od / 2), od / 2)
    right.circle(
        "OUTLINE", (od / 2, od / 2), od / 2 - t
    )  # 끝에서 보면 안쪽 모서리도 보인다
    right.cross((od / 2, od / 2), od / 2 + ext)
    views["right"] = right
    return views, (L, od, od)


def draw_cone(p, holes, k):
    """축 z, 큰 쪽이 아래. 판 두께 t 는 면에 수직이라 안쪽 면은 가로로 t / cos α 만큼 안에 있다.
    평면도에서 위쪽 열린 끝의 안쪽 모서리는 보이고, 아래쪽 안쪽 모서리는 판에 가려 숨은선이다."""
    D, d, H, t = (
        p["large_outer_diameter"],
        p["small_outer_diameter"],
        p["height"],
        p["thickness"],
    )
    R, r = D / 2, d / 2
    off = t / math.cos(math.atan((R - r) / H))  # 안쪽 면까지의 가로 거리
    ext = 2.5 * k
    views = {}
    for name in ("front", "right"):
        v = View(D, H)
        v.line("OUTLINE", (0, 0), (D, 0))
        v.line("OUTLINE", (D, 0), (R + r, H))
        v.line("OUTLINE", (R + r, H), (R - r, H))
        v.line("OUTLINE", (R - r, H), (0, 0))
        v.line("HIDDEN", (off, 0), (R - r + off, H))
        v.line("HIDDEN", (D - off, 0), (R + r - off, H))
        v.line("CENTER", (R, -ext), (R, H + ext))
        views[name] = v
    top = View(D, D)
    top.circle("OUTLINE", (R, R), R)
    top.circle("OUTLINE", (R, R), r)
    top.circle("OUTLINE", (R, R), r - off)
    top.circle("HIDDEN", (R, R), R - off)
    top.cross((R, R), R + ext)
    views["top"] = top
    return views, (D, D, H)


def draw_head(p, holes, k):
    """2:1 반타원 헤드, 열린 쪽이 아래. 2:1 은 안쪽 면 기준이다 (현업자 도면 HEAD 와 같다): 안쪽 면은 반축
    ID/2, ID/4 인 타원이다. 바깥 면은 반축을 t 씩 늘린 타원으로 그린다 (타원을 t 만큼 평행 이동한 곡선은 타원이
    아니어서 이렇게 그린다. 꼭대기와 양 끝에서는 정확하다). 직선부는 없다."""
    od, t = p["outer_diameter"], p["thickness"]
    a, b = od / 2 - t, (od - 2 * t) / 4  # 안쪽 반축
    ext = 2.5 * k
    views = {}
    for name in ("front", "right"):
        v = View(od, b + t)
        v.line("OUTLINE", (0, 0), (od, 0))
        v.ellipse("OUTLINE", (od / 2, 0), a + t, b + t, 0, math.pi)
        v.ellipse("HIDDEN", (od / 2, 0), a, b, 0, math.pi)
        v.line("CENTER", (od / 2, -ext), (od / 2, b + t + ext))
        views[name] = v
    c = (od / 2, od / 2)
    top = View(od, od)
    top.circle("OUTLINE", c, od / 2)
    top.circle("HIDDEN", c, a)
    top.cross(c, od / 2 + ext)
    views["top"] = top
    return views, (od, od, b + t)


SHAPES = {
    "flat": (draw_flat, flat_blank),
    "bent_sheet": (draw_bent, bent_blank),
    "cylinder": (draw_cylinder, cylinder_blank),
    "cone": (draw_cone, cone_blank),
    "press_formed": (draw_head, head_blank),
}

# ----------------------------------------------------------------------------- 용지 배치 (용지 mm)
# 좌표는 모두 용지 mm 이고, 도면에는 축척의 역수 k 를 곱해 부품 mm 로 쓴다 (옛 데이터와 같은 배치).
FRAME = (10, 10, 410, 287)  # A3 가로 420 × 297 에서 여백 10
FRONT_AT = (50, 55)  # 정면도 왼쪽 아래
GAP = 35  # 뷰 사이 간격
DIM_OFFSET = 12  # 외형선에서 치수선까지
TEXT_H = 3.0  # 치수·주기 글자 높이
TICK = 1.2  # 치수 끝 사선 반 길이
TITLE = (290, 10, 410, 50)  # 표제란


def layout(views: dict, k: float) -> dict:
    """3각법: 평면도는 정면도 위, 우측면도는 정면도 오른쪽. 반환은 뷰마다 도면 좌표의 원점."""
    fx, fy = FRONT_AT[0] * k, FRONT_AT[1] * k
    front = views["front"]
    return {
        "front": (fx, fy),
        "top": (fx, fy + front.height + GAP * k),
        "right": (fx + front.width + GAP * k, fy),
    }


def fits(views: dict, origins: dict, k: float) -> bool:
    x1, y1 = FRAME[2] * k, FRAME[3] * k
    tx0, ty1 = TITLE[0] * k, TITLE[3] * k
    for name, v in views.items():
        ox, oy = origins[name]
        right, top = ox + v.width, oy + v.height
        if right > x1 - 10 * k or top > y1 - 10 * k:
            return False
        if right > tx0 and oy < ty1:  # 표제란과 겹침
            return False
    return True


# ----------------------------------------------------------------------------- DXF


def new_document(k: float):
    # 저장할 때마다 바뀌는 값(작성 시각, 문서 GUID)을 고정해 같은 입력이면 같은 파일이 되게 한다
    ezdxf.options.write_fixed_meta_data_for_testing = True
    doc = ezdxf.new("R2000", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    doc.header["$LTSCALE"] = k
    for name, color, ltype in (
        ("OUTLINE", 7, "CONTINUOUS"),
        ("HIDDEN", 4, "HIDDEN"),
        ("CENTER", 1, "CENTER"),
        ("DIM", 3, "CONTINUOUS"),
        ("TEXT", 2, "CONTINUOUS"),
        ("FRAME", 8, "CONTINUOUS"),
        ("TITLE", 8, "CONTINUOUS"),
    ):
        doc.layers.add(name, color=color, linetype=ltype)
    return doc


def put(msp, pr, ox, oy):
    kind, layer = pr[0], pr[1]
    att = {"layer": layer}
    if kind == "line":
        (x0, y0), (x1, y1) = pr[2], pr[3]
        msp.add_line((ox + x0, oy + y0), (ox + x1, oy + y1), dxfattribs=att)
    elif kind == "circle":
        (cx, cy), r = pr[2], pr[3]
        msp.add_circle((ox + cx, oy + cy), r, dxfattribs=att)
    elif kind == "arc":
        (cx, cy), r, a0, a1 = pr[2], pr[3], pr[4], pr[5]
        msp.add_arc((ox + cx, oy + cy), r, a0, a1, dxfattribs=att)
    elif kind == "ellipse":
        (cx, cy), a, b, u0, u1 = pr[2], pr[3], pr[4], pr[5], pr[6]
        msp.add_ellipse(
            (ox + cx, oy + cy),
            major_axis=(a, 0, 0),
            ratio=b / a,
            start_param=u0,
            end_param=u1,
            dxfattribs=att,
        )


def add_dimension(doc, msp, p1, p2, vertical: bool, value: float, k: float):
    """선형 치수 하나. 치수 블록(*D)에 치수선·보조선·끝 사선·글자를 LINE 과 TEXT 로 넣고, DIMENSION 에는
    측정값(group 42)을 적는다. reader 는 둘 다 읽는다 (dxf_reader.py 의 DIMENSION)."""
    off, tick, th = DIM_OFFSET * k, TICK * k, TEXT_H * k
    blk = doc.blocks.new_anonymous_block(type_char="D")
    att = {"layer": "DIM"}
    if vertical:
        x = p1[0] - off
        a, b = (x, p1[1]), (x, p2[1])
        blk.add_line(a, b, dxfattribs=att)
        blk.add_line(p1, a, dxfattribs=att)
        blk.add_line(p2, b, dxfattribs=att)
        mid = (x - 0.6 * th - th / 2, (p1[1] + p2[1]) / 2)
        rot = 90
    else:
        y = p1[1] - off
        a, b = (p1[0], y), (p2[0], y)
        blk.add_line(a, b, dxfattribs=att)
        blk.add_line(p1, a, dxfattribs=att)
        blk.add_line(p2, b, dxfattribs=att)
        mid = ((p1[0] + p2[0]) / 2, y - 0.6 * th - th / 2)
        rot = 0
    for e in (a, b):
        blk.add_line(
            (e[0] - tick, e[1] - tick), (e[0] + tick, e[1] + tick), dxfattribs=att
        )
    text = f"{value:g}"
    t = blk.add_text(text, dxfattribs={**att, "height": th, "rotation": rot})
    t.set_placement(mid, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    msp.new_entity(
        "DIMENSION",
        dxfattribs={
            "layer": "DIM",
            "geometry": blk.name,
            "dimstyle": "Standard",
            "defpoint": b,
            "text_midpoint": mid,
            "dimtype": 32,  # 회전 선형 치수, 블록은 이 치수만 쓴다
            "text": "<>",
            "actual_measurement": value,
            "defpoint2": p1,
            "defpoint3": p2,
            "angle": rot,
        },
    )


def hole_note(holes: list[float]) -> str | None:
    """같은 지름 구멍 수와 지름. DXF 에서 Ø 는 %%c 로 쓴다 (R2000 은 ANSI 코드페이지라 UTF-8 Ø 가 깨진다)."""
    if not holes:
        return None
    sizes = sorted(set(holes))
    return ", ".join(f"{holes.count(s)}-%%c{s:g}" for s in sizes)


def title_block(msp, k: float, spec: dict, scale_text: str):
    x0, y0, x1, y1 = (v * k for v in TITLE)
    att = {"layer": "TITLE"}
    for p, q in (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
        ((x0, 30 * k), (x1, 30 * k)),
        ((350 * k, y0), (350 * k, y1)),
    ):
        msp.add_line(p, q, dxfattribs=att)
    t = spec["p"]["thickness"]
    for x, y, h, text in (
        (292, 44, 3.2, f"PART NAME  {spec['cls'].upper()}"),
        (292, 37, 3.2, f"MATERIAL  {spec['mat']}, {t:g}t"),
        (292, 23, 3.2, "SCALE"),
        (312, 23, 3.2, scale_text),
        (330, 23, 3.2, "DIM  mm"),
        (292, 15, 3.2, "DW'G NO"),
        (314, 15, 4.8, drawing_no(spec)),
        (352, 44, 3.2, "A3 (297x420)"),
        (352, 37, 3.2, "THIRD ANGLE"),
    ):
        msp.add_text(
            text, dxfattribs={**att, "height": h * k, "insert": (x * k, y * k)}
        )


def drawing_no(spec: dict) -> str:
    return f"SYN-{int(spec['id'].rsplit('_', 1)[1]):05d}"


# ----------------------------------------------------------------------------- 한 장


def build_one(spec: dict, out: Path) -> dict:
    k = float(spec["scale"])
    scale_text = f"1/{spec['scale']}"
    draw, blank = SHAPES[spec["cls"]]
    views, extents = draw(spec["p"], spec["holes"], k)
    for v in views.values():
        v.dedup()
    origins = layout(views, k)
    if not fits(views, origins, k):
        raise ValueError(f"{spec['id']}: views do not fit the A3 frame at {scale_text}")

    doc = new_document(k)
    msp = doc.modelspace()
    fx0, fy0, fx1, fy1 = (v * k for v in FRAME)
    for p, q in (
        ((fx0, fy0), (fx1, fy0)),
        ((fx1, fy0), (fx1, fy1)),
        ((fx1, fy1), (fx0, fy1)),
        ((fx0, fy1), (fx0, fy0)),
    ):
        msp.add_line(p, q, dxfattribs={"layer": "FRAME"})
    for name in ("front", "top", "right"):
        ox, oy = origins[name]
        for pr in views[name].prims:
            put(msp, pr, ox, oy)

    # 치수: 정면도 가로·세로, 평면도 세로(y), 우측면도 가로(y)
    dims = []
    f, tp, rt = origins["front"], origins["top"], origins["right"]
    fv, tv, rv = views["front"], views["top"], views["right"]
    for view, axis, p1, p2, vertical, value in (
        ("front", "x", f, (f[0] + fv.width, f[1]), False, extents[0]),
        ("front", "z", f, (f[0], f[1] + fv.height), True, extents[2]),
        ("top", "y", tp, (tp[0], tp[1] + tv.height), True, extents[1]),
        ("right", "y", rt, (rt[0] + rv.width, rt[1]), False, extents[1]),
    ):
        add_dimension(doc, msp, p1, p2, vertical, value, k)
        dims.append({"view": view, "axis": axis, "value": value})

    notes = {}
    for name in ("top", "right"):
        note = hole_note(views[name].holes)
        if note:
            ox, oy = origins[name]
            msp.add_text(
                note,
                dxfattribs={
                    "layer": "TEXT",
                    "height": TEXT_H * k,
                    "insert": (ox, oy + views[name].height + 2 * TEXT_H * k),
                },
            )
            notes[name] = note.replace("%%c", "Ø")
    title_block(msp, k, spec, scale_text)
    doc.header["$EXTMIN"] = (fx0, fy0, 0)
    doc.header["$EXTMAX"] = (fx1, fy1, 0)

    item = out / spec["id"]
    item.mkdir(parents=True, exist_ok=True)
    dxf_path = item / f"{spec['id']}.dxf"
    doc.saveas(dxf_path)

    label = {
        "id": spec["id"],
        "class": spec["cls"],
        "units": "mm",
        "params": spec["p"],
        "thickness": spec["p"]["thickness"],
        "holes": [
            {"axis": ax, "diameter": d, "center": list(c)} for ax, d, c in spec["holes"]
        ],
        "hole_notes": notes,
        "extents": list(extents),
        "flat_pattern": blank(spec["p"]),
        "sheet": {
            "projection": "third",
            "scale": 1 / k,
            "scale_text": scale_text,
            "paper_mm": [297, 420],
            "material": spec["mat"],
            "drawing_no": drawing_no(spec),
            "frame_model_units": [fx0, fy0, fx1, fy1],
        },
        "views": {
            name: {
                "bbox_dxf": [
                    origins[name][0],
                    origins[name][1],
                    origins[name][0] + views[name].width,
                    origins[name][1] + views[name].height,
                ],
                "extent_mm": [views[name].width, views[name].height],
            }
            for name in ("front", "top", "right")
        },
        "dimensions": dims,
        "files": {"dxf": dxf_path.name, "png": f"{spec['id']}.png"},
        "source": "scripts/build_synthetic.py",
    }
    (item / "label.json").write_text(
        json.dumps(label, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return label


def render_png(label: dict, item: Path):
    """reader 의 렌더러로 PNG 를 그린다 (도면 틀 기준, 폭 16 in, 146 dpi)."""
    from cutplan_agent.reader.dxf_adapter import render
    from cutplan_agent.reader.dxf_reader import read_dxf

    entities, _ = read_dxf(item / label["files"]["dxf"])
    x0, y0, x1, y1 = label["sheet"]["frame_model_units"]
    m = 0.01 * (x1 - x0)
    render(
        entities,
        item / label["files"]["png"],
        bbox=(x0 - m, y0 - m, x1 + m, y1 + m),
        dpi=146,
    )


# ----------------------------------------------------------------------------- 비교 표


def blank_text(cls: str, fp: dict) -> str:
    keys = {
        "flat": ("length", "width"),
        "bent_sheet": ("length", "width", "bend_lines"),
        "cylinder": ("length", "width"),
        "cone": ("sector_outer_radius", "sector_inner_radius", "sector_angle_deg"),
        "press_formed": ("blank_diameter",),
    }[cls]
    return ", ".join(f"{k}={fp.get(k)}" for k in keys)


def write_compare(labels: list[dict], old_dir: Path, out: Path):
    rows = [
        "# 옛 정답과 새 정답의 전개 값",
        "",
        f"옛 정답: `{old_dir}` (동료 생성기). 새 정답: `scripts/build_synthetic.py`. 바뀐 이유는 docs/data/synthetic.md.",
        "",
        "| id | 옛 정답 | 새 정답 | 최대 차이 |",
        "|---|---|---|---:|",
    ]
    for lab in labels:
        path = old_dir / lab["id"] / "label.json"
        if not path.exists():
            continue
        old = json.loads(path.read_text(encoding="utf-8"))["flat_pattern"]
        new = lab["flat_pattern"]
        diffs = [
            abs(new[k] - old[k]) / abs(old[k])
            for k in new
            if isinstance(new[k], (int, float))
            and isinstance(old.get(k), (int, float))
            and old[k]
        ]
        worst = f"{100 * max(diffs):.2f}%" if diffs else ""
        rows.append(
            f"| {lab['id']} | {blank_text(lab['class'], old)} | {blank_text(lab['class'], new)} | {worst} |"
        )
    (out / "compare.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=Path("data_v3/generated"))
    ap.add_argument(
        "--compare", type=Path, help="옛 데이터 폴더. 주면 compare.md 를 쓴다"
    )
    ap.add_argument("--no-png", action="store_true", help="PNG 를 그리지 않는다")
    ap.add_argument("--only", help="이 문자열이 id 에 들어간 도면만 만든다")
    ap.add_argument(
        "-q", "--quiet", action="store_true", help="도면마다 한 줄씩 출력하지 않는다"
    )
    args = ap.parse_args(argv)

    specs = [s for s in SPECS if not args.only or args.only in s["id"]]
    labels = []
    for spec in specs:
        label = build_one(spec, args.out)
        if not args.no_png:
            render_png(label, args.out / spec["id"])
        labels.append(label)
        if not args.quiet:
            print(f"{spec['id']}: {blank_text(spec['cls'], label['flat_pattern'])}")

    with (args.out / "index.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "class", "params", "scale", "material", "flat_pattern"])
        for lab in labels:
            w.writerow(
                [
                    lab["id"],
                    lab["class"],
                    json.dumps(lab["params"]),
                    lab["sheet"]["scale_text"],
                    lab["sheet"]["material"],
                    blank_text(lab["class"], lab["flat_pattern"]),
                ]
            )
    if args.compare:
        write_compare(labels, args.compare, args.out)
    if not args.quiet:
        print(f"{len(labels)} drawings -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
