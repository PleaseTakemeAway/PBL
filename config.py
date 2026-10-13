# -*- coding: utf-8 -*-
"""경로·모델·현장 기본값. KDM 배치툴(발표자료 08 슬라이드)의 설정값을 기본으로 둔다."""
from pathlib import Path

ROOT = Path(r"D:\노바투스2026")
DATASET = ROOT / "Data" / "dataset"
TOOLKIT = ROOT / "tools" / "dwg2png"           # 이전 세션 툴킷 (libredwg, unfold 엔진, cp_extract)
DWG2DXF = TOOLKIT / "libredwg" / "dwg2dxf.exe"
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
RUNS_DIR = ROOT / "runs"

# ---- Claude API ----
MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
VLM_MAX_PX = 2576          # 이 이상은 서버가 축소하므로 dpi 를 역산해 맞춘다

# ---- 현장 규칙 (KDM 배치툴 기본값) ----
DENSITY_STEEL = 7.85e-6    # kg/mm^3  (POR 중량 = t x W x L x 밀도, KD25038: 10x2438x9150 -> 1,751kg 확인)
KERF_MARGIN = {"gas": 20.0, "plasma": 10.0, "laser": 5.0}   # 조각 간 커팅여유 (mm)
DEFAULT_CUT = "gas"
TRANSPORT_MAX = (12000.0, 3050.0)   # 운반 상한 (길이, 폭) mm
SNAP = 100.0                        # 맞춤 판재 길이 반올림 단위
EDGE_MARGIN = 10.0                  # 판 가장자리 여유

# 판재 규격 후보 (dataset sheets.csv 상위 규격 + 밀 표준폭). 폭 x 길이
STD_WIDTHS = [1219.0, 1524.0, 1829.0, 2000.0, 2134.0, 2438.0, 2500.0, 2670.0, 3048.0]
STD_LENGTHS = [2438.0, 3048.0, 4000.0, 5000.0, 6000.0, 6096.0, 7000.0, 8000.0, 9000.0, 10000.0, 12000.0]

# 전개 판정 (툴킷 전개구분표 + KDM 발표자료)
UNFOLD_CLASS = {
    "cylinder":     ["SHELL", "CHANNEL", "L/SHELL", "LARGE SHELL", "SMALL SHELL", "NECK", "NOZZLE NECK", "DAVIT"],
    "cone_frustum": ["CONE", "REDUCER", "BTM.CONE", "BTM CONE"],
    "head":         ["HEAD", "ELLIP", "DISH"],
    "pad_ring":     ["REINF. PAD", "REINF PAD", "RE-PAD", "REPAD", "PAD"],
    "flat":         ["PLATE", "BAFFLE", "RIB", "LUG", "STRIP", "SCREEN", "EQUATOR", "BRACKET", "CLIP",
                     "PARTITION", "TEMPLATE", "BASE", "WEB", "COVER", "SUPPORT PLATE", "TUBESHEET"],
}
