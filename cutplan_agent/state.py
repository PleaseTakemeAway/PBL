# -*- coding: utf-8 -*-
"""
에이전트가 매 step 읽고 쓰는 단일 상태(JobState) + trajectory 로그.

모든 skill 은 JobState 를 갱신하고 요약만 LLM 에 돌려준다 (큰 JSON 을 매번 context 에 넣지 않기 위해).
trajectory 는 (skill, args, result, dt, step) 리스트 → Phase 2 RL 의 학습 데이터.
"""

from __future__ import annotations

import functools
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from cutplan_agent.config import RUNS_DIR


class BomItem(BaseModel):
    item_no: str = ""
    part_name: str = ""
    material: str = ""
    thickness: Optional[float] = None
    qty: int = 1
    unit: str = "EA"
    size_text: str = ""  # 도면 표기 원문 (예: "t10", "Ø(210-124.3)", "2800x2949")
    weight_kg: Optional[float] = None
    source_drawing: str = ""
    unfold_class: str = (
        ""  # cylinder | cone_frustum | head | pad_ring | flat | formed | none
    )
    is_plate: bool = True
    confidence: str = "medium"
    notes: List[str] = Field(default_factory=list)


class PartSpec(BaseModel):
    """L2 가 채우고 L3 가 소비하는 부품 3D 파라미터 (툴킷 unfold.PartModel 의 확장)."""

    part_id: str
    part_name: str
    part_type: (
        str  # cylinder | cone_frustum | bent_sheet | flat | head | pad_ring | unknown
    )
    material: str = ""
    thickness: float = 0
    quantity: int = 1
    inner_dia: float = 0
    length: float = 0
    large_inner_dia: float = 0
    small_inner_dia: float = 0
    cone_height: float = 0
    head_type: str = "2:1 ellipsoidal"
    straight_flange: float = 50
    pad_od: float = 0
    pad_id: float = 0
    width: float = 0
    segments: List[float] = Field(default_factory=list)
    bend_angles: List[float] = Field(default_factory=list)
    bend_radii: List[float] = Field(default_factory=list)
    outline: List[List[float]] = Field(default_factory=list)
    seams: Dict[str, Any] = Field(
        default_factory=dict
    )  # 용접선 정보 (long_seams, circ_courses ...)
    confidence: str = "medium"
    notes: List[str] = Field(default_factory=list)


class Piece(BaseModel):
    """네스팅에 들어가는 조각 (전개 + 분할 + 여유 반영)."""

    piece_id: str
    part_id: str
    label: str
    material: str
    thickness: float
    w: float
    h: float
    shape: str = "rect"  # rect | circle | segment | sector | polygon
    qty: int = 1
    area: float = 0  # 실제 형상 면적 (활용률 계산용)
    outline: List[List[float]] = Field(default_factory=list)
    rot_ok: bool = True
    note: str = ""


class Placement(BaseModel):
    piece_id: str
    x: float
    y: float
    w: float
    h: float
    rot: float = 0


class Sheet(BaseModel):
    sheet_id: int
    material: str
    thickness: float
    w: float  # 폭
    l: float  # 길이
    qty: int = 1
    custom: bool = False
    placements: List[Placement] = Field(default_factory=list)
    utilization: float = 0
    gross_kg: float = 0
    net_kg: float = 0


class HitlEvent(BaseModel):
    point: str  # H1 전개 직전 | H2 자재목록 후 | H3 네스팅 후 | H4 구매의뢰
    question: str
    options: List[str] = Field(default_factory=list)
    answer: Optional[str] = None
    auto: bool = False
    step: int = 0


class JobState(BaseModel):
    job: str
    inputs: List[str] = Field(default_factory=list)
    drawings: List[Dict[str, Any]] = Field(
        default_factory=list
    )  # ingest 결과 (path, kind, pages, dxf, category)
    design_data: Dict[str, Any] = Field(default_factory=dict)  # GA 설계조건
    bom: List[BomItem] = Field(default_factory=list)
    parts: List[PartSpec] = Field(default_factory=list)
    flats: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )  # part_id -> 전개 결과
    pieces: List[Piece] = Field(default_factory=list)
    sheets: List[Sheet] = Field(default_factory=list)
    por: List[Dict[str, Any]] = Field(default_factory=list)
    verify: Dict[str, Any] = Field(default_factory=dict)
    hitl: List[HitlEvent] = Field(default_factory=list)
    hitl_policy: Dict[str, str] = Field(
        default_factory=lambda: {"H1": "ask", "H2": "ask", "H3": "auto", "H4": "ask"}
    )
    eval_mode: bool = False  # True 면 ask_human 이 GT/기본값으로 자동 응답

    # ---- 영속화 ----
    def run_dir(self) -> Path:
        d = RUNS_DIR / self.job
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self) -> str:
        p = self.run_dir() / "state.json"
        p.write_text(self.model_dump_json(indent=1, exclude_none=True), encoding="utf8")
        return str(p)

    @classmethod
    def load(cls, job: str) -> "JobState":
        p = RUNS_DIR / job / "state.json"
        return cls.model_validate_json(p.read_text(encoding="utf8"))


class Trajectory:
    """skill 호출 기록. RL 용 (state_summary, action, result, reward 자리)."""

    def __init__(self, job: str):
        self.job = job
        self.steps: List[Dict[str, Any]] = []

    def record(
        self,
        skill: str,
        args: Dict[str, Any],
        result: Any,
        dt: float,
        state: Optional[JobState] = None,
    ):
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "skill": skill,
                "args": _short(args),
                "result": _short(result),
                "dt": round(dt, 3),
                "state": {
                    "bom": len(state.bom),
                    "parts": len(state.parts),
                    "pieces": len(state.pieces),
                    "sheets": len(state.sheets),
                    "hitl": len(state.hitl),
                }
                if state
                else None,
                "reward": None,
            }
        )

    def save(self) -> str:
        d = RUNS_DIR / self.job
        d.mkdir(parents=True, exist_ok=True)
        p = d / "trajectory.json"
        p.write_text(
            json.dumps(self.steps, ensure_ascii=False, indent=1), encoding="utf8"
        )
        return str(p)


def _short(x: Any, limit: int = 2000) -> Any:
    try:
        s = json.dumps(x, ensure_ascii=False, default=str)
    except Exception:
        s = str(x)
    return (
        json.loads(s)
        if len(s) <= limit
        else s[:limit] + f"... (+{len(s) - limit} chars)"
    )


# 전역 컨텍스트: orchestrator 가 set 하고 skill 들이 참조
_CTX: Dict[str, Any] = {"state": None, "traj": None}


def set_context(state: JobState, traj: Trajectory):
    _CTX["state"], _CTX["traj"] = state, traj


def get_state() -> JobState:
    s = _CTX["state"]
    if s is None:
        raise RuntimeError("JobState 가 설정되지 않았다. set_context() 먼저.")
    return s


def logged(fn):
    """skill 호출을 trajectory 에 기록하는 데코레이터. 반환값은 JSON 직렬화 가능한 dict/str 이어야 한다."""

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        t0 = time.time()
        try:
            out = fn(*a, **kw)
        except Exception as e:  # 실패도 기록 (RL 에서 음의 reward)
            out = {"error": f"{type(e).__name__}: {e}"}
        traj, st = _CTX["traj"], _CTX["state"]
        if traj is not None:
            traj.record(
                fn.__name__,
                {**{f"arg{i}": v for i, v in enumerate(a)}, **kw},
                out,
                time.time() - t0,
                st,
            )
        return out

    return wrapper
