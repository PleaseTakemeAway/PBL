"""
L2 관계·의미 매핑(Relation & Semantic) — "무엇을 의미하고 무엇과 이어지나". VLM 추론의 본체.

  classify_drawing       도면 종류 (GA / DETAIL OF BODY / NOZZLE / SADDLE / BUNDLE / MANHOLE / CP / 기타)
  extract_design_data    GA → DESIGN DATA·재질표·노즐표 → state.design_data
  extract_part_model     BOM 항목 + 도면 뷰 → 3D 파라미터(PartSpec).  "그림을 따라 그리지 말고 형상을 읽어라"
  set_part_spec          사람/에이전트가 파라미터를 직접 지정 (KDM 접근 B: 조각+스펙 입력, HITL 경로)
  detect_split_lines     WELDING SEAM PLAN/ORIENTATION 에서 용접선·코스 구성을 읽어 PartSpec.seams 에 붙임 (RQ1)
  resolve_missing_spec   BOM 에 두께만 있는 패드 등 → 노즐표/관례로 보충, 못 하면 HITL 표식
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from cutplan_agent.config import SKILLS_DIR
from cutplan_agent.skills.l1_perception import vlm_parse
from cutplan_agent.state import PartSpec, get_state, logged


class DrawingClass(BaseModel):
    category: str = Field(
        description="GA | DETAIL_OF_BODY | DETAIL_OF_NOZZLE | DETAIL_OF_SADDLE | DETAIL_OF_TUBE_BUNDLE | "
        "DETAIL_OF_MANHOLE | PLATFORM_LADDER | NAMEPLATE | TEST_RING | CUTTING_PLAN | OTHER"
    )
    has_bom: bool = False
    has_welding_seam_plan: bool = False
    plate_parts_expected: List[str] = Field(
        default_factory=list, description="이 도면에서 나올 판재 부품 이름"
    )
    confidence: str = "medium"
    reason: str = ""


@logged
def classify_drawing(drawing_index: int, page: int = 1) -> dict:
    """도면 종류를 판정하고 BOM/용접선 배치도 유무, 기대되는 판재 부품을 적는다."""
    st = get_state()
    d = st.drawings[drawing_index]
    out = vlm_parse(
        [d["pages"][page - 1]],
        "이 도면의 종류를 분류하라. 제목(TITLE)과 뷰 구성을 근거로. BOM 표와 WELDING SEAM PLAN/ORIENTATION 뷰가 있는지, "
        "이 도면에서 커팅플랜에 들어갈 판재 부품(SHELL, HEAD, CONE, PAD, LUG, BAFFLE ...)이 무엇일지 적어라.",
        DrawingClass,
    )
    d["category"] = out.category
    d["class_info"] = out.model_dump()
    return out.model_dump()


@logged
def extract_design_data(drawing_index: int, page: int = 1) -> dict:
    """GA 도면에서 설계조건·재질표·노즐표를 읽어 state.design_data 에 저장."""
    from cutplan_agent.skills.l1_perception import vlm_read_page

    r = vlm_read_page(drawing_index, "design_data", page)
    if "error" in r:
        return r
    st = get_state()
    st.design_data = r
    return {
        "shell_id": r.get("shell_id"),
        "design_pressure": r.get("design_pressure"),
        "corrosion_allowance": r.get("corrosion_allowance"),
        "n_nozzles": len(r.get("nozzle_list", [])),
        "materials": r.get("material_spec"),
    }


# ----------------------------------------------------------------------------- 부품 모델 추출
class PartModelOut(BaseModel):
    part_type: str = Field(
        description="cylinder | cone_frustum | eccentric_cone | bent_sheet | flat | head | pad_ring | unknown"
    )
    part_name: str = ""
    material: str = ""
    thickness: float = 0
    quantity: int = 1
    inner_dia: float = Field(
        0,
        description="원통 안지름 ID. OD 로 적혀 있으면 ID=OD-2t 로 환산하고 notes 에 기록",
    )
    length: float = Field(
        0, description="원통 코스 길이(굽힘축 방향). 여러 코스면 courses 에 각각"
    )
    courses: List[float] = Field(
        default_factory=list,
        description="쉘이 여러 코스면 각 코스 길이 (TL~TL 을 코스별로)",
    )
    large_inner_dia: float = 0
    small_inner_dia: float = 0
    cone_height: float = Field(0, description="원뿔대 수직 높이 (모선 아님)")
    eccentricity: float = Field(
        0,
        description="편심 콘의 두 원 중심 거리 e. 한쪽 면이 수직이면 0 (e = (D1-D2)/2 로 계산)",
    )
    head_type: str = Field(
        "",
        description="2:1 ellipsoidal | hemispherical | torispherical (F&D) | flat flanged",
    )
    straight_flange: float = Field(0, description="헤드 직선부 SF (T.L 에서 끝단까지)")
    knuckle_radius: float = Field(
        0, description="접시형·평판형 헤드의 내측 너클 반경 IKR"
    )
    pad_od: float = 0
    pad_id: float = 0
    width: float = 0
    segments: List[float] = Field(default_factory=list)
    bend_angles: List[float] = Field(default_factory=list)
    bend_radii: List[float] = Field(default_factory=list)
    outline: List[List[float]] = Field(default_factory=list)
    evidence: List[str] = Field(
        default_factory=list, description="어느 뷰의 어느 치수에서 읽었는지"
    )
    confidence: str = Field(
        "medium", description="high | medium | estimated | unreadable"
    )
    notes: List[str] = Field(default_factory=list)


def _unfold_prompt() -> str:
    p = SKILLS_DIR / "02_prompts" / "unfold_extract.md"
    return p.read_text(encoding="utf8") if p.exists() else ""


@logged
def extract_part_model(
    bom_index: int,
    drawing_index: int,
    pages: Optional[List[int]] = None,
    hints: str = "",
) -> dict:
    """BOM 항목 하나에 대해 도면 뷰에서 3D 파라미터를 읽어 PartSpec 을 만든다 (state.parts 에 추가).
    hints 에 dxf_read_text 로 확인한 정확한 숫자나 사람의 지시를 넣을 수 있다."""
    st = get_state()
    item = st.bom[bom_index]
    d = st.drawings[drawing_index]
    pngs = [d["pages"][p - 1] for p in (pages or [1])]
    dd = st.design_data or {}
    prompt = (
        f"대상 부품: BOM 항목 {item.item_no} '{item.part_name}' 재질 {item.material} 두께 {item.thickness} 수량 {item.qty} {item.unit}, "
        f"SIZE 원문 '{item.size_text}'. 1차 전개 판정: {item.unfold_class}.\n"
        f"GA 설계조건(참고): shell_id={dd.get('shell_id', '')}, 재질표={dd.get('material_spec', {})}.\n"
        + (f"힌트: {hints}\n" if hints else "")
        + "도면에서 이 부품의 3D 형상 파라미터를 읽어라. 어느 뷰의 어느 치수를 썼는지 evidence 에 적어라. 쉘이 여러 코스면 courses 에 코스별 길이. "
        "헤드는 part_type=head 로 두고 ID·종류·직선부를 적어라. 접시형이면 너클 반경(IKR)도. "
        "편심 콘은 part_type=eccentric_cone 으로 두고 큰쪽·작은쪽 안지름, 수직 높이, 편심량을 적어라. "
        "보강패드는 pad_ring 으로 OD/ID. 값이 없으면 0 으로 두고 confidence 를 낮춰라."
    )
    out = vlm_parse(pngs, prompt, PartModelOut, system=_unfold_prompt())
    spec = PartSpec(
        part_id=f"B{bom_index}_{re.sub(r'[^A-Za-z0-9]+', '_', item.part_name)[:20]}",
        part_name=item.part_name or out.part_name,
        part_type=out.part_type,
        material=item.material or out.material,
        thickness=item.thickness or out.thickness,
        quantity=item.qty,
        inner_dia=out.inner_dia,
        length=out.length,
        large_inner_dia=out.large_inner_dia,
        small_inner_dia=out.small_inner_dia,
        cone_height=out.cone_height,
        eccentricity=out.eccentricity,
        head_type=out.head_type or "2:1 ellipsoidal",
        straight_flange=out.straight_flange or 50,
        knuckle_radius=out.knuckle_radius,
        pad_od=out.pad_od,
        pad_id=out.pad_id,
        width=out.width,
        segments=out.segments,
        bend_angles=out.bend_angles,
        bend_radii=out.bend_radii,
        outline=out.outline,
        seams={"courses": out.courses} if out.courses else {},
        confidence=out.confidence,
        notes=out.notes + [f"evidence: {e}" for e in out.evidence],
    )
    st.parts.append(spec)
    return {"part_index": len(st.parts) - 1, **spec.model_dump(exclude={"outline"})}


@logged
def set_part_spec(
    part_name: str,
    part_type: str,
    material: str,
    thickness: float,
    quantity: int = 1,
    inner_dia: float = 0,
    length: float = 0,
    courses: Optional[List[float]] = None,
    large_inner_dia: float = 0,
    small_inner_dia: float = 0,
    cone_height: float = 0,
    head_type: str = "2:1 ellipsoidal",
    straight_flange: float = 50,
    knuckle_radius: float = 0,
    eccentricity: float = 0,
    pad_od: float = 0,
    pad_id: float = 0,
    width: float = 0,
    segments: Optional[List[float]] = None,
    bend_angles: Optional[List[float]] = None,
    bend_radii: Optional[List[float]] = None,
    outline: Optional[List[List[float]]] = None,
    long_seams: int = 1,
    confidence: str = "high",
    note: str = "",
) -> dict:
    """VLM 없이 부품 파라미터를 직접 지정한다 (KDM 접근 B / HITL 입력 / 테스트). state.parts 에 추가."""
    st = get_state()
    pid = f"P{len(st.parts)}_{re.sub(r'[^A-Za-z0-9]+', '_', part_name)[:20]}"
    spec = PartSpec(
        part_id=pid,
        part_name=part_name,
        part_type=part_type,
        material=material,
        thickness=thickness,
        quantity=quantity,
        inner_dia=inner_dia,
        length=length,
        large_inner_dia=large_inner_dia,
        small_inner_dia=small_inner_dia,
        cone_height=cone_height,
        eccentricity=eccentricity,
        head_type=head_type,
        straight_flange=straight_flange,
        knuckle_radius=knuckle_radius,
        pad_od=pad_od,
        pad_id=pad_id,
        width=width,
        segments=segments or [],
        bend_angles=bend_angles or [],
        bend_radii=bend_radii or [],
        outline=outline or [],
        seams={"courses": courses or [], "long_seams": long_seams},
        confidence=confidence,
        notes=[note] if note else [],
    )
    st.parts.append(spec)
    return {"part_index": len(st.parts) - 1, "part_id": pid}


# ----------------------------------------------------------------------------- 분할선 (RQ1)
class SeamPlan(BaseModel):
    courses: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[{'name':'SA-01','kind':'shell|cone|head','length':1700,'long_seams':1,'angles':[0]}]",
    )
    head_seams: List[str] = Field(default_factory=list)
    cone_seams: List[str] = Field(default_factory=list)
    total_tl_to_tl: float = 0
    confidence: str = "medium"
    notes: List[str] = Field(default_factory=list)


@logged
def detect_split_lines(
    drawing_index: int, part_index: Optional[int] = None, page: int = 1
) -> dict:
    """WELDING SEAM PLAN / ORIENTATION 뷰에서 코스 구성과 롱심 수를 읽는다. part_index 를 주면 그 부품의 seams 에 붙인다."""
    st = get_state()
    d = st.drawings[drawing_index]
    out = vlm_parse(
        [d["pages"][page - 1]],
        "WELDING SEAM PLAN 과 WELDING SEAM ORIENTATION 뷰를 읽어라. 쉘 코스(SA-xx)별 길이와 롱심 개수·각도, 헤드/콘 용접선(HA/SB), "
        "TL~TL 전체 길이를 적어라. 코스 길이는 코스 경계 치수에서 읽는다. 없는 값은 0.",
        SeamPlan,
    )
    data = out.model_dump()
    if part_index is not None:
        st.parts[part_index].seams.update(data)
    d.setdefault("extract", {})["seams"] = data
    return data


# ----------------------------------------------------------------------------- 결측 스펙 보충
_INCH_OD = {
    "1": 33.4,
    "1-1/2": 48.3,
    "2": 60.3,
    "3": 88.9,
    "4": 114.3,
    "6": 168.3,
    "8": 219.1,
    "10": 273.1,
    "12": 323.9,
    "14": 355.6,
    "16": 406.4,
    "18": 457.2,
    "20": 508.0,
    "24": 609.6,
}


@logged
def resolve_missing_spec(part_index: int, nozzle_mark: str = "") -> dict:
    """BOM 에 두께만 있는 보강패드 등의 치수를 GA 노즐표/관례로 보충한다. 추정값은 confidence=estimated 로 표시해 HITL(H2) 대상이 된다."""
    st = get_state()
    p = st.parts[part_index]
    dd = st.design_data or {}
    if p.part_type == "pad_ring" and (p.pad_od <= 0 or p.pad_id <= 0):
        noz = next(
            (
                n
                for n in dd.get("nozzle_list", [])
                if nozzle_mark and n.get("mark", "").upper() == nozzle_mark.upper()
            ),
            None,
        )
        if noz and noz.get("reinf_pad_od"):
            p.pad_od = float(re.sub(r"[^\d.]", "", noz["reinf_pad_od"]) or 0)
            size = re.sub(r'["\s]', "", noz.get("size", ""))
            p.pad_id = _INCH_OD.get(size, 0) + 3.0 if size in _INCH_OD else 0
            p.confidence = "medium"
            p.notes.append(
                f"패드 OD 는 GA 노즐표({nozzle_mark}) 에서, ID 는 파이프 OD+3"
            )
        elif noz:
            size = re.sub(r'["\s]', "", noz.get("size", ""))
            od = _INCH_OD.get(size, 0)
            if od:
                p.pad_id, p.pad_od = od + 3.0, round(2 * od, 0)
                p.confidence = "estimated"
                p.notes.append(
                    "패드 OD ≈ 2×노즐 OD (관례). 강도계산서로 확정 필요 → HITL H2"
                )
        else:
            p.confidence = "unreadable"
            p.notes.append("노즐표에 해당 노즐 없음. 사람이 OD/ID 지정 필요 (H2)")
    return {
        "part_id": p.part_id,
        "part_type": p.part_type,
        "pad_od": p.pad_od,
        "pad_id": p.pad_id,
        "confidence": p.confidence,
        "notes": p.notes[-2:],
    }
