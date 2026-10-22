"""Stage 3: build explicit wireframe and unresolved feature hypotheses."""

from copy import deepcopy

from cutplan_agent.reconstruct.models import ReconstructionCandidate


class CandidateGenerator:
    def __init__(self, max_candidates: int = 10):
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        self.max_candidates = max_candidates

    def generate_wireframe_candidates(
        self, vertex_matches: list[dict], edge_matches: list[tuple[int, int]]
    ) -> list[ReconstructionCandidate]:
        if not vertex_matches or not edge_matches:
            return []
        candidate = ReconstructionCandidate(
            "wireframe-1",
            [m["position"] for m in vertex_matches],
            list(edge_matches),
            parameters={"geometry_type": "wireframe", "units": "mm"},
            provenance=[
                {"stage": "view_matching", "vertex_matches": deepcopy(vertex_matches)}
            ],
        )
        return [candidate]

    def generate_feature_candidates(
        self, candidates: list[ReconstructionCandidate], features: list[dict]
    ) -> list[ReconstructionCandidate]:
        if not features:
            return []
        results = []
        for base in candidates[: self.max_candidates]:
            candidate = deepcopy(base)
            candidate.id += "-features"
            candidate.features = deepcopy(features)
            candidate.provenance.append(
                {
                    "stage": "feature_generation",
                    "status": "hypothesis; no hole/solid geometry is added",
                }
            )
            results.append(candidate)
        return results

    def apply_sheet_metal_constraints(
        self, candidates: list[ReconstructionCandidate], metadata: dict
    ) -> list[ReconstructionCandidate]:
        for candidate in candidates:
            candidate.parameters.update(
                sheet_thickness=metadata.get("sheet_thickness"),
                manufacturing=deepcopy(metadata.get("manufacturing", {})),
            )
            candidate.provenance.append(
                {
                    "stage": "sheet_metal_constraints",
                    "sheet_thickness": metadata.get("sheet_thickness"),
                    "source": "drawing metadata",
                    "requires_solid_validation": True,
                }
            )
        return candidates[: self.max_candidates]
