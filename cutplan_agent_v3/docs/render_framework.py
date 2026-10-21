"""Render the inspected architecture, without running models or the pipeline.

Run: ../pbl/bin/python docs/render_framework.py
Only docs/framework.png and docs/framework.svg are generated.
"""
from pathlib import Path
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


OUT = Path(__file__).resolve().parent
font_path = subprocess.check_output(
    ["fc-match", "Noto Sans CJK KR", "-f", "%{file}"], text=True
).strip()
FONT = FontProperties(fname=font_path)
INK = "#172B4D"
MUTED = "#52647B"
COLORS = {
    "code": ("#EEF5FF", "#3875CB"),
    "model": ("#F3EDFF", "#8553BC"),
    "data": ("#E9F8F1", "#258065"),
    "output": ("#FFF5E5", "#C58B25"),
}
fig, ax = plt.subplots(figsize=(18, 18))
fig.patch.set_facecolor("#FFFFFF")
ax.set(xlim=(0, 24), ylim=(0, 24), aspect="equal")
ax.axis("off")
fig.subplots_adjust(left=0.015, right=0.985, bottom=0.015, top=0.985)


def text(x, y, value, *, size=13, weight="normal", color=INK, ha="center"):
    return ax.text(x, y, value, fontproperties=FONT, fontsize=size,
                   weight=weight, color=color, ha=ha, va="center", linespacing=1.65)


def box(x, y, w, h, value, kind="code", *, size=13):
    fill, edge = COLORS[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.025,rounding_size=0.12",
                              facecolor=fill, edgecolor=edge, linewidth=1.3, zorder=2))
    text(x+w/2, y+h/2, value, size=size)


def panel(x, y, w, h, title):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.18",
                              facecolor="#FAFBFD", edgecolor="#CED8E5", linewidth=1.0))
    text(x+0.3, y+h-0.35, title, size=13, weight="bold", ha="left")


def arrow(points, *, kind="code", dashed=False):
    color = COLORS[kind][1]
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, linewidth=1.35,
                linestyle="--" if dashed else "-", zorder=1)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>", mutation_scale=16,
                                linewidth=1.35, color=color,
                                linestyle="--" if dashed else "-", zorder=1))


text(12, 23.35, "CUTPLAN_AGENT_V2 · 현재 구현 프레임워크", size=23, weight="bold")
text(12, 22.72, "원문 OCR + 스키마 제한 Reasoning + 결정론적 3D 와이어프레임 복원", size=13, color=MUTED)

box(0.8, 21.15, 22.4, 1.0,
    "실행·서빙  |  experiments.sh (Local/API 혼합) / experiments_local.sh (Local) → main.py\n"
    "OCR·Reasoning별 GPU / port / model 설정 · 단일 파일 또는 배치 실행", size=13)

box(0.8, 19.45, 5.4, 1.1, "단일 입력\nDXF / 이미지 / PDF / JSON", "data")
box(6.9, 19.45, 9.5, 1.1, "입력 라우팅 · drawing_io.py\ninput_mode / dxf_mode에 따라 분석 경로 선택")
box(17.1, 19.45, 6.1, 1.1, "배치 제어 · batch.py\n폴더의 DXF 탐색 → 도면별 반복")
arrow([(6.2, 20), (6.9, 20)])
arrow([(17.1, 20), (16.4, 20)])
arrow([(11.65, 21.15), (11.65, 20.55)])

panel(0.6, 12.7, 22.8, 6.1, "1. 도면별 2D 분석  |  원시 기하와 모델 판단을 분리")
box(1, 14.85, 7.7, 3.1,
    "DXF 직접 경로 · dxf_reader / dxf_adapter\n"
    "엔티티·TEXT 읽기 / 프레임 제거 / 뷰 후보 분할\n\n"
    "Vision 경로 · vision_reader / vision_adapter\n"
    "DXF·PDF 래스터화 / 타일 / OpenCV 기하 추출", size=12.5)
arrow([(8.8, 19.45), (8.8, 19.05), (8.2, 19.05), (8.2, 17.95)])
box(9.6, 16.55, 5.8, 1.4, "OCR 모델 · vlm.py\nFree OCR. → raw text\nJSON 형식 제한 없음", "model", size=13)
box(16.3, 15.4, 6.7, 2.55,
    "Reasoning 모델 · vlm.py\n"
    "입력: OCR 원문 + 도면 이미지\n"
    "글자·좌표 / 표제란 / 뷰·투상법 / part_class\n"
    "Local: vLLM + XGrammar\nAPI: 제공자의 JSON Schema 기능", "model", size=12)
arrow([(8.7, 17.25), (9.6, 17.25)], kind="model")
arrow([(15.4, 17.25), (16.3, 17.25)], kind="model")
text(15.85, 17.65, "raw", size=10, color=COLORS["model"][1])
arrow([(8.7, 15.25), (15.9, 15.25), (15.9, 15.8), (16.3, 15.8)], kind="model")
text(12.1, 14.94, "도면 이미지 · 뷰 후보 · 치수 등", size=11, color=MUTED)
box(9.6, 13.05, 13.4, 1.25,
    "구조·도면별 검증  |  vlm_output.py + 각 adapter\n"
    "JSON 타입·필수 키·enum / 뷰 ID·중복 / 좌표 범위 검증 · 분류 점수 softmax", size=12.5)
