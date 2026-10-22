"""
L1 인식(Perception) — "무엇이 어디에 적혀 있나". OCR 의 경계 안.

  ingest_drawing     DWG→DXF(libredwg) / PDF→PNG / DXF→PNG. 벡터·래스터 모두 PNG 를 만든다 (VLM 입력 통일)
  dxf_read_text      벡터 도면의 TEXT/MTEXT/DIMENSION 을 좌표와 함께 그대로 뽑는다 (정확한 숫자의 1차 출처)
  vlm_read_page      VLM 구조화 추출: title_block | bom | design_data | notes | dims
  normalize_bom      BOM 행 정규화(재질·두께·수량·단위·전개판정) → state.bom

VLM 호출은 Claude API (claude-opus-5-5) + structured output. ANTHROPIC_API_KEY 필요.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from cutplan_agent.config import (
    DWG2DXF,
    HANGUL_FONT_FILE,
    MAX_TOKENS,
    MODEL,
    UNFOLD_CLASS,
    VLM_MAX_PX,
)
from cutplan_agent.state import BomItem, get_state, logged


# ----------------------------------------------------------------------------- 파일 → 이미지
def _run_dir() -> Path:
    return get_state().run_dir()


def _dwg_to_dxf(dwg: Path) -> Path:
    out = _run_dir() / "dxf" / (dwg.stem + ".dxf")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1000:
        return out
    subprocess.run(
        [str(DWG2DXF), "-y", "-o", str(out), str(dwg)], capture_output=True, timeout=300
    )
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"dwg2dxf 실패: {dwg.name}")
    return out


def _render_dxf(dxf: Path, png: Path, target_px: int = VLM_MAX_PX) -> int:
    """툴킷 dwg2png.render 와 같은 방식(ezdxf matplotlib 백엔드, 한글 폰트 재매핑)."""
    import ezdxf
    import matplotlib
    from ezdxf import bbox
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    doc = ezdxf.readfile(str(dxf))
    if "KO_MALGUN" not in doc.styles:
        doc.styles.add("KO_MALGUN", font=HANGUL_FONT_FILE)
    hangul = re.compile(r"[가-힣]")
    for e in doc.entitydb.values():
        t = e.dxftype()
        txt = (
            e.text
            if t == "MTEXT"
            else e.dxf.get("text", "")
            if t in ("TEXT", "ATTRIB", "ATTDEF")
            else ""
        )
        if txt and hangul.search(txt):
            e.dxf.style = "KO_MALGUN"
    msp = doc.modelspace()
    ext = bbox.extents(msp, fast=True)
    w, h = (ext.size.x, ext.size.y) if ext.has_data else (1.0, 1.0)
    ar = (w / h) if h else 1.0
    dpi = 200
    fw, fh = (
        (target_px / dpi, target_px / dpi / ar)
        if ar >= 1
        else (target_px / dpi * ar, target_px / dpi)
    )
    fig = plt.figure(figsize=(max(fw, 2), max(fh, 2)), dpi=dpi)
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
    fig.set_size_inches(
        max(fw, 2), max(fh, 2), forward=True
    )  # ezdxf finalize 가 figure 크기를 줄여 놓으므로 되돌린다
    fig.savefig(str(png), dpi=dpi, facecolor="white")
    plt.close(fig)
    return len(list(msp))


def _render_pdf(pdf: Path, out_dir: Path, dpi: int = 220) -> List[str]:
    import pymupdf

    doc = pymupdf.open(str(pdf))
    pages = []
    for i, pg in enumerate(doc):
        long_in = max(pg.rect.width, pg.rect.height) / 72.0
        use = min(dpi, int(VLM_MAX_PX / long_in))
        p = out_dir / f"{pdf.stem}_p{i + 1:02d}.png"
        if not p.exists():
            pg.get_pixmap(dpi=use).save(str(p))
        pages.append(str(p))
    return pages


@logged
def ingest_drawing(path: str) -> dict:
    """도면 파일(dwg/dxf/pdf/png)을 읽어 PNG 페이지와 (벡터면) DXF 를 준비하고 state.drawings 에 등록한다.
    반환: {"index", "kind": "vector|raster", "pages": [...], "dxf": ...}"""
    st = get_state()
    src = Path(path)
    if not src.exists():
        return {"error": f"파일 없음: {path}"}
    img_dir = _run_dir() / "pages"
    img_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    rec: Dict[str, Any] = {
        "path": str(src),
        "name": src.name,
        "kind": "",
        "dxf": "",
        "pages": [],
        "category": "",
        "entities": 0,
    }
    if ext in (".dwg", ".dxf"):
        dxf = _dwg_to_dxf(src) if ext == ".dwg" else src
        png = img_dir / (src.stem + ".png")
        if not png.exists():
            rec["entities"] = _render_dxf(dxf, png)
        rec.update(kind="vector", dxf=str(dxf), pages=[str(png)])
    elif ext == ".pdf":
        rec.update(kind="raster", pages=_render_pdf(src, img_dir))
    elif ext in (".png", ".jpg", ".jpeg"):
        rec.update(kind="raster", pages=[str(src)])
    else:
        return {"error": f"지원하지 않는 형식: {ext}"}
    for i, d in enumerate(st.drawings):
        if d["path"] == rec["path"]:
            st.drawings[i] = rec
            return {
                "index": i,
                **{k: rec[k] for k in ("kind", "pages", "dxf", "entities")},
            }
    st.drawings.append(rec)
    return {
        "index": len(st.drawings) - 1,
        **{k: rec[k] for k in ("kind", "pages", "dxf", "entities")},
    }


# ----------------------------------------------------------------------------- 벡터 텍스트
_FMT = re.compile(r"\{?\\[A-Za-z][^;]*;")


def _clean(s: str) -> str:
    return re.sub(
        r"\s+", " ", _FMT.sub("", s or "").replace("}", "").replace("\\P", " | ")
    ).strip()


@logged
def dxf_read_text(drawing_index: int, max_items: int = 600, pattern: str = "") -> dict:
    """벡터 도면(DXF)의 텍스트·치수를 좌표와 함께 뽑는다. pattern(정규식)으로 필터 가능.
    치수(DIMENSION)는 측정값과 표기 텍스트를 같이 준다. 숫자의 정확한 1차 출처."""
    import ezdxf

    st = get_state()
    d = st.drawings[drawing_index]
    if not d.get("dxf"):
        return {"error": "벡터 도면이 아니다 (dxf 없음). vlm_read_page 를 써라."}
    doc = ezdxf.readfile(d["dxf"])
    msp = doc.modelspace()
    rx = re.compile(pattern, re.I) if pattern else None
    texts, dims = [], []
    for e in msp:
        t = e.dxftype()
        if t in ("TEXT", "MTEXT", "ATTRIB"):
            s = _clean(e.text if t == "MTEXT" else e.dxf.get("text", ""))
            if not s or (rx and not rx.search(s)):
                continue
            p = e.dxf.insert
            hgt = (
                e.dxf.get("char_height", 0) if t == "MTEXT" else e.dxf.get("height", 0)
            )
            texts.append(
                {
                    "text": s,
                    "x": round(p.x, 1),
                    "y": round(p.y, 1),
                    "layer": e.dxf.layer,
                    "h": round(float(hgt or 0), 1),
                }
            )
        elif t == "DIMENSION":
            try:
                meas = e.get_measurement()
                meas = (
                    round(float(meas), 2)
                    if isinstance(meas, (int, float))
                    else str(meas)
                )
            except Exception:
                meas = None
            txt = _clean(e.dxf.get("text", ""))
            if rx and not (rx.search(str(meas)) or rx.search(txt)):
                continue
            p = e.dxf.get("defpoint", None)
            dims.append(
                {
                    "measurement": meas,
                    "text_override": txt,
                    "dimtype": int(e.dxf.dimtype) & 7,
                    "x": round(p.x, 1) if p else None,
                    "y": round(p.y, 1) if p else None,
                    "layer": e.dxf.layer,
                }
            )
    out = {
        "drawing": d["name"],
        "n_texts": len(texts),
        "n_dims": len(dims),
        "texts": texts[:max_items],
        "dims": dims[:max_items],
    }
    if len(texts) > max_items or len(dims) > max_items:
        out["note"] = f"max_items={max_items} 로 잘렸다. pattern 으로 좁혀라."
    return out


# ----------------------------------------------------------------------------- VLM 구조화 추출
class TitleBlock(BaseModel):
    drawing_no: str = ""
    title: str = ""
    project: str = ""
    customer: str = ""
    workorder: str = ""
    scale: str = ""
    rev: str = ""
    date: str = ""


class BomRowRaw(BaseModel):
    item_no: str = ""
    part_name: str = ""
    material: str = ""
    qty_text: str = ""
    unit: str = ""
    size_text: str = Field(
        "", description="SIZE/DIMENSION 칸 원문 그대로 (예: t10, Ø21.3x25L, 2800x2949)"
    )
    weight_text: str = ""
    remark: str = ""


class BomTable(BaseModel):
    rows: List[BomRowRaw]
    table_location: str = Field("", description="표가 도면 어디에 있는지 (예: 우하단)")
    confidence: str = "medium"
    notes: List[str] = Field(default_factory=list)


class DesignData(BaseModel):
    code: str = ""
    design_pressure: Dict[str, str] = Field(
        default_factory=dict, description="{'shell': '7.0', 'tube': '10.5'} (kg/cm2)"
    )
    design_temperature: Dict[str, str] = Field(default_factory=dict)
    corrosion_allowance: Dict[str, str] = Field(default_factory=dict)
    joint_efficiency: Dict[str, str] = Field(default_factory=dict)
    radiography: Dict[str, str] = Field(default_factory=dict)
    mdmt: str = ""
    shell_id: str = ""
    material_spec: Dict[str, str] = Field(
        default_factory=dict,
        description="{'SHELL': 'SA516-70N', 'HEAD': ..., 'REINF. PAD': ...}",
    )
    nozzle_list: List[Dict[str, str]] = Field(
        default_factory=list,
        description="[{'mark','qty','size','rating','reinf_pad_od','service'}]",
    )
    notes: List[str] = Field(default_factory=list)


class DimItem(BaseModel):
    text: str
    kind: str = Field(
        "linear",
        description="linear | diameter | radius | angle | label | revision | note",
    )
    view: str = Field(
        "",
        description="어느 뷰에 속하나 (예: 'WELDING SEAM PLAN', 'VIEW X', 'SECTION Y')",
    )
    x_frac: float = Field(0, description="페이지 폭 대비 0~1")
    y_frac: float = Field(0, description="페이지 높이 대비 0~1 (위가 0)")
    attached_to: str = Field(
        "",
        description="어느 형상·부품의 어떤 치수인지 추정 (예: 'SHELL I.D', 'TL to TL', 'SA-02 course length')",
    )


class DimList(BaseModel):
    items: List[DimItem]
    views: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Notes(BaseModel):
    notes: List[str]
    formed_parts: List[str] = Field(
        default_factory=list,
        description="성형해석/드로잉 등 전개 불가를 암시하는 노트가 가리키는 부품",
    )


_SCHEMAS = {
    "title_block": TitleBlock,
    "bom": BomTable,
    "design_data": DesignData,
    "dims": DimList,
    "notes": Notes,
}

_PROMPTS = {
    "title_block": "이 도면의 표제란(우하단 TITLE BLOCK)을 읽어라. 도면번호(DWG NO), 제목(TITLE), 프로젝트, 고객, 워크오더(KDM W/O NO), 척도, 리비전, 날짜.",
    "bom": (
        "이 도면의 BOM/PART LIST 표를 모든 행 그대로 옮겨라. 열 경계는 표선 기준. SIZE 칸은 원문 그대로(t10, Ø21.3x25L, H350x350x12x19 ...). "
        "수량 단위(EA/SET/SH'T)와 중량이 있으면 함께. 표가 여러 개면 전부. 읽지 못한 칸은 빈 문자열, notes 에 이유."
    ),
    "design_data": "GA 도면의 DESIGN DATA 표, MATERIAL SPECIFICATION 표, NOZZLE LIST 표를 읽어라. SHELL SIDE / TUBE SIDE 열을 구분. 노즐표의 보강패드(REINF. PAD) 정보가 있으면 반드시 포함.",
    "dims": (
        "이 도면의 치수·라벨 텍스트를 모두 나열하되, 각 항목이 어느 뷰에 있고 어느 형상의 어떤 치수인지(attached_to) 추정하라. "
        "△ 안 숫자는 revision, 풍선 안 숫자는 label. I.D/O.D/T.L 접두를 보존하라. 위치는 페이지 비율 좌표."
    ),
    "notes": "도면의 NOTE 항목을 모두 옮기고, 성형해석·드로잉·프레스 등 전개 불가를 암시하는 노트가 어느 부품을 가리키는지 적어라.",
}


def _client():
    from cutplan_agent.client import (
        make_client,  # ANTHROPIC_WORKSPACE_ID 가 있으면 anthropic-workspace-id 헤더를 붙인다
    )

    return make_client()


def _image_block(png_path: str) -> dict:
    data = base64.standard_b64encode(Path(png_path).read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": data},
    }


def _strict_schema(model: type[BaseModel]) -> dict:
    """pydantic 스키마를 structured output 이 받는 형태로 (additionalProperties:false, title 제거)."""

    def fix(node):
        if isinstance(node, dict):
            node.pop("title", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                props = node.get("properties", {})
                node["required"] = list(props.keys())
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    s = model.model_json_schema()
    fix(s)
    return s


def vlm_parse(
    png_paths: List[str], prompt: str, schema: type[BaseModel], system: str = ""
) -> BaseModel:
    """이미지 + 지시 → pydantic 모델. refusal 은 예외로 올린다."""
    client = _client()
    content = [_image_block(p) for p in png_paths] + [{"type": "text", "text": prompt}]
    kw: Dict[str, Any] = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": _strict_schema(schema)},
        },
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if system:
        kw["system"] = system
    resp = client.beta.messages.create(**kw)
    if resp.stop_reason == "refusal":
        raise RuntimeError(
            f"모델이 거부: {getattr(resp.stop_details, 'explanation', '')}"
        )
    text = next(b.text for b in resp.content if b.type == "text")
    return schema.model_validate(json.loads(text))


@logged
def vlm_read_page(
    drawing_index: int, what: str, page: int = 1, extra_instruction: str = ""
) -> dict:
    """VLM 으로 도면 페이지에서 구조화 정보를 뽑는다. what: title_block | bom | design_data | dims | notes.
    결과는 state.drawings[i]['extract'][what] 에 저장되고 요약을 돌려준다."""
    st = get_state()
    d = st.drawings[drawing_index]
    if what not in _SCHEMAS:
        return {"error": f"what 은 {list(_SCHEMAS)} 중 하나"}
    png = d["pages"][page - 1]
    system = (
        "너는 압력용기·열교환기 제작사의 도면 판독 담당자다. 적힌 것을 적힌 대로 옮기고, 없는 값은 지어내지 않는다. "
        "숫자는 mm, 중량은 kg. 읽기 어려운 글자는 notes 에 적는다."
    )
    out = vlm_parse(
        [png],
        _PROMPTS[what]
        + ("\n추가 지시: " + extra_instruction if extra_instruction else ""),
        _SCHEMAS[what],
        system,
    )
    d.setdefault("extract", {})[what] = out.model_dump()
    data = out.model_dump()
    if what == "bom":
        return {
            "n_rows": len(data["rows"]),
            "rows": data["rows"],
            "notes": data["notes"],
        }
    return data


# ----------------------------------------------------------------------------- BOM 정규화
_THK = re.compile(
    r"(?:^|[^\d.])t\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*[tT](?![a-zA-Z])|THK\.?\s*(\d+(?:\.\d+)?)",
    re.I,
)
_PLATE_MAT = re.compile(
    r"^(SA|A)\s?(516|283|285|240|387|36|204)|^SS\s?400|^S(S|US)\s?3\d{2}|^B168|^A240|^SPCC|^SPHC|^St\s?37",
    re.I,
)
_NON_PLATE = re.compile(
    r"SA\s?106|SA\s?105|SA\s?182|SA\s?193|SA\s?194|SA\s?312|SA\s?403|SA\s?234|S20C|SCH\s?\d|NUT|BOLT|GASKET|PIPE|FLANGE|STUD|PLUG|SOCKET|H\d{3}x",
    re.I,
)


def _unfold_class(name: str, size_text: str) -> str:
    n = name.upper()
    if "PIPE" in size_text.upper() or "SCH" in size_text.upper():
        return "none"
    for cls, keys in UNFOLD_CLASS.items():
        if any(k in n for k in keys):
            # PAD 는 'REINF. PAD' 와 'LEG PAD'(평판) 를 구분
            if cls == "pad_ring" and (
                "LEG" in n or "LUG" in n or "WEAR" in n or "SUPPORT" in n
            ):
                return "flat"
            return cls
    return "unknown"


@logged
def normalize_bom(
    drawing_index: int,
    rows: Optional[List[dict]] = None,
    default_thickness_from_material: bool = True,
) -> dict:
    """VLM 이 읽은 BOM 행(또는 직접 준 rows)을 정규화해 state.bom 에 넣는다.
    재질 패턴으로 판재 여부, 이름 키워드로 전개 판정(unfold_class)을 붙인다."""
    st = get_state()
    d = st.drawings[drawing_index]
    rows = (
        rows
        if rows is not None
        else d.get("extract", {}).get("bom", {}).get("rows", [])
    )
    added = []
    for r in rows:
        name, mat, size = (
            r.get("part_name", ""),
            r.get("material", ""),
            r.get("size_text", ""),
        )
        thk = None
        for src in (size, mat if default_thickness_from_material else ""):
            m = _THK.search(src or "")
            if m:
                thk = float(next(g for g in m.groups() if g))
                break
        qty_m = re.search(r"\d+", r.get("qty_text", "") or "")
        qty = int(qty_m.group()) if qty_m else 1
        unit = (r.get("unit") or "").upper() or (
            "SET" if "SET" in (r.get("qty_text", "") or "").upper() else "EA"
        )
        is_plate = bool(_PLATE_MAT.search(mat or "")) and not _NON_PLATE.search(
            f"{mat} {size} {name}"
        )
        wt = None
        wm = re.search(r"\d+(?:\.\d+)?", (r.get("weight_text") or "").replace(",", ""))
        if wm:
            wt = float(wm.group())
        item = BomItem(
            item_no=r.get("item_no", ""),
            part_name=name,
            material=mat,
            thickness=thk,
            qty=qty,
            unit=unit,
            size_text=size,
            weight_kg=wt,
            source_drawing=d["name"],
            unfold_class=_unfold_class(name, size) if is_plate else "none",
            is_plate=is_plate,
            confidence="high" if (thk is not None and is_plate) else "medium",
        )
        if is_plate and thk is None:
            item.notes.append("두께를 읽지 못함")
        st.bom.append(item)
        added.append(
            {
                "item_no": item.item_no,
                "part_name": item.part_name,
                "material": item.material,
                "t": item.thickness,
                "qty": item.qty,
                "unit": item.unit,
                "is_plate": item.is_plate,
                "unfold_class": item.unfold_class,
            }
        )
    plates = [a for a in added if a["is_plate"]]
    return {
        "added": len(added),
        "plates": len(plates),
        "items": added,
        "bom_index_range": [len(st.bom) - len(added), len(st.bom) - 1],
    }
