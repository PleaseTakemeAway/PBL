# 도면 → 전개도 → 커팅플랜: Skill-기반 LLM 에이전트 프레임워크 설계

작성일: 2026-10-01
대상 데이터: `Data/data_v2` (HCE 판금 브라켓, PDF 도면 + 정답 DXF + TruTops TAF), `Data/2023년 cutting plan` (KDM 압력용기 커팅플랜 DWG 31건 + 추출 데이터셋)

---

## 0. 한 줄 요약

**LLM은 "관계 추론"만 하고, 수치 계산·기하 생성·검증은 전부 결정적(deterministic) skill이 한다.**
Phase 1은 Claude API + tool use로 skill 라이브러리와 검증기(verifier)를 만들고 trajectory를 쌓는 단계이고,
Phase 2는 그 verifier를 reward로 써서 skill 선택 정책을 RL로 개선하는 단계다.
"Skill RL"의 실체는 **verifier가 곧 reward 함수**라는 점이다. verifier 없이는 RL도 없다.

---

## 1. 데이터가 말해주는 문제의 실제 구조

### 1-1. 두 데이터셋은 서로 다른 도메인이다

| 항목 | data_v2 (76K3-40022) | 2023년 cutting plan (KD23xxx) |
|---|---|---|
| 발주처/제품 | 현대건설기계 판금 브라켓 (COWL GROUP) | KDM Tech 압력용기·열교환기 |
| 입력 도면 | 조립도 1 + 용접조립도 + 단품도, 스캔 PDF 10p (텍스트 없음) | 이 폴더에 없음 (Drive의 POR PDF에 있음) |
| 전개 방식 | **판금 굽힘 전개** (K-factor, bend allowance, R5) | **압력용기 전개** (shell π(D+t)L, cone sector, head blank, pad 링) |
| 정답 전개도 | 고객 제공 DXF 5개 (`76K3-42020／4T／1EA.dxf` 등) | 커팅플랜 DWG 안의 부품 외곽 (parts.csv 13,388개) |
| 정답 네스팅 | TruTops `.TAF` (배치 좌표·회전) | 커팅플랜 DWG (sheets.csv 936장) |
| 재질 표기 | SS400 (BOM) ↔ St37-40 (TAF) 매핑 필요 | SA516-70 / A516-70 / SA283-C 혼용 |

→ **도메인 지식 prompt는 하나가 아니라 "부품 유형별 skill"로 분리**해야 한다. 판금 브라켓에 압력용기 전개 공식을 주면 안 되고, 그 반대도 마찬가지.

### 1-2. manifest.csv가 이미 보여주는 "판단" 문제

`_flat_by_page/manifest.csv`를 보면 10페이지 중 전개도가 나온 건 6페이지다. 나머지는:
- p01: 최상위 조립도 → 전개 대상 아님
- p02: 용접조립품 → 하위 부품으로 내려가야 함
- p03, p08: 프레스 성형품(SPCC 3t) → 굽힘전개 불가, 성형해석 필요
- p09/p10: 같은 부품이 조립도와 단품도에 중복

즉 전개도 그리기 전에 **"이 페이지를 전개해야 하는가, 어떤 방식으로, BOM의 어느 줄에 해당하는가"**라는 분류·연결 판단이 먼저다. 이게 LLM이 해야 할 일의 본체다.

### 1-3. 도면에서 숫자 뽑기는 OCR만으로 안 된다

p05(76K3-40211)를 보면:
- 정면도·측면도·평면도가 한 장에 있고 치수가 뷰마다 흩어져 있음
- `△84`, `△144` 같은 개정 삼각형 마크 안의 숫자는 치수가 아니라 개정 번호
- `2-Ø13`, `2-R5`는 "2개, 지름 13" 같은 수량 접두 표기
- 용접너트(S241-xxx)는 판재가 아니므로 전개 대상에서 제외
- BOM에 `SS400,6t`라고 적혀 있어도 파일명은 `4T` → 표기 불일치 존재

OCR은 "숫자와 위치"를 주고, **"이 숫자가 어느 형상의 어느 치수인가"**는 VLM+도면 규칙 prompt가 판단해야 한다. 슬라이드 13-14쪽의 결론과 같다.

---

## 2. 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│  Orchestrator (Claude API, tool_runner)                          │
│  - system prompt: 역할 + 작업 절차 + 출력 스키마                  │
│  - 매 step: skill 호출 → 결과 관찰 → 다음 skill 선택              │
│  - 종료 조건: verify_* 통과 or 최대 step                          │
└───────┬──────────────────────────────────────────────────────────┘
        │ tool calls (JSON, strict schema)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  Skill Library  (전부 Python 함수, @beta_tool)                    │
