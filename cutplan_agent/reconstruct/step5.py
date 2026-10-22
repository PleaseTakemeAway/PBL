"""Stage 5: preserve unresolved evidence as a structured human review request."""


class AmbiguityResolver:
    def detect_ambiguities(
        self, candidates: list, evaluations: list, views: list, metadata: dict
    ) -> list[dict]:
        issues = []
        if not any(e.valid for e in evaluations):
            issues.append(
                {
                    "kind": "no_valid_candidate",
                    "message": "No geometrically consistent candidate was found",
                }
            )
        if len(views) < 3:
            issues.append(
                {
                    "kind": "missing_view",
                    "message": "A third orthographic view could eliminate projected alternatives",
                }
            )
        if len([e for e in evaluations if e.valid]) > 1:
            issues.append(
                {
                    "kind": "multiple_candidates",
                    "candidate_ids": [e.candidate_id for e in evaluations if e.valid],
                }
            )
        if any(c.features for c in candidates) or any(
            p.kind == "circle" for v in views for p in v.primitives
        ):
            issues.append(
                {
                    "kind": "feature_topology",
                    "message": "Circle observations do not determine hole depth or solid topology",
                }
            )
        if any(v.alignment.get("origin_inferred") for v in views):
            issues.append(
                {
                    "kind": "view_alignment",
                    "message": "View origins were inferred from bounding minima; confirm shared datums",
                }
            )
        if metadata.get("unsupported_entities"):
            issues.append(
                {
                    "kind": "unsupported_entities",
                    "entities": metadata["unsupported_entities"],
                }
            )
        if any(
            a.get("association_requires_review") for v in views for a in v.annotations
        ):
            issues.append(
                {
                    "kind": "annotation_association",
                    "message": "Nearest-primitive annotation associations are suggestions only",
                }
            )
        unknown = sorted(
            {
                name
                for e in evaluations
                if e.valid
                for name, c in e.checks.items()
                if c.status == "unknown"
            }
        )
        if unknown:
            issues.append({"kind": "unverified_constraints", "checks": unknown})
        return issues

    def find_additional_evidence(self, views: list, metadata: dict) -> list[dict]:
        evidence = [
            {
                "source": "metadata",
                "kind": "extent_dimension",
                "axis": axis,
                "value_mm": value,
            }
            for axis, value in metadata.get("dimensions", {}).items()
        ]
        evidence += [
            {"source": v.id, "kind": "annotation", "annotation": a}
            for v in views
            for a in v.annotations
        ]
        if metadata.get("sheet_thickness") is not None:
            evidence.append(
                {
                    "source": "metadata",
                    "kind": "sheet_thickness",
                    "value_mm": metadata["sheet_thickness"],
                }
            )
        return evidence  # Does not invent measurements or fetch external data.

    def build_resolution_options(self, ambiguities: list[dict]) -> list[dict]:
        actions = {
            "no_valid_candidate": "Correct view labels, alignment, or missing geometry",
            "missing_view": "Provide the missing front, top, or right view",
            "multiple_candidates": "Select a candidate using dimensions or a section view",
            "feature_topology": "Provide hole depth, axis, and through/blind designation",
            "view_alignment": "Specify each view origin using a shared datum",
            "unsupported_entities": "Vectorize or add an adapter for the listed entities",
            "annotation_association": "Confirm the target primitive of each annotation",
            "unverified_constraints": "Build a CAD solid and run physical/manufacturing checks",
        }
        return [
            {
                "ambiguity": issue["kind"],
                "action": actions[issue["kind"]],
                "requires_human_review": True,
            }
            for issue in ambiguities
        ]

    def create_review_request(
        self, ambiguities: list, evidence: list, options: list
    ) -> dict:
        return {
            "status": "needs_review" if ambiguities else "resolved",
            "automatic_approval": False,
            "ambiguities": ambiguities,
            "available_evidence": evidence,
            "resolution_options": options,
        }
