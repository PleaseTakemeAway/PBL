"""Connect every requested method in the six-stage reconstruction pipeline."""
from models import DrawingDocument, ReconstructionResult
from step1 import DrawingInterpreter
from step2 import ViewMatcher
from step3 import CandidateGenerator
from step4 import CandidateEvaluator
from step5 import AmbiguityResolver


class ReconstructionPipeline:
    def __init__(self, tolerance: float = 0.01, max_candidates: int = 10):
        self.interpreter = DrawingInterpreter()
        self.matcher = ViewMatcher(tolerance)
        self.generator = CandidateGenerator(max_candidates)
        self.evaluator = CandidateEvaluator(tolerance)
        self.resolver = AmbiguityResolver()

    def run(self, drawing: DrawingDocument) -> ReconstructionResult:
        metadata = self.interpreter.extract_metadata(drawing)
        views = self.interpreter.segment_views(drawing)
        views = self.interpreter.identify_views(views)
        if len(views) < 2:
            raise ValueError("3D reconstruction requires at least two distinct orthographic views")
        views = self.interpreter.align_views(views, metadata)
        views = self.interpreter.classify_lines(views)
        primitives = self.interpreter.extract_primitives(views)
        metadata["primitive_counts"] = {view_id: {kind: len(items) for kind, items in group.items()} for view_id, group in primitives.items()}
        views = self.interpreter.associate_annotations(views)
        vertex_matches = self.matcher.match_vertices(views)
        edge_matches = self.matcher.match_edges([m["position"] for m in vertex_matches], views)
        features = self.matcher.match_features(views)
        candidates = self.generator.generate_wireframe_candidates(vertex_matches, edge_matches)
        candidates += self.generator.generate_feature_candidates(candidates, features)
        candidates = self.generator.apply_sheet_metal_constraints(candidates, metadata)
        candidates, evaluations = self.evaluator.rank_candidates(candidates, views, metadata)
        ambiguities = self.resolver.detect_ambiguities(candidates, evaluations, views, metadata)
        evidence = self.resolver.find_additional_evidence(views, metadata)
        options = self.resolver.build_resolution_options(ambiguities)
        review = self.resolver.create_review_request(ambiguities, evidence, options)
        return ReconstructionResult(metadata, views, candidates, evaluations, review)