│                                                                  │
│  [Perception]   render_page · ocr_page · detect_views            │
│                 extract_title_block · extract_bom_table          │
│  [Knowledge]    load_domain_prompt(part_type) · lookup_material  │
│                 lookup_std_plate_sizes · lookup_bend_table       │
│  [Geometry]     unfold_sheetmetal · unfold_shell · unfold_cone   │
│                 unfold_head · build_outline(dxf) · add_holes     │
│  [Verify]       verify_closed_loop · verify_vs_bom(weight)       │
│                 verify_dims_consistency · compare_with_gt        │
│  [Nesting]      group_parts_by_mat_thk · nest_rect · nest_poly   │
│                 pick_sheet_size · write_cutting_plan_dxf         │
│  [Output]       write_flat_dxf · write_por_table · save_state    │
└───────┬──────────────────────────────────────────────────────────┘
        │ 모든 호출/결과가 JSONL로 기록됨
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  Trajectory Store + Evaluator                                    │
│  - 정답(GT DXF/TAF/CP dataset)과 비교 → step reward, final reward│
│  - Phase 2에서 이 로그가 RL 학습 데이터가 됨                     │
└──────────────────────────────────────────────────────────────────┘
```

### 2-1. 왜 이 구조인가

1. **LLM이 좌표를 직접 생성하지 않는다.** 전개 외곽선은 `unfold_*` 함수가 파라미터(W, H, 굽힘선 위치, R, t, 구멍 목록)를 받아 결정적으로 만든다. LLM은 그 파라미터를 채우는 역할이다. 이러면 verifier가 파라미터 단위로 오류를 지적할 수 있고 reward가 조밀(dense)해진다.
2. **Skill을 tool로 노출하면 trajectory = (state, action, result) 시퀀스가 자연히 기록된다.** RL에서 필요한 형식이 공짜로 나온다.
3. **도메인 지식 prompt를 skill로 만들면(load_domain_prompt)** "어떤 지식을 언제 불러오는가"도 정책의 일부가 된다. 이것이 사용자가 말한 "전문 지식 Prompt 불러오기 skill"의 정확한 위치다.

### 2-2. 상태(State) 객체

에이전트가 매 step 참조·갱신하는 단일 JSON. 모든 skill은 이 객체를 읽고/쓴다.

```json
{
  "job": "76K3-40022",
  "pages": [
    {"page": 5, "dwg_no": "76K3-40211", "kind": "weld_assy|part|top_assy|formed",
     "unfold_method": "sheetmetal_bend|shell|cone|head|none",
     "bom_ref": {"part_no": "76K3-42110", "material": "SS400", "t": 6, "qty": 1},
     "views": [...], "dims": [...], "holes": [...],
     "flat": {"w": 222, "h": 252, "dxf": "p05_flat.dxf"},
     "verify": {"closed": true, "weight_err": 0.03, "gt_iou": 0.98}}
  ],
  "sheets": [...],          // 네스팅 결과
  "por": [...]              // 구매요구 테이블
}
```

---

## 3. Skill 명세 (Phase 1에서 구현할 것)

### 3-1. Perception skills

| skill | 입력 | 출력 | 구현 |
|---|---|---|---|
| `render_page(pdf, page, dpi)` | PDF | PNG 경로 | PyMuPDF (이미 설치됨) |
| `ocr_page(png)` | PNG | `[{text, bbox, conf}]` | 1차: Claude vision으로 구조화 추출. 2차: PaddleOCR/Tesseract 병행 후 앙상블 |
| `extract_title_block(png)` | PNG 우하단 crop | dwg_no, part_name, material, scale, sheet | Claude vision + structured output (Pydantic) |
| `extract_bom_table(png)` | PNG BOM 영역 crop | `[{item, part_no, name, material, t, qty}]` | Claude vision + structured output |
| `detect_views(png)` | PNG | 뷰 bbox 목록 (정면/측면/평면/상세) | OpenCV 연결성분 + Claude 판정 |
| `classify_page(state, page)` | 타이틀블록+BOM | kind, unfold_method, bom_ref | **LLM 판단** (핵심 관계 추론) |

핵심: `ocr_page`의 출력을 그대로 믿지 말고, `dims`를 만들 때 반드시 **어느 뷰의 어느 edge에 붙은 치수인지** bbox 관계로 연결한다. 개정 삼각형(△) 안 숫자는 `kind: revision`으로 태깅해 치수에서 제외.

### 3-2. Knowledge skills (도메인 prompt 로더)

`load_domain_prompt(topic)` 하나로 통일하고 topic별 markdown을 `knowledge/` 폴더에 둔다.

| topic | 내용 |
|---|---|
| `drawing_conventions_kr` | `2-Ø13`, `R5`, `△n`, `T.L`, `C.L`, 1/3 scale, 3각법, 은선 규칙, 용접기호 |
| `sheetmetal_unfold` | K-factor(0.33~0.5), bend allowance = (π/180)·θ·(R + K·t), 최소 R = t 규칙, 굽힘선 위치 |
| `pressure_vessel_unfold` | shell 전개 = π(D_i + t)·L, cone sector 각도, 2:1 ellip. head blank dia ≈ 1.2·D + 2·h_sf 등 |
| `material_mapping` | SS400↔St37↔A283-C, SA516-70 vs A516-70(ASME/ASTM 동일), SUS304↔SA240-304 |
| `nesting_rules` | 부품 간격(2.5~10mm, t별), 판 가장자리 여유, 회전 허용(0/90/180/270), 잔재 활용 |
| `std_plate_sizes` | sheets.csv 상위 규격 (2438×6000, 3048×8250, 1524×7000 …) + 두께별 재고 규격 |

이 markdown들은 처음엔 현업 지식을 정리해 손으로 쓰고, Phase 2에서 **"이 prompt를 불러왔을 때 reward가 올라갔는가"**로 유효성을 평가한다.

### 3-3. Geometry skills (전개도 생성)

전부 `ezdxf` 기반 결정적 함수. LLM은 파라미터만 넘긴다.

- `unfold_sheetmetal(faces, bends, t, k_factor, holes)` → 전개 외곽 polyline + 구멍 원 + 굽힘선(별도 layer)
- `unfold_shell(D, L, t, seam_count)` → 사각형 W=π(D+t)/seam, H=L
- `unfold_cone(D_big, D_small, H, t)` → sector 폴리라인
- `unfold_head_blank(D, t, type)` → 원판 지름
- `unfold_pad(OD, ID, t)` → 링
- `write_flat_dxf(outline, holes, info, path)` → 기존 `_flat_by_page` 형식(layer: BLANK/HOLE/INFO) 유지

### 3-4. Verify skills (= reward 함수의 원형)

| skill | 검사 | 반환 |
|---|---|---|
| `verify_closed_loop(dxf)` | 외곽선이 닫혔는가, 자기교차 없는가 | bool + 오류 위치 |
| `verify_vs_bom(state, page)` | 전개 면적×t×밀도 ≈ BOM WEIGHT (p05: 1.05kg)? | 상대오차 |
| `verify_dims_consistency(page)` | 전체 치수 = 부분 치수 합? (170 = 60 + 110?) | 불일치 목록 |
| `verify_holes(page)` | 구멍 개수·지름이 `2-Ø13` 표기와 일치? | bool |
| `compare_with_gt(dxf, gt_dxf)` | 외곽 IoU, W/H 오차, 구멍 수 일치 | 점수 (개발용, 운영 시 미사용) |

BOM weight 검사는 정답 DXF 없이도 쓸 수 있는 **self-verification**이라 특히 중요하다. p05 BOM에 PLATE 1.05kg이 있으니 SS400 밀도 7.85로 역산하면 면적을 검증할 수 있다.

### 3-5. Nesting skills

- `group_parts(state)` → (material, t)별 부품 묶음. 재질 매핑 skill 사용.
- `pick_sheet_size(group, std_sizes)` → 후보 판 규격 (LLM이 std_plate_sizes 참고해 선택)
- `nest_rect(parts, sheet, gap, rotations)` → maxrects/skyline 알고리즘 (rectpack 라이브러리)
- `nest_poly(parts, sheet)` → 2차. 원판·링 같은 비사각형 (shapely + no-fit-polygon 또는 간단 grid 탐색)
- `write_cutting_plan_dxf(sheets)` → 기존 CP 형식(판 외곽 + 부품 + 라벨 텍스트 `SA283-C 8t x 3048 x 7650 - 1 SH'T`)
- `utilization(sheets)` → 활용률 = Σ부품면적 / 판면적

