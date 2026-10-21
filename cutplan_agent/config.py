# -*- coding: utf-8 -*-
"""경로·모델·현장 기본값. KDM 배치툴(발표자료 08 슬라이드)의 설정값을 기본으로 둔다."""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")             # API 키·머신별 값 (git 제외). 이미 설정된 환경변수가 우선

# 데이터·툴킷·결과가 놓이는 작업 루트. CUTPLAN_ROOT 로 덮어쓸 수 있다.
ROOT = Path(os.environ.get("CUTPLAN_ROOT") or PROJECT_ROOT)
DATA_DIR = ROOT / "Data"                       # 원본·정제 데이터 (git 제외). scripts/ 가 만들고 읽는다
DATASET = DATA_DIR / "dataset"
DRIVE_STAGING = DATA_DIR / "drive" / "8. Data"  # Google Drive '8. Data' 압축을 푸는 위치 (ingest_drive_inputs.py 입력)
TEST_DATA = ROOT / "test_data"
TOOLKIT = ROOT / "tools" / "dwg2png"           # 이전 세션 툴킷. 코드는 Windows 용 libredwg 동봉본만 쓴다
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
SKILLS_DIR = PROJECT_ROOT / "skills"           # v3 와 같이 쓰는 도메인 문서·프롬프트
RUNS_DIR = ROOT / "runs"


def _find_dwg2dxf() -> Path:
    """툴킷 동봉 libredwg 를 우선 쓰고, 없으면 PATH 의 dwg2dxf (Linux: libredwg-tools)."""
    bundled = TOOLKIT / "libredwg" / ("dwg2dxf.exe" if os.name == "nt" else "dwg2dxf")
    if bundled.exists():
        return bundled
    found = shutil.which("dwg2dxf")
    return Path(found) if found else bundled


DWG2DXF = _find_dwg2dxf()

# 한글 글리프 폰트 (OS 별로 설치된 것 중 앞에서부터 사용)
HANGUL_FONT_FILE = "malgun.ttf" if os.name == "nt" else "NotoSansCJK-Regular.ttc"
HANGUL_FONT_FAMILIES = ["Malgun Gothic", "Noto Sans CJK KR", "NanumGothic", "DejaVu Sans"]

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
