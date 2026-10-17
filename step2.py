"""Stage 2: establish shared-axis vertex and projected-edge correspondences."""
from itertools import combinations
from math import dist, isfinite
from geometry import geometry_lines, point_on_segment, project, segment_covered, supports_point
from models import DrawingView, ReconstructionCandidate


class ViewMatcher:
    def __init__(self, tolerance: float = 0.01, max_vertices: int = 500):
        if not isfinite(tolerance) or tolerance <= 0 or max_vertices < 1:
            raise ValueError("tolerance and max_vertices must be positive")
        self.tolerance, self.max_vertices = tolerance, max_vertices

    def match_vertices(self, views: list[DrawingView]) -> list[dict]:
        matches = []
        for left, right in combinations(views, 2):
            shared = set(left.axes) & set(right.axes)
            if len(shared) != 1:
                continue
            axis = next(iter(shared))
            left_points = sorted({p for line in geometry_lines(left) for p in line.points})
            right_points = sorted({p for line in geometry_lines(right) for p in line.points})
            for a in left_points:
                for b in right_points:
                    if abs(a[left.axes.index(axis)]-b[right.axes.index(axis)]) > self.tolerance:
                        continue
                    coords = dict(zip(left.axes, a))
                    coords.update(zip(right.axes, b))
                    coords[axis] = (a[left.axes.index(axis)]+b[right.axes.index(axis)])/2
                    point = tuple(coords[k] for k in range(3))
                    if not all(supports_point(view, project(point, view), self.tolerance) for view in views):
                        continue
                    if any(dist(point, m["position"]) <= self.tolerance for m in matches):
                        continue
                    matches.append({"position": point, "view_ids": [left.id, right.id], "shared_axis": "xyz"[axis]})
                    if len(matches) > self.max_vertices:
                        raise ValueError("Vertex limit exceeded; split the drawing into smaller parts")
        return matches

    def match_edges(self, vertices: list, views: list[DrawingView]) -> list[tuple[int, int]]:
        edges = []
        for i, j in combinations(range(len(vertices)), 2):
            a, b = vertices[i], vertices[j]
            if dist(a, b) <= self.tolerance:
                continue
            # Keep minimal segments rather than overlapping long and short edges.
            if any(k not in (i, j) and point_on_segment(p, a, b, self.tolerance) for k, p in enumerate(vertices)):
                continue
            if all(segment_covered(project(a, view), project(b, view), [p.points for p in geometry_lines(view)], self.tolerance) for view in views):
                edges.append((i, j))
        return edges

    def match_features(self, views: list[DrawingView]) -> list[dict]:
        # A projected circle alone cannot determine hole depth or feature topology.
        return [{"kind": "circle_observation", "view_id": view.id, "primitive_id": p.id, "center": p.center, "radius": p.radius, "normal_axis": "xyz"[next(iter(set(range(3))-set(view.axes)))], "requires_review": True} for view in views for p in view.primitives if p.kind == "circle" and p.line_type == "visible"]

    def check_projection_consistency(self, candidate: ReconstructionCandidate, views: list[DrawingView]) -> dict:
        unsupported, missing = [], []
        for view in views:
            projected = [(project(candidate.vertices[i], view), project(candidate.vertices[j], view)) for i, j in candidate.edges]
            source = [p.points for p in geometry_lines(view)]
            for index, edge in enumerate(projected):
                if not segment_covered(*edge, source, self.tolerance):
                    unsupported.append({"view": view.id, "edge": index})
            for primitive in geometry_lines(view):
                if not segment_covered(*primitive.points, projected, self.tolerance):
                    missing.append({"view": view.id, "primitive": primitive.id})
        return {"consistent": not unsupported and not missing, "unsupported_edges": unsupported, "missing_primitives": missing}