LLM이 하는 결정: 판 규격 선택, 회전 허용 여부, 어느 부품을 어느 판에 넣을지 대분류. 좌표 배치는 알고리즘.

---

## 4. 코드 플로우

### 4-1. 디렉토리

```
cutplan_agent/
  agent/
    orchestrator.py      # tool_runner 루프, state 관리, trajectory 로깅
    prompts/system.md    # 역할·절차·출력 형식
  skills/
    perception.py        # render_page, ocr_page, extract_*, classify_page
    knowledge.py         # load_domain_prompt, lookup_*
    geometry.py          # unfold_*, write_flat_dxf
    verify.py            # verify_*, compare_with_gt
    nesting.py           # group_parts, nest_rect, write_cutting_plan_dxf
  knowledge/*.md         # 도메인 prompt
  eval/
    gt_loader.py         # data_v2 DXF/TAF, 2023 CP dataset 로더
    metrics.py           # reward 계산
    run_eval.py          # 배치 실행 + scorecard
  runs/                  # trajectory JSONL, 생성 DXF
```

### 4-2. Orchestrator 골격 (Python, anthropic 1.6.0 설치 확인됨)

```python
# agent/orchestrator.py
import json, time, anthropic
from anthropic import beta_tool
from skills import perception, knowledge, geometry, verify, nesting

client = anthropic.Anthropic()
STATE = {"job": None, "pages": [], "sheets": [], "por": []}
TRAJ = []  # trajectory 로그

def logged(fn):
    """모든 skill 호출을 (name, args, result, t)로 기록 → RL 데이터"""
    def wrapper(**kw):
        t0 = time.time()
        out = fn(**kw)
        TRAJ.append({"skill": fn.__name__, "args": kw, "result": out, "dt": time.time() - t0})
        return json.dumps(out, ensure_ascii=False)
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    wrapper.__annotations__ = fn.__annotations__
    return wrapper

@beta_tool
@logged
def render_page(page: int, dpi: int = 150) -> dict:
    """도면 PDF의 한 페이지를 PNG로 렌더링한다. Args: page: 1-based 페이지 번호. dpi: 해상도."""
    return perception.render_page(STATE["job"], page, dpi)

@beta_tool
@logged
def load_domain_prompt(topic: str) -> dict:
    """도메인 지식 문서를 불러온다. Args: topic: drawing_conventions_kr | sheetmetal_unfold |
    pressure_vessel_unfold | material_mapping | nesting_rules | std_plate_sizes"""
    return {"topic": topic, "text": knowledge.load(topic)}

@beta_tool
@logged
def unfold_sheetmetal(page: int, faces: list, bends: list, t: float,
                      k_factor: float = 0.44, holes: list = ()) -> dict:
    """판금 굽힘 전개도를 생성해 DXF로 저장한다. Args: faces: [{w,h}] 평면 목록.
    bends: [{between:[i,j], angle, r}] 굽힘 목록. t: 두께. k_factor: K값. holes: [{x,y,d}]"""
    return geometry.unfold_sheetmetal(STATE, page, faces, bends, t, k_factor, list(holes))

@beta_tool
@logged
def verify_vs_bom(page: int, density: float = 7.85e-6) -> dict:
    """전개 면적×두께×밀도를 BOM 중량과 비교한다."""
    return verify.weight_check(STATE, page, density)

# ... 나머지 skill도 같은 패턴

TOOLS = [render_page, load_domain_prompt, unfold_sheetmetal, verify_vs_bom, ...]

def run(job: str, pdf: str, max_steps: int = 60):
    STATE.update(job=job, pdf=pdf)
    runner = client.beta.messages.tool_runner(
        model="claude-opus-5-5",
        max_tokens=16000,
        output_config={"effort": "high"},
        system=open("agent/prompts/system.md", encoding="utf8").read(),
        tools=TOOLS,
        messages=[{"role": "user", "content":
            f"도면 {pdf}를 처리하라. 절차: 페이지 분류 → 전개 대상 선정 → 치수 추출 → 전개도 생성 → 검증 → 네스팅 → POR."}],
    )
    for i, msg in enumerate(runner):
        if i >= max_steps:
            break
    json.dump(TRAJ, open(f"runs/{job}_traj.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    return STATE
```

