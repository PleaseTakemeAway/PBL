"""Shared, serializable data contracts for the six reconstruction stages."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

Point2D = tuple[float, float]
Point3D = tuple[float, float, float]
VIEW_AXES = {"front": (0, 2), "top": (0, 1), "right": (1, 2)}


def point2(value: Any) -> Point2D:
    if len(value) != 2:
        raise ValueError("A drawing point must contain two coordinates")
    result = tuple(float(v) for v in value)
    if not all(isfinite(v) for v in result):
        raise ValueError("Coordinates must be finite")
    return result


@dataclass
class Primitive2D:
    id: str
    kind: str
    points: list[Point2D] = field(default_factory=list)
    center: Point2D | None = None
    radius: float | None = None
    line_type: str = "visible"
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Primitive2D:
        primitive = cls(
            id=str(value["id"]), kind=str(value.get("kind", "line")).lower(),
            points=[point2(p) for p in value.get("points", [])],
            center=point2(value["center"]) if value.get("center") is not None else None,
            radius=float(value["radius"]) if value.get("radius") is not None else None,
            line_type=str(value.get("line_type", "visible")),
            attributes=dict(value.get("attributes", {})),
        )
        if primitive.kind == "line" and len(primitive.points) != 2:
            raise ValueError(f"Line {primitive.id} requires exactly two points")
        if primitive.kind == "circle" and (
            primitive.center is None or primitive.radius is None
            or not isfinite(primitive.radius) or primitive.radius <= 0
        ):
            raise ValueError(f"Circle {primitive.id} requires a center and positive radius")
        if primitive.kind not in {"line", "circle"}:
            raise ValueError(f"Unsupported primitive: {primitive.kind}")
        return primitive


@dataclass
class DrawingView:
    id: str
    name: str
    primitives: list[Primitive2D]
    annotations: list[dict[str, Any]] = field(default_factory=list)
    origin: Point2D | None = None
    scale: float = 1.0
    alignment: dict[str, Any] = field(default_factory=dict)

    @property
    def axes(self) -> tuple[int, int]:
        return VIEW_AXES[self.name]


@dataclass
class DrawingDocument:
    views: list[DrawingView]
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any], source: str | None = None) -> DrawingDocument:
        views = [DrawingView(
            id=str(v["id"]), name=str(v.get("name", v["id"])),
            primitives=[Primitive2D.from_dict(p) for p in v.get("primitives", [])],
            annotations=list(v.get("annotations", [])),
            origin=point2(v["origin"]) if v.get("origin") is not None else None,
            scale=float(v.get("scale", 1.0)),
        ) for v in value.get("views", [])]
        if not views or len({v.id for v in views}) != len(views):
            raise ValueError("Drawing must have views with unique IDs")
        for view in views:
            if not isfinite(view.scale) or view.scale <= 0:
                raise ValueError("View scale must be positive and finite")
            if len({p.id for p in view.primitives}) != len(view.primitives):
                raise ValueError(f"Duplicate primitive ID in {view.id}")
        return cls(views, dict(value.get("metadata", {})), source)


@dataclass
class ReconstructionCandidate:
    id: str
    vertices: list[Point3D]
    edges: list[tuple[int, int]]
    features: list[dict[str, Any]] = field(default_factory=list) # Feature 설계를 어떻게 진행하는가?
    parameters: dict[str, Any] = field(default_factory=dict) # 뭐에 대한 parameters?
    provenance: list[dict[str, Any]] = field(default_factory=list) 
    score: float = 0.0

    @property
    def extents(self) -> Point3D:
        if not self.vertices:
            return (0.0, 0.0, 0.0)
        return tuple(max(p[a] for p in self.vertices) - min(p[a] for p in self.vertices) for a in range(3))


@dataclass
class CheckResult:
    status: str  # pass, fail, or unknown; unknown never implies validation.
    messages: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateEvaluation:
    candidate_id: str
    valid: bool
    score: float
    checks: dict[str, CheckResult]


@dataclass
class ReconstructionResult:
    metadata: dict[str, Any]
    views: list[DrawingView]
    candidates: list[ReconstructionCandidate]
    evaluations: list[CandidateEvaluation]
    review_request: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
