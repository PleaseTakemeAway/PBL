"""Stage 6: export STEP wireframe, parameters, traceability, and review report."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile
from models import ReconstructionCandidate, ReconstructionResult
from step4 import CandidateEvaluator


def _write(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _step_string(value: str) -> str:
    if any(ord(char) > 126 for char in value):
        return "'\\X2\\" + value.encode("utf-16-be").hex().upper() + "\\X0\\'"
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


class ReconstructionExporter:
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = tolerance

    def export_step(self, candidate: ReconstructionCandidate, path: str | Path) -> Path:
        if CandidateEvaluator(self.tolerance).validate_geometry(candidate).status != "pass":
            raise ValueError("Cannot export invalid geometry")
        if candidate.parameters.get("units", "mm") != "mm":
            raise ValueError("STEP exporter expects millimeter coordinates")
        entities = []
        def entity(value):
            entities.append(f"#{len(entities)+1}={value};")
            return f"#{len(entities)}"
        app = entity("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
        entity(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{app})")
        product_context = entity(f"PRODUCT_CONTEXT('',{app},'mechanical')")
        product = entity(f"PRODUCT({_step_string(candidate.id)},{_step_string(candidate.id)},'',({product_context}))")
        formation = entity(f"PRODUCT_DEFINITION_FORMATION('','',{product})")
        context = entity(f"PRODUCT_DEFINITION_CONTEXT('part definition',{app},'design')")
        definition = entity(f"PRODUCT_DEFINITION('design','',{formation},{context})")
        shape = entity(f"PRODUCT_DEFINITION_SHAPE('','',{definition})")
        length = entity("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
        angle = entity("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
        solid_angle = entity("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
        uncertainty = entity(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE({self.tolerance:.12E}),{length},'distance_accuracy_value','drawing tolerance')")
        geometry_context = entity(f"(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({uncertainty})) GLOBAL_UNIT_ASSIGNED_CONTEXT(({length},{angle},{solid_angle})) REPRESENTATION_CONTEXT('',''))")
        points = [entity("CARTESIAN_POINT('',(" + ",".join(f"{value:.12E}" for value in p) + "))") for p in candidate.vertices]
        curves = [entity(f"POLYLINE('',({points[i]},{points[j]}))") for i, j in candidate.edges]
        curve_set = entity("GEOMETRIC_CURVE_SET('',(" + ",".join(curves) + "))")
        representation = entity(f"GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION('',({curve_set}),{geometry_context})")
        entity(f"SHAPE_DEFINITION_REPRESENTATION({shape},{representation})")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('Wireframe reconstruction; no solid or confirmed holes'),'2;1');\n"
        header += f"FILE_NAME({_step_string(Path(path).name)},'{timestamp}',(''),(''),'cutplan_agent_v2','cutplan_agent_v2','');\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n"
        return _write(path, header+"\n".join(entities)+"\nENDSEC;\nEND-ISO-10303-21;\n")

    def export_parameters(self, candidate: ReconstructionCandidate, path: str | Path) -> Path:
        value = {"candidate_id": candidate.id, "units": "mm", "extents": dict(zip("xyz", candidate.extents)), "features": candidate.features, "parameters": candidate.parameters, "score": candidate.score}
        return _write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")

    def export_provenance(self, result: ReconstructionResult, path: str | Path) -> Path:
        return _write(path, json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False)+"\n")

    def export_report(self, result: ReconstructionResult, path: str | Path) -> Path:
        lines = ["# 도면 3D 복원 보고서", "", f"- 입력: {result.metadata.get('source')}", "- 좌표 단위: mm", "- 출력 형상: 와이어프레임 (면·솔리드·홀은 확정하지 않음)", f"- 검토 상태: {result.review_request['status']}", "", "## 후보 검증", ""]
        for evaluation in result.evaluations:
            lines += [f"### {evaluation.candidate_id}", "", f"점수: {evaluation.score:.3f}; 기하 후보 유효 여부: {evaluation.valid}", ""]
            for name, check in evaluation.checks.items():
                lines.append(f"- {name}: {check.status}" + (" - " + "; ".join(check.messages) if check.messages else ""))
            lines.append("")
        lines += ["## 필요한 추가 검토", ""]
        lines += [f"- {option['ambiguity']}: {option['action']}" for option in result.review_request["resolution_options"]]
        lines += ["", "점수는 수행 가능한 검사의 적합도이며, unknown 검사를 통과했다는 의미가 아님.", ""]
        return _write(path, "\n".join(lines))