### 4-3. 시스템 프롬프트 골격 (`prompts/system.md`)

```
너는 판금/압력용기 생산기술자다. 입력 도면(PDF)에서 판재 부품을 찾아 전개도를 만들고 커팅플랜을 작성한다.

절차:
1. 모든 페이지의 타이틀블록과 BOM을 읽어 페이지 종류를 분류한다 (top_assy / weld_assy / part / formed).
2. 전개 대상은 "판재(PLATE)이며 굽힘 또는 롤링으로 제작 가능한 부품"이다. 프레스 성형품, 너트/볼트, 구매품은 제외한다.
3. 부품 유형에 맞는 도메인 지식을 load_domain_prompt로 먼저 불러온 뒤 치수를 해석한다.
4. 좌표를 직접 계산하지 말고 unfold_* skill에 파라미터를 넘긴다.
5. 전개 후 반드시 verify_closed_loop, verify_vs_bom, verify_holes를 호출하고, 실패하면 파라미터를 수정해 재시도한다.
6. 재질·두께별로 그룹화하고 표준 판 규격에서 선택해 nest_rect를 호출한다.
7. 최종적으로 write_por_table로 구매요구 테이블을 만든다.

판단이 불확실한 값은 state에 confidence를 기록한다. 추측으로 채우지 않는다.
```

