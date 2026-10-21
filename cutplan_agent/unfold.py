"""
부품 전개(development / flat pattern) 계산 엔진

도면을 '따라 그리는' 것이 아니라, 부품의 3차원 형상 파라미터를 받아
평평하게 폈을 때의 블랭크 형상을 공학식으로 계산한다.

지원 형상
    flat          이미 평판  -> 윤곽 그대로 통과
    cylinder      원통(SHELL/CHANNEL) -> 직사각형
    cone_frustum  원뿔대(CONE) -> 부채꼴(환형 섹터)
    bent_sheet    절곡 판금 -> 직선구간 + 굽힘여유(BA)

중립축 규약
    KDM TECH 의 실제 도면 태그 44건을 역산한 결과, 원통 전개길이는
        L = pi x (ID + t)
    즉 중립축을 평균지름에 두고 있다 (K-factor = 0.5).
    python -m cutplan_agent.unfold --validate 로 그 44건을 재검증할 수 있다.

원본: tools/dwg2png/vlm/unfold.py (이전 세션 툴킷). l3_rules.unfold_part 가 절곡·평판에 쓴다.
"""
from __future__ import annotations

import math
from typing import List, Literal, Optional

import ezdxf
from ezdxf import units
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# 입력 스키마 — VLM 이 도면을 읽고 채우는 '부품 모델'
# --------------------------------------------------------------------------
class PartModel(BaseModel):
    part_type: Literal["flat", "cylinder", "cone_frustum", "bent_sheet", "unknown"]
    part_name: str
    drawing_no: str
    material: str
    thickness: float = Field(description="판 두께 t (mm)")
    quantity: int

    # --- cylinder ---
    inner_dia: float = Field(0, description="원통 안지름 ID (mm)")
    length: float = Field(0, description="원통 길이 / 높이 (mm)")

    # --- cone_frustum ---
    large_inner_dia: float = Field(0, description="원뿔대 큰쪽 안지름")
    small_inner_dia: float = Field(0, description="원뿔대 작은쪽 안지름 (꼭지점이면 0)")
    cone_height: float = Field(0, description="원뿔대 수직 높이")

    # --- bent_sheet ---
    width: float = Field(0, description="절곡판 폭 (굽힘축 방향 길이)")
    segments: List[float] = Field(default_factory=list,
                                  description="굽힘 사이 직선구간 길이들 (외측 기준)")
    bend_angles: List[float] = Field(default_factory=list,
                                     description="각 굽힘의 굽힘각(도). 90 이면 직각")
    bend_radii: List[float] = Field(default_factory=list,
                                    description="각 굽힘의 내측 반지름 R")

    # --- flat ---
    outline: List[List[float]] = Field(default_factory=list,
                                       description="평판 윤곽 [[x,y], ...]")

    confidence: Literal["high", "medium", "estimated", "unreadable"] = "medium"
    notes: List[str] = Field(default_factory=list)


class FlatPattern(BaseModel):
    """전개 계산 결과."""
    part_type: str
    outline: List[List[float]]          # 전개 블랭크 윤곽
    arcs: List[dict] = Field(default_factory=list)   # 부채꼴 등 호 정보
    bend_lines: List[List[List[float]]] = Field(default_factory=list)
    blank_w: float = 0
    blank_h: float = 0
    developed_length: float = 0
    formula: str = ""
    warnings: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# K-factor — 중립축 위치
# --------------------------------------------------------------------------
def k_factor(radius: float, thickness: float) -> float:
    """내측 반지름/두께 비에 따른 중립축 계수.

    롤링(원통·원뿔)은 R/t 가 크므로 0.5 로 수렴한다 — KDM 관행과 일치.
    프레스 절곡은 R/t 가 작을수록 중립축이 안쪽으로 이동한다.
    """
    if thickness <= 0:
        return 0.5
    ratio = radius / thickness
    if ratio < 1.0:
        return 0.33
    if ratio < 3.0:
        return 0.40
    return 0.50


