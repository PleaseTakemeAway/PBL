"""Stage 4: distinguish verified, failed, and unavailable checks."""

from collections import defaultdict
from math import dist, isfinite

from models import CandidateEvaluation, CheckResult, ReconstructionCandidate
from step2 import ViewMatcher


class CandidateEvaluator:
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = tolerance
        self.matcher = ViewMatcher(tolerance)

    def validate_geometry(self, candidate: ReconstructionCandidate) -> CheckResult:
        errors = []
        if len(candidate.vertices) < 2 or not candidate.edges:
            errors.append("At least two vertices and one edge are required")
        if any(
            len(p) != 3 or not all(isfinite(v) for v in p) for p in candidate.vertices
        ):
            errors.append("Vertices must be finite 3D coordinates")
            return CheckResult("fail", errors)
        if len({tuple(sorted(edge)) for edge in candidate.edges}) != len(
            candidate.edges
        ):
            errors.append("Duplicate edges")
        for i, j in candidate.edges:
            if not (
                0 <= i < len(candidate.vertices) and 0 <= j < len(candidate.vertices)
            ):
                errors.append(f"Invalid edge indices: {(i, j)}")
            elif (
                i == j
                or dist(candidate.vertices[i], candidate.vertices[j]) <= self.tolerance
            ):
                errors.append(f"Zero-length edge: {(i, j)}")
        return CheckResult("fail" if errors else "pass", errors)

    def check_reprojection(
        self, candidate: ReconstructionCandidate, views: list
    ) -> CheckResult:
        result = self.matcher.check_projection_consistency(candidate, views)
        return CheckResult(
            "pass" if result["consistent"] else "fail",
            []
            if result["consistent"]
            else ["Candidate does not cover the supplied drawing geometry"],
            result,
        )

    def check_dimensions(
        self, candidate: ReconstructionCandidate, metadata: dict, views: list
    ) -> CheckResult:
        dimensions = list(metadata.get("dimensions", {}).items())
        dimensions += [
            (a["axis"], a["value"])
            for v in views
            for a in v.annotations
            if a.get("kind") == "dimension"
            and a.get("axis") in {"x", "y", "z"}
            and a.get("value") is not None
        ]
        if not dimensions:
            return CheckResult(
                "unknown", ["No explicit axis extent dimensions supplied"]
            )
        errors, comparisons = [], []
        for axis, expected in dimensions:
            if axis not in {"x", "y", "z"} or not isfinite(expected) or expected <= 0:
                errors.append(f"Invalid extent dimension: {axis}={expected}")
                continue
            actual = candidate.extents["xyz".index(axis)]
            comparisons.append({"axis": axis, "expected": expected, "actual": actual})
            if abs(actual - expected) > self.tolerance:
                errors.append(
                    f"Dimension mismatch on {axis}: {actual} vs {expected} mm"
                )
        return CheckResult(
            "fail" if errors else "pass", errors, {"comparisons": comparisons}
        )

    def check_physical_constraints(
        self, candidate: ReconstructionCandidate
    ) -> CheckResult:
        errors = []
        thickness = candidate.parameters.get("sheet_thickness")
        if thickness is not None and (
            not isfinite(thickness)
            or thickness <= 0
            or thickness > max(candidate.extents) + self.tolerance
        ):
            errors.append(
                "Sheet thickness is nonpositive or exceeds every bounding extent"
            )
        adjacency = defaultdict(set)
        for i, j in candidate.edges:
            adjacency[i].add(j)
            adjacency[j].add(i)
        seen, pending = set(), [0] if candidate.vertices else []
        while pending:
            vertex = pending.pop()
            if vertex not in seen:
                seen.add(vertex)
                pending.extend(adjacency[vertex] - seen)
        if len(seen) != len(candidate.vertices):
            errors.append("Wireframe is disconnected or contains isolated vertices")
        if errors:
            return CheckResult("fail", errors)
        return CheckResult(
            "unknown",
            [
                "Wireframe connectivity checked; volume, collisions, and solid closure require a CAD solid"
            ],
            {"connected": True},
        )

    def check_manufacturability(
        self, candidate: ReconstructionCandidate
    ) -> CheckResult:
        rules = candidate.parameters.get("manufacturing", {})
        errors = []
        for key in ("minimum_hole_diameter", "minimum_bend_radius"):
            if key in rules and (not isfinite(rules[key]) or rules[key] <= 0):
                errors.append(f"Invalid manufacturing constraint: {key}")
        for feature in candidate.features:
            if feature.get("kind") == "hole" and "minimum_hole_diameter" in rules:
                if (
                    feature["radius"] * 2
                    < rules["minimum_hole_diameter"] - self.tolerance
                ):
                    errors.append(
                        "Hole diameter is below the supplied manufacturing limit"
                    )
        return CheckResult(
            "fail" if errors else "unknown",
            errors
            or [
                "Bend radii, tool access, and sheet unfolding require confirmed solid features"
            ],
            {"provided_rules": rules},
        )

    def rank_candidates(
        self, candidates: list[ReconstructionCandidate], views: list, metadata: dict
    ) -> tuple[list[ReconstructionCandidate], list[CandidateEvaluation]]:
        evaluations = []
        for candidate in candidates:
            checks = {"geometry": self.validate_geometry(candidate)}
            if checks["geometry"].status == "fail":
                checks.update(
                    {
                        name: CheckResult(
                            "unknown", ["Skipped because geometry is invalid"]
                        )
                        for name in (
                            "reprojection",
                            "dimensions",
                            "physical",
                            "manufacturability",
                        )
                    }
                )
            else:
                checks.update(
                    reprojection=self.check_reprojection(candidate, views),
                    dimensions=self.check_dimensions(candidate, metadata, views),
                    physical=self.check_physical_constraints(candidate),
                    manufacturability=self.check_manufacturability(candidate),
                )
            weights = {
                "geometry": 1,
                "reprojection": 3,
                "dimensions": 2,
                "physical": 1,
                "manufacturability": 1,
            }
            known = sum(
                weights[name]
                for name, check in checks.items()
                if check.status != "unknown"
            )
            score = (
                100
                * sum(
                    weights[name]
                    for name, check in checks.items()
                    if check.status == "pass"
                )
                / known
                if known
                else 0.0
            )
            candidate.score = round(score, 3)
            evaluations.append(
                CandidateEvaluation(
                    candidate.id,
                    all(c.status != "fail" for c in checks.values()),
                    candidate.score,
                    checks,
                )
            )
        lookup = {e.candidate_id: e for e in evaluations}
        ranked = sorted(
            candidates, key=lambda c: (not lookup[c.id].valid, -c.score, c.id)
        )
        return ranked, [lookup[c.id] for c in ranked]
