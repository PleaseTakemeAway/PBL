"""Stage 1: interpret drawing metadata and normalize orthographic views."""

from copy import deepcopy
from math import dist, isfinite

from models import VIEW_AXES, DrawingDocument, DrawingView


class DrawingInterpreter:
    UNIT_FACTORS = {
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "inch": 25.4,
        "in": 25.4,
    }  # 원래 커팅 플랜은 그럼 단위를 뭐로 통일 했음?

    def extract_metadata(self, drawing: DrawingDocument) -> dict:
        metadata = deepcopy(
            drawing.metadata
        )  # Metadata의 구조? 어떤 식으로 받아와서 연산 하는거야
        units = metadata.get("units")
        if units not in self.UNIT_FACTORS:
            raise ValueError("Specify drawing units: mm, cm, m, or inch")
        scale = float(metadata.get("drawing_scale", 1.0))
        if not isfinite(scale) or scale <= 0:
            raise ValueError("drawing_scale must be positive and finite (1:2 = 0.5)")
        factor = self.UNIT_FACTORS[units]
        metadata.update(
            source=drawing.source,
            source_units=units,
            units="mm",
            coordinate_factor=factor / scale,
            dimension_factor=factor,
        )
        metadata["dimensions"] = {
            axis: float(value) * factor
            for axis, value in metadata.get("dimensions", {}).items()
        }
        if any(
            axis not in {"x", "y", "z"} or not isfinite(value) or value <= 0
            for axis, value in metadata["dimensions"].items()
        ):
            raise ValueError(
                "Extent dimensions must have x/y/z axes and positive finite values"
            )
        if metadata.get("sheet_thickness") is not None:
            metadata["sheet_thickness"] = float(metadata["sheet_thickness"]) * factor
            if (
                not isfinite(metadata["sheet_thickness"])
                or metadata["sheet_thickness"] <= 0
            ):
                raise ValueError("sheet_thickness must be positive and finite")
        rules = metadata.get("manufacturing", {})
        for name in ("minimum_hole_diameter", "minimum_bend_radius"):
            if name in rules:
                rules[name] = float(rules[name]) * factor
                if not isfinite(rules[name]) or rules[name] <= 0:
                    raise ValueError(f"{name} must be positive and finite")
        return metadata

    def segment_views(self, drawing: DrawingDocument) -> list[DrawingView]:
        # View boundaries come from JSON groups or FRONT/TOP/RIGHT DXF layers.
        # Raster view segmentation can be added by replacing this adapter.
        return deepcopy(drawing.views)

    def identify_views(self, views: list[DrawingView]) -> list[DrawingView]:
        aliases = {"정면도": "front", "평면도": "top", "우측면도": "right"}
        for view in views:
            view.name = aliases.get(view.name, view.name.lower())
            if view.name not in VIEW_AXES:
                raise ValueError(f"Unknown view {view.name}; use front, top, or right")
        if len({v.name for v in views}) != len(views):
            raise ValueError("Only one view per orientation is supported")
        return views

    def align_views(
        self, views: list[DrawingView], metadata: dict
    ) -> list[DrawingView]:
        for view in views:
            points = [point for p in view.primitives for point in p.points]
            for p in view.primitives:
                if p.kind == "circle":
                    points.extend(
                        [
                            (p.center[0] - p.radius, p.center[1] - p.radius),
                            (p.center[0] + p.radius, p.center[1] + p.radius),
                        ]
                    )
            if not points:
                raise ValueError(f"View {view.id} contains no geometry")
            origin = (
                view.origin
                if view.origin is not None
                else tuple(min(p[a] for p in points) for a in range(2))
            )
            factor = metadata["coordinate_factor"] / view.scale

            def transform(point):
                return tuple((point[a] - origin[a]) * factor for a in range(2))

            for primitive in view.primitives:
                primitive.points = [transform(p) for p in primitive.points]
                if primitive.center is not None:
                    primitive.center = transform(primitive.center)
                    primitive.radius *= factor
            for annotation in view.annotations:
                if annotation.get("position") is not None:
                    annotation["position"] = transform(annotation["position"])
                if (
                    annotation.get("kind") == "dimension"
                    and annotation.get("value") is not None
                ):
                    annotation["value"] = (
                        float(annotation["value"]) * metadata["dimension_factor"]
                    )
                    if not isfinite(annotation["value"]) or annotation["value"] <= 0:
                        raise ValueError(
                            "Annotation dimensions must be positive and finite"
                        )
            view.alignment = {
                "source_origin": origin,
                "coordinate_factor": factor,
                "origin_inferred": view.origin is None,
            }
            view.origin, view.scale = (0.0, 0.0), 1.0
        return views

    def classify_lines(self, views: list[DrawingView]) -> list[DrawingView]:
        for view in views:
            for primitive in view.primitives:
                style = str(primitive.attributes.get("linetype", "")).upper()
                if "CENTER" in style or "DASHDOT" in style:
                    primitive.line_type = "center"
                elif "HIDDEN" in style or "DASHED" in style:
                    primitive.line_type = "hidden"
                if primitive.line_type not in {
                    "visible",
                    "hidden",
                    "center",
                    "dimension",
                }:
                    raise ValueError(f"Unknown line_type for {primitive.id}")
        return views

    def extract_primitives(self, views: list[DrawingView]) -> dict:
        return {
            view.id: {
                "lines": [p for p in view.primitives if p.kind == "line"],
                "circles": [p for p in view.primitives if p.kind == "circle"],
            }
            for view in views
        }

    def associate_annotations(self, views: list[DrawingView]) -> list[DrawingView]:
        for view in views:
            for annotation in view.annotations:
                if annotation.get("primitive_id") is not None:
                    if annotation["primitive_id"] not in {
                        p.id for p in view.primitives
                    }:
                        raise ValueError(
                            f"Annotation refers to unknown primitive {annotation['primitive_id']}"
                        )
                    continue
                if annotation.get("position") is not None:

                    def distance(primitive):
                        point = primitive.center or tuple(
                            sum(p[a] for p in primitive.points) / len(primitive.points)
                            for a in range(2)
                        )
                        return dist(annotation["position"], point)

                    annotation["suggested_primitive_id"] = min(
                        view.primitives, key=distance
                    ).id
                    annotation["association_requires_review"] = True
        return views


# Compatibility with the misspelling in the original draft.
DrawingInterprete = DrawingInterpreter