def bend_allowance(angle_deg: float, radius: float, thickness: float) -> float:
    """굽힘여유 BA = theta x (R + K t).  굽힘 구간의 중립축 호 길이."""
    k = k_factor(radius, thickness)
    return math.radians(angle_deg) * (radius + k * thickness)


# --------------------------------------------------------------------------
# 형상별 전개
# --------------------------------------------------------------------------
def unfold_cylinder(m: PartModel) -> FlatPattern:
    """원통 -> 직사각형.  L = pi x (ID + t)"""
    w = []
    if m.inner_dia <= 0 or m.length <= 0:
        return FlatPattern(part_type="cylinder", outline=[],
                           warnings=["inner_dia 또는 length 가 비어 전개 불가"])
    mean_dia = m.inner_dia + m.thickness            # 중립축 지름 (K=0.5)
    L = math.pi * mean_dia
    if m.thickness > 0 and m.inner_dia / m.thickness < 20:
        w.append(f"ID/t = {m.inner_dia/m.thickness:.1f} 로 작다 — 후육 원통은 "
                 f"중립축이 평균지름에서 벗어날 수 있다")
    H = m.length
    return FlatPattern(
        part_type="cylinder",
        outline=[[0, 0], [L, 0], [L, H], [0, H]],
        blank_w=L, blank_h=H, developed_length=L,
        formula=f"L = pi x (ID + t) = pi x ({m.inner_dia} + {m.thickness}) = {L:.1f}",
        warnings=w)


def unfold_cone(m: PartModel) -> FlatPattern:
    """원뿔대 -> 부채꼴(환형 섹터).

    중립면 기준. 큰쪽/작은쪽 평균지름으로 모선길이와 전개 반지름을 구한다.
        s  = sqrt(h^2 + ((D1m - D2m)/2)^2)        모선 길이
        R1 = s x D1m / (D1m - D2m)                 큰쪽 전개 반지름
        R2 = R1 - s                                작은쪽 전개 반지름
        theta = pi x D1m / R1                      부채꼴 중심각(rad)
    """
    w = []
    D1m = m.large_inner_dia + m.thickness
    D2m = m.small_inner_dia + m.thickness if m.small_inner_dia > 0 else m.thickness
    h = m.cone_height
    if D1m <= 0 or h <= 0:
        return FlatPattern(part_type="cone_frustum", outline=[],
                           warnings=["large_inner_dia 또는 cone_height 가 비어 전개 불가"])
    if D2m >= D1m:
        return FlatPattern(part_type="cone_frustum", outline=[],
                           warnings=["작은쪽 지름이 큰쪽 이상 — 값이 뒤바뀐 듯"])

    dR = (D1m - D2m) / 2.0
    s = math.hypot(h, dR)
    R1 = s * D1m / (D1m - D2m)
    R2 = R1 - s
    theta = math.pi * D1m / R1                      # rad
    if theta > 2 * math.pi:
        w.append("중심각이 360도를 넘는다 — 분할 전개가 필요하다")

    # 부채꼴 윤곽을 점으로 (호는 arcs 에도 남긴다)
    n = max(24, int(math.degrees(theta) / 2))
    outer = [[R1 * math.cos(a), R1 * math.sin(a)]
             for a in (theta * i / n for i in range(n + 1))]
    inner = [[R2 * math.cos(a), R2 * math.sin(a)]
             for a in (theta * i / n for i in range(n, -1, -1))]
    pts = outer + inner

    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return FlatPattern(
        part_type="cone_frustum",
        outline=pts,
        arcs=[{"r": R1, "start": 0.0, "end": math.degrees(theta)},
              {"r": R2, "start": 0.0, "end": math.degrees(theta)}],
        blank_w=max(xs) - min(xs), blank_h=max(ys) - min(ys),
        developed_length=theta * R1,
        formula=(f"s={s:.1f}  R1={R1:.1f}  R2={R2:.1f}  "
                 f"theta={math.degrees(theta):.2f}도"),
        warnings=w)


