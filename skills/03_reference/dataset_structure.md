# dataset/ 구조

워크오더 단위로 **입력 도면 → 전개도 → 커팅플랜** 을 매칭한 데이터셋.

```
KDM/<year>/<workorder>/     KDM Tech 압력용기 (67개 커팅플랜, 59 워크오더 + 도면만 있는 워크오더)
  input/         Google Drive '8. Data/기술부' 에서 가져온 설계 자료. scripts/ingest_drive_inputs.py 로 채움
    drawings/      GA, Detail of body/tube bundle/saddle/nozzle 등 설계도면 (dwg + pdf). 협력사 하위폴더(동은/신우) 유지
    calculation/   강도계산서 PDF (shell 두께, 압력/온도 등 데이터시트 값의 출처)
    por/           구매부/POR 의 구매요구서 PDF (#23002PR-01 ...). 현재 소수만 확보
    index.csv      원본 경로·분류·복사 여부. documents(절차서) 는 용량 때문에 복사 안 하고 여기만 기록
  cutting_plan/  *_CP.dwg (원본) + .png/.dxf (변환본)  = 최종 출력 정답
  unfold/        커팅플랜에서 잘라낸 부품별 외곽 DXF     = 전개도 정답 (scripts/extract_part_unfolds.py)
  gt/            sheets.csv(판재), parts.csv(부품 배치), part_tags.csv(부품표), scorecard.json(추출 품질)
HCE/76K3-40022/             현대건설기계 판금 브라켓 (정답 완비 샘플)
  input/         스캔 PDF 10p + BOM xlsx + 페이지 트레이스 DXF
  unfold/        고객 제공 정답 전개 DXF 5개 (`76K3-xxxxx／4T／1EA.dxf`), generated_flat*/ 는 이전 세션 생성본
  cutting_plan/  TruTops TAF (네스팅 정답) + nesting_dataset.json
  gt/            sheets.csv, parts.csv, bom.csv
manifest.csv                워크오더별 파일 수·품질 요약. input_drawings=0 이면 Drive 도면 미확보, cp_files=0 이면 커팅플랜 없음(grade=도면만)
_third_party_index.csv      구매부/타사 POR 자료 (타사 프로젝트의 05. 도면 / 07. PR, MPS). 복사하지 않고 목록만
```

Drive 원본은 `D:/노바투스2026/Dataset/8. Data/` (zip 파트 007·008 해제분). 나머지 파트를 풀면 ingest 스크립트를 다시 실행.

## Drive 원본(8. Data) 폴더별 의미와 파이프라인에서의 역할 (2026-10-01 샘플 확인)
| 폴더 | 내용 | 역할 |
|---|---|---|
| 기술부/.../<WO>/DWG | GA(설계조건표·재질표·노즐표·전체치수), Detail of body(쉘 코스·헤드·용접선·BOM), tube bundle(튜브시트·배플), saddle, nozzle(보강패드), test ring, name plate. dwg+pdf | **입력**. 판재 부품 목록과 전개 치수의 출처 |
| 기술부/.../<WO>/CAL | 강도계산서(설계압력·온도·부식여유, 부품별 소요두께, 중량 요약) | 검증. BOM 두께·중량 cross-check, GA에 없는 설계값 보충 |
| 기술부/.../<WO>/DOC | 수압시험·검사·NDE·도장·포장 절차서, WPS/PQR | 미사용 (복사 안 함) |
| 구매부/POR | 구매요구서. `*PR-nn PLATE.pdf` 는 재질·t×W×L·SH'T 수량·중량 표 = 커팅플랜 결과물 | **최종 출력 정답** (STEP 4 구매요구서) |
| 구매부/견적서(발췌본) | 워크오더·자재군별(PLATE, FORGING, TUBE…) 업체 견적 | 참고. PLATE 견적은 POR 판재 목록의 2차 검증 |
| 구매부/타사 POR 자료 | 신화·일진·타사 테스트자료: 타사의 PR, MPS, POS, NESTING.dwg, DEVELOPMENT DWG(전개도) | 추가 학습/평가 데이터 (도면 표기 방식 다양성). `_third_party_index.csv` |
| 영업부 | 입찰(ITB/RFQ)·현설자료·고객 GAD·질의응답. 대부분 배관/건설 공사 | 미사용. 장치 제작건의 고객 GAD 만 STEP 1 입력 후보 |

## 사용 우선순위
- `grade` = 성공 이고 `n_sheets_ok` 가 큰 워크오더부터 (정답 노이즈 적음)
- `quality = chain_path` 판재는 부품 분리 불가 → 네스팅 평가에서 제외
- HCE 샘플은 전개도 IoU 평가의 기준 세트

## unfold/ 사용 시 주의 (2026-10-01 점검 결과)
- `unfold/index.csv` 의 `match` 열: `ok` = 잘라낸 엔티티 수가 parts.csv n_ents 와 일치, `diff` = 불일치, `none` = 해당 bbox 안에 기하 없음
- **평가에는 match=ok 행만 사용**할 것. diff 는 이웃 부품 혼입 또는 ARC 누락 가능성 있음
- parts.csv 의 w/h 는 곡선을 꼭짓점 기준으로 근사한 값이라 큰 ARC 가 있는 부품은 bbox 가 실제보다 작음 → 그런 부품은 diff/none
- parts.csv 에는 부재번호 풍선 원(레이어 `부재번호`, 약 90x90, n_ents=1, holes=0)이 부품으로 잘못 잡힌 행이 약 900개 있음 → none 으로 표시되므로 자동 제외됨
- 근본 해결(닫힌 루프 기반 재추출)은 TODO
