"""Tolerance-aware projection and finite segment coverage helpers."""

from math import dist

from models import DrawingView, Point2D, Point3D


def project(point: Point3D, view: DrawingView) -> Point2D:
    return tuple(point[axis] for axis in view.axes)


def geometry_lines(view: DrawingView):
    return [
        p
        for p in view.primitives
        if p.kind == "line" and p.line_type in {"visible", "hidden"}
    ]


def point_on_segment(point, start, end, tolerance: float) -> bool:
    length2 = sum((b - a) ** 2 for a, b in zip(start, end))
    if length2 <= tolerance**2:
        return dist(point, start) <= tolerance
    t = sum((p - a) * (b - a) for p, a, b in zip(point, start, end)) / length2
    closest = tuple(a + max(0.0, min(1.0, t)) * (b - a) for a, b in zip(start, end))
    return dist(point, closest) <= tolerance


def segment_covered(start: Point2D, end: Point2D, segments, tolerance: float) -> bool:
    length = dist(start, end)
    if length <= tolerance:
        return True  # An edge perpendicular to this view projects to a point.
    dx, dy = end[0] - start[0], end[1] - start[1]
    intervals = []
    for a, b in segments:
        if any(
            abs((p[0] - start[0]) * dy - (p[1] - start[1]) * dx) / length > tolerance
            for p in (a, b)
        ):
            continue
        ts = [
            ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / (length * length)
            for p in (a, b)
        ]
        intervals.append((max(0.0, min(ts)), min(1.0, max(ts))))
    covered = 0.0
    for low, high in sorted(intervals):
        if high < low or low > covered + tolerance / length:
            continue
        covered = max(covered, high)
    return covered >= 1.0 - tolerance / length


def supports_point(view: DrawingView, point: Point2D, tolerance: float) -> bool:
    return any(
        point_on_segment(point, *p.points, tolerance) for p in geometry_lines(view)
    )