def unfold_bent(m: PartModel) -> FlatPattern:
    """절곡 판금 -> 직선구간 + 굽힘여유.

    전개길이 = sum(직선구간) + sum(BA_i)
    직선구간은 외측 치수 기준으로 주어지므로, 굽힘에 물린 만큼(setback) 뺀다.
    """
    w = []
    if not m.segments:
        return FlatPattern(part_type="bent_sheet", outline=[],
                           warnings=["segments 가 비어 전개 불가"])
    n_bend = len(m.bend_angles)
    if n_bend != len(m.bend_radii) or len(m.segments) != n_bend + 1:
        w.append(f"구간 {len(m.segments)}개 / 굽힘 {n_bend}개 — 개수가 "
                 f"맞지 않는다 (구간 = 굽힘 + 1 이어야 함)")

    t = m.thickness
    total = 0.0
    cuts = []           # 굽힘선 위치(전개 좌표 x)
    for i, seg in enumerate(m.segments):
        # 앞뒤 굽힘에 물린 setback 을 뺀 실제 평면부 길이
        sb = 0.0
        if i > 0 and i - 1 < n_bend:
            r, a = m.bend_radii[i-1], m.bend_angles[i-1]
            sb += (r + t) * math.tan(math.radians(a) / 2)
        if i < n_bend:
            r, a = m.bend_radii[i], m.bend_angles[i]
            sb += (r + t) * math.tan(math.radians(a) / 2)
        flat = seg - sb
        if flat < 0:
            w.append(f"구간 {i+1} 이 굽힘에 모두 먹혔다 (길이 {seg}, setback {sb:.1f})")
            flat = 0.0
        total += flat
        if i < n_bend:
            ba = bend_allowance(m.bend_angles[i], m.bend_radii[i], t)
            cuts.append((total, total + ba))
            total += ba

    W = m.width if m.width > 0 else 100.0
    if m.width <= 0:
        w.append("width 가 비어 임시로 100 을 썼다")
    bl = [[[x0, 0], [x0, W]] for x0, _ in cuts] + [[[x1, 0], [x1, W]] for _, x1 in cuts]
    return FlatPattern(
        part_type="bent_sheet",
        outline=[[0, 0], [total, 0], [total, W], [0, W]],
        bend_lines=bl,
        blank_w=total, blank_h=W, developed_length=total,
        formula=("전개 = sum(평면부) + sum(BA),  BA = theta x (R + K t), "
                 f"K={k_factor(m.bend_radii[0] if m.bend_radii else t, t):.2f}"),
        warnings=w)


def unfold_flat(m: PartModel) -> FlatPattern:
    if not m.outline:
        return FlatPattern(part_type="flat", outline=[],
                           warnings=["outline 이 비어 있다"])
    xs = [p[0] for p in m.outline]; ys = [p[1] for p in m.outline]
    return FlatPattern(part_type="flat", outline=m.outline,
                       blank_w=max(xs)-min(xs), blank_h=max(ys)-min(ys),
                       formula="평판 - 전개 불필요, 윤곽 그대로")


DISPATCH = {"cylinder": unfold_cylinder, "cone_frustum": unfold_cone,
            "bent_sheet": unfold_bent, "flat": unfold_flat}


def unfold(m: PartModel) -> FlatPattern:
    fn = DISPATCH.get(m.part_type)
    if fn is None:
        return FlatPattern(part_type=m.part_type, outline=[],
                           warnings=[f"지원하지 않는 형상: {m.part_type}"])
    return fn(m)


# --------------------------------------------------------------------------
# DXF 출력
# --------------------------------------------------------------------------
def write_dxf(m: PartModel, fp: FlatPattern, path: str) -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    msp = doc.modelspace()
    for name, color in (("BLANK", 7), ("BEND", 3), ("INFO", 5)):
        if name not in doc.layers:
            doc.layers.add(name, color=color)

    if fp.outline:
        msp.add_lwpolyline(fp.outline, close=True, dxfattribs={"layer": "BLANK"})
    for seg in fp.bend_lines:
        msp.add_line(seg[0], seg[1], dxfattribs={"layer": "BEND"})

    info = [
        f"{m.drawing_no}  {m.part_name}   QTY {m.quantity}",
        f"{m.material}  t{m.thickness}",
        f"TYPE: {fp.part_type}",
        f"BLANK: {fp.blank_w:.1f} x {fp.blank_h:.1f} mm",
        f"FORMULA: {fp.formula}",
    ] + [f"! {x}" for x in fp.warnings]
    y = -30.0
    for ln in info:
        msp.add_text(ln, height=max(fp.blank_h, 100) * 0.03,
                     dxfattribs={"layer": "INFO"}).set_placement((0, y))
        y -= max(fp.blank_h, 100) * 0.045

    doc.set_modelspace_vport(height=max(fp.blank_h, 100) * 1.6,
                             center=(fp.blank_w / 2, fp.blank_h / 2))
    doc.saveas(path)