arrow([(19.65, 15.4), (19.65, 14.3)], kind="model")
arrow([(8.7, 15.05), (9.1, 15.05), (9.1, 13.68), (9.6, 13.68)])

box(0.8, 10.7, 22.4, 1.3,
    "공통 데이터 계약 · models.py  |  DrawingDocument\n"
    "metadata(재질·두께·단위·분석 기록) + DrawingView[](뷰별 Primitive2D[]·annotations)", "data", size=14)
arrow([(16.3, 13.05), (16.3, 12.35), (16.3, 12)], kind="data")
arrow([(4.85, 14.85), (4.85, 12)], kind="data")
text(4.85, 13.7, "원시 기하·치수·좌표\n결정론적 처리", size=11, color=COLORS["data"][1])
text(12, 10.23, "JSON 계약 입력 / legacy FRONT·TOP·RIGHT 레이어 입력은 모델 분석을 우회할 수 있음", size=11, color=MUTED)

panel(0.6, 4.05, 22.8, 5.75, "2. 3D 복원·검증·출력  |  pipeline.py는 ①~⑤ / ⑥은 main.py·batch.py에서 별도 호출")
box(1, 7.9, 6.7, 1.15, "① step1 · DrawingInterpreter\n단위 정규화 / 뷰 정렬 / 선·치수 해석", size=12.5)
box(8.65, 7.9, 6.7, 1.15, "② step2 · ViewMatcher\n뷰 간 정점·모서리·특징 대응", size=12.5)
box(16.3, 7.9, 6.7, 1.15, "③ step3 · CandidateGenerator\n3D 와이어프레임 후보 생성 / 판금 제약", size=12.5)
box(16.3, 5.95, 6.7, 1.15, "④ step4 · CandidateEvaluator\n기하·재투영·치수·물리 검사 / 순위 결정", size=12.5)
box(8.65, 5.95, 6.7, 1.15, "⑤ step5 · AmbiguityResolver\n모호성 검출 / 추가 근거 / 검토 요청", size=12.5)
box(1, 5.95, 6.7, 1.15, "⑥ step6 · ReconstructionExporter\n검증된 최상위 후보 저장 / 보고서 출력", size=12.5)
box(8.65, 4.35, 14.35, 0.95,
    "Reasoning 후보 비교 · confirm_candidates() [선택]\n"
    "원본 뷰 ↔ 후보 재투영 비교 / 검증기 순위는 유지, 불일치하면 review", "model", size=11.5)
arrow([(0.8, 11.35), (0.25, 11.35), (0.25, 8.47), (1, 8.47)])
arrow([(7.7, 8.47), (8.65, 8.47)])
arrow([(15.35, 8.47), (16.3, 8.47)])
arrow([(19.65, 7.9), (19.65, 7.1)])
arrow([(16.3, 6.52), (15.35, 6.52)])
arrow([(12, 5.95), (12, 5.3)], kind="model")
arrow([(8.65, 4.82), (8.1, 4.82), (8.1, 6.26), (7.7, 6.26)], kind="model")
arrow([(8.65, 6.8), (7.7, 6.8)], dashed=True)

box(0.8, 2.05, 11.1, 1.4,
    "도면별 산출물\n"
    "analysis/sheet_analysis.json · prediction.json(배치)\n"
    "provenance.json · report.md · STEP* · parameters.json*", "output", size=12)
box(12.7, 2.05, 10.5, 1.4,
    "배치 최종 집계 · batch.py\n"
    "predictions.json · reconstruction.json · accuracy.md\n"
    "정답 label.json은 도면별 예측·복원 종료 후 평가에만 사용", "output", size=11.7)
arrow([(4.35, 5.95), (4.35, 3.45)], kind="output")
arrow([(11.9, 2.75), (12.7, 2.75)], kind="output")

for x, label, kind in ((1, "결정론적 코드", "code"), (6.5, "모델 호출", "model"),
                       (11.6, "데이터 계약", "data"), (17.2, "파일 산출물", "output")):
    fill, edge = COLORS[kind]
    ax.add_patch(FancyBboxPatch((x, 1.16), 0.36, 0.25, boxstyle="round,pad=0.015",
                              facecolor=fill, edgecolor=edge, linewidth=1))
    text(x+0.56, 1.29, label, size=11, ha="left", color=MUTED)
text(12, 0.73, "* 유효 후보가 있을 때만 STEP·parameters 출력. STEP은 솔리드가 아닌 와이어프레임.", size=11, color=MUTED)
text(12, 0.25, "배치 = 도면별 독립 예측·복원 후 집계. 여러 도면의 좌표·형상을 하나로 병합하지 않음.", size=11, color=MUTED)

for extension in ("png", "svg"):
    path = OUT/f"framework.{extension}"
    fig.savefig(path, dpi=160, facecolor="white")
    print(path)
plt.close(fig)