### 4-4. 실행 흐름 (한 job의 이상적인 trajectory)

```
render_page(1..10) ─┐
extract_title_block  ├─ 10회
extract_bom_table(1) ─┘
classify_page(1..10)          → p04,05,06,07,09,10 = part / p03,08 = formed / p01 = top / p02 = weld
load_domain_prompt(drawing_conventions_kr)
load_domain_prompt(sheetmetal_unfold)
for p in [4,5,6,7,10]:
    detect_views(p) → ocr_page(p) → (LLM이 dims를 뷰/edge에 연결)
    unfold_sheetmetal(p, faces, bends, t, holes)
    verify_closed_loop(p); verify_vs_bom(p); verify_holes(p)
    (실패 시 파라미터 수정 후 재호출, 최대 3회)
load_domain_prompt(material_mapping); load_domain_prompt(std_plate_sizes)
group_parts() → {(SS400,4t): [42020,40220_1,40231A,42510], (SS400,6t): [42110]}
pick_sheet_size(...) → 2438×1219
nest_rect(...) → sheets
write_cutting_plan_dxf(); write_por_table()
```

---

## 5. 실험 설계

### 5-1. 실험 A: data_v2 (end-to-end, 정답 완비)

| 단계 | 입력 | 정답 | 지표 |
|---|---|---|---|
| A1 페이지 분류 | PDF 10p | manifest.csv의 status/reason | 정확도 (10/10) |
| A2 BOM 추출 | p01 BOM 이미지 | bom.csv (22행) | 행 단위 F1 |
| A3 전개도 | 페이지별 | 고객 DXF 5개 (`76K3-4xxxx／4T／1EA.dxf`) | W/H 오차(mm), 외곽 IoU, 구멍 수·지름 일치 |
| A4 자기검증 | 생성 DXF | BOM WEIGHT | 중량 상대오차 < 5% |
| A5 네스팅 | 전개 5종 × 수량 | TAF (2438×1219, St37-40 4t, 21개 배치) | 판 수 일치, 활용률 차이, 겹침 0 |

주의: 정답 TAF는 4t만 있다 (42110은 BOM에 6t인데 4t 판에 같이 배치됨 = 현장에서 4t로 통일). 이 "BOM 두께 ≠ 실제 절단 두께" 케이스는 그대로 두고 에이전트가 파일명 `4T`를 근거로 판단하는지 본다.

### 5-2. 실험 B: 2023 커팅플랜 (네스팅 skill + 압력용기 전개 검증)

이 폴더에는 KD23xxx의 **원본 설계도면이 없다**. 그래서 B는 두 층으로 나눈다.

**B1 (지금 가능): 부품 리스트 → 커팅플랜.**
입력 = part_tags.csv(dwg_no, part_name, material, t, size, qty) + sheets.csv의 재질/두께.
정답 = sheets.csv(판 규격·수량) + parts.csv(배치).
지표 = 판 수, 총 판 면적, 활용률을 사람 계획과 비교. `quality=ok` 판(592장)만 사용.
여기서 `size`가 `⌀1296`, `⌀168x⌀300`, `2800x2949`처럼 형식이 제각각이라 **size 문자열 → 전개 형상 파싱 자체가 skill**(`parse_tag_size`)이고 LLM 관계 추론 대상이다.

**B2 (Drive에서 POR PDF 확보 후): 도면 → 부품 리스트.**
슬라이드 7-8쪽 문제(T.L, shell 두께가 GA 데이터시트에 있음)가 여기서 나온다. 정답은 part_tags.csv의 size/qty.