# --------------------------------------------------------------------------
# 검증 — 실제 도면 태그 44건으로 원통 공식 재확인
# --------------------------------------------------------------------------
def validate(tags_csv: str) -> None:
    """공식 L = pi(ID+t) 의 검정.

    도면의 전개길이에서 ID 를 역산했을 때 '설계자가 실제로 쓸 법한 둥근 값'이
    나오는지 본다. 답에서 ID 를 만들어 다시 답을 예측하는 순환검증이 아니라,
    역산값이 라운드 넘버에 얼마나 붙는지를 잔차로 측정한다.

    대조군으로 안지름/바깥지름 기준 공식도 같이 재서, 평균지름 가설이
    실제로 더 잘 맞는지 확인한다.
    """
    import csv, io as _io, re
    rows = list(csv.DictReader(_io.open(tags_csv, encoding="utf-8-sig")))
    cases = []
    for r in rows:
        if not re.match(r"^(SHELL|L/SHELL|CHANNEL)", r["part_name"].upper()):
            continue
        mm = re.fullmatch(r"([\d.]+)x([\d.]+)", r["size"])
        if not mm:
            continue
        a, b = float(mm.group(1)), float(mm.group(2))
        cases.append((r["part_name"], float(r["thickness"]), max(a, b)))

    def residual(dia_from_L, grid):
        """역산 지름이 grid 배수에서 얼마나 떨어져 있는가 (mm)."""
        return abs(dia_from_L - round(dia_from_L / grid) * grid)

    print(f"검정 대상 {len(cases)}건 (SHELL / L/SHELL / CHANNEL)\n")
    print(f"{'가설':<26}{'5mm격자 잔차 중앙값':>22}{'<=2mm':>9}{'<=0.5mm':>10}")
    print("-" * 68)
    best = None
    for label, dia in (("중립축 = 평균지름 (ID+t)", lambda L, t: L / math.pi - t),
                       ("중립축 = 안지름 (ID)",      lambda L, t: L / math.pi),
                       ("중립축 = 바깥지름 (ID+2t)", lambda L, t: L / math.pi - 2 * t)):
        res = [residual(dia(L, t), 5.0) for _, t, L in cases]
        res.sort()
        med = res[len(res) // 2]
        n2 = sum(1 for x in res if x <= 2.0)
        n05 = sum(1 for x in res if x <= 0.5)
        print(f"{label:<26}{med:>22.2f}{n2:>9}{n05:>10}")
        if best is None or med < best[1]:
            best = (label, med)

    print(f"\n채택: {best[0]}  (잔차 중앙값 {best[1]:.2f}mm)")

    print(f"\n{'부품':<12}{'t':>4}{'도면 전개길이':>14}{'역산 ID':>11}{'잔차':>8}")
    print("-" * 52)
    worst = sorted(cases, key=lambda c: -residual(c[2] / math.pi - c[1], 5.0))
    for n, t, L in worst[:5]:
        d = L / math.pi - t
        print(f"{n[:11]:<12}{t:>4.0f}{L:>14.1f}{d:>11.1f}{residual(d, 5.0):>8.2f}")
    print("  (잔차가 큰 건 = 공식이 안 맞거나, ID 가 5mm 격자가 아닌 설계)")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--validate":
        from cutplan_agent.config import ROOT
        validate(sys.argv[2] if len(sys.argv) > 2
                 else str(ROOT / "Data" / "_dataset" / "part_tags.csv"))
    else:
        print(__doc__)