**중요한 발견**: `scorecard.csv`를 보면 31건 중 ok_rate가 낮은 도면이 많고(`KD23004` 40%, `chain_path` 판 81장). GT 자체가 노이즈가 있으니 **B1 평가는 scorecard grade=성공인 도면(KD23002, 23008, 23015, 23022 …)부터** 시작한다.

### 5-3. 실험 진행 순서 (권장)

1. **Week 1**: Perception + Knowledge skill 구현, 실험 A1·A2 (LLM 단독 vs. skill 사용 비교)
2. **Week 2**: Geometry + Verify skill, 실험 A3·A4. 여기서 `_flat_by_page` 결과와 재현 비교
3. **Week 3**: Nesting skill, 실험 A5 + B1
4. **Week 4~**: trajectory 100건 이상 축적 → Phase 2

각 실험은 **ablation**을 반드시 포함: (a) skill 없이 VLM 직접 답변, (b) OCR skill만, (c) OCR + domain prompt, (d) 전체. 이게 "skill이 정말 도움이 되는가"를 보여주는 논문/보고서의 핵심 표가 된다.

---

## 6. Phase 2: Skill RL

### 6-1. 무엇을 정책(policy)으로 볼 것인가

trajectory에서 정책의 action은 세 가지다:
1. **skill 선택** (다음에 어떤 skill을 부를지, 어떤 domain prompt를 로드할지)
2. **skill 파라미터** (faces/bends/holes 값, 판 규격 선택)
3. **재시도 판단** (verify 실패 후 무엇을 고칠지)

### 6-2. Reward

```
R_final = 0.4·IoU(전개 외곽) + 0.2·1[구멍 일치] + 0.2·(1 - |ΔW|+|ΔH| / (W+H))
        + 0.2·(활용률 / 사람 활용률)        # 네스팅 포함 시
R_step  = +0.05 verify 통과 / -0.05 같은 skill 3회 연속 실패 / -0.01 per step (효율)
R_self  = verify_vs_bom 통과 (정답 없이도 계산 가능 → 운영 중에도 reward 가능)
```

### 6-3. 학습 대상 3가지 선택지 (현실적 순서)

| 방식 | 학습 대상 | 장점 | 단점 |
|---|---|---|---|
| **(1) Verifier-guided best-of-N + prompt/skill 진화** | system prompt, knowledge/*.md, skill description | API 모델 그대로, ZDR 유지, 지금 바로 가능 | 파라미터 학습 아님 |
| **(2) 오픈 VLM에 trajectory SFT → GRPO** (Qwen2.5-VL 7B 등) | 모델 가중치 | 진짜 RL, 온프레미스 배포 | GPU·데이터 100건+ 필요 |
| (3) API 모델 + 강화학습된 소형 "skill selector" | 어떤 skill/prompt를 붙일지 정하는 분류기 | 가볍고 해석 가능 | 이득이 제한적 |

권장: **(1)로 시작해서 trajectory와 verifier가 안정되면 (2)로.** (1)에서 "이 domain prompt를 넣었더니 IoU가 0.7→0.95"라는 결과 자체가 skill 유효성 증거이고, (2)의 reward 함수는 (1)의 verifier를 그대로 쓴다.

---

## 7. 지금 결정해야 하는 것

1. **모델·데이터 반출 정책**: 슬라이드 12쪽에 ZDR 요구가 있다. Claude Fable 5.1은 ZDR 불가(30일 보존 필요)이고, Opus 5.5의 ZDR 가능 여부는 조직 설정에서 확인해야 한다. 안 되면 Bedrock/Vertex 경유 또는 Phase 2를 앞당겨 오픈 모델로.
2. **OCR 엔진**: 1차는 Claude vision 구조화 추출로 가고, 정확도가 부족한 치수(작은 글씨, 겹침)에서만 PaddleOCR 병행. 처음부터 두 개 다 만들 필요 없음.
3. **KD23xxx 원본 도면 확보**: 실험 B2를 위해 Drive의 POR PDF 중 KD23002, 23008, 23015, 23022 (scorecard 성공 건) 4개만 먼저 받으면 된다.
4. **판금 K-factor 기준값**: HCE 도면 NOTE에 "bending R min. as possible"만 있으므로 K=0.44(연강 기본)로 시작하고, 정답 DXF 5개로 역산해서 실제 값을 확정한다.
