# part_name 정규화 · 형상 class 규칙

생성 스크립트: `scripts/build_part_class_dataset.py` (규칙 표 `NAME_RULES`, `LABEL_KEYWORDS`, `decide_class`).

## 1. class 5종

| class | 뜻 | 전개 공식 (unfold_rules.md) | 대표 부품 |
|---|---|---|---|
| `cylinder` | 판을 말아 만드는 원통. 전개 = 직사각형 | L = π(ID + t), H = 코스 길이 | SHELL, CHANNEL, SKIRT, JACKET SHELL, 노즐 NECK / SLEEVE |
| `cone` | 원뿔대. 전개 = 환형 부채꼴 | R1 = s·D1m/(D1m−D2m), θ = π·D1m/R1 | CONE |
| `head` | 성형 헤드. 전개 = 블랭크 원판 | 블랭크 = 형식별 약산식, 2:1 반타원은 1.2 × Dm + 2·SF (`shell_cone_head_unfold.md` 4.2. 2026-10-27 까지 reader 는 1.25~1.30 × ID) | HEAD, TOP/BTM HEAD, JACKET HEAD |
| `ring` | 평판 링 (OD/ID). 분할 가능 | 평판 | 노즐 보강 PAD, LAP PLATE, INS. RING, FIRE CLIP, COMP RING |
| `flat` | 평판 윤곽 그대로 | 평판 | RIB, BASE/WEB/WEAR PL, LUG, GUSSET, BAFFLE, COVER, STRIP, 원판형 IMP. PL |

## 2. 이름 정규화 (name_norm / name_family)

`part_name` → MTEXT 서식 코드 제거 → 대문자 → `NAME_RULES` 를 위에서부터 첫 매칭.

| 원본 표기 예 | name_norm | name_family |
|---|---|---|
| SHELL, SHELL-1 | SHELL | SHELL |
| L SHELL, L/SHELL | L SHELL | SHELL |
| CH SHELL, C/SHELL | CHANNEL SHELL | SHELL |
| CHANNEL / SKIRT / JACKET SHELL | 그대로 | SHELL |
| CONE | CONE | CONE |
| HEAD, TOP HEAD, BTM HEAD, S/HEAD, C/HEAD | HEAD | HEAD |
| JACKET HEAD | JACKET HEAD | HEAD |
| `M1/24`, `N11/3`, `K1A,K1B/3`, `N11 INT/30` (마크만) | NOZZLE | NOZZLE |
| `N1 NECK/22B`, `M1 SLEEVE`, `N/Z NECK` | NOZZLE NECK | NOZZLE |
| `N1 LAP PL/22B` | NOZZLE LAP PLATE | NOZZLE |
| `N1 PAD/22B`, `MH1 PAD`, `A PAD/10`, `K5PAD`, `S2, S3 PAD/` | NOZZLE PAD | PAD |
| SADDLE PAD, LIFT PAD, LEG PAD, LUG PAD | SUPPORT PAD | PAD |
| REINF. PAD, RE-PAD | REINF PAD | PAD |
| LIFT LUG, LIFTING LUG, LUG, TAILDING LUG, EARTH LUG | LIFTING LUG | LUG |
| RIB, RIB PL, RIB PLATE, RIB PALTE, INT. RIB, NOZ RIB | RIB | RIB |
| LIFT RIB | LIFT RIB | RIB |
| STIFF | STIFFENER | RIB |
| GUSSET, GUSSET_GS-n | GUSSET | GUSSET |
| BASE PL(ATE) / WEB PL(ATE) / WEAR PL, BEAR PL / SLDING PL, SLDING SHOE | BASE / WEB / WEAR / SLIDING PLATE | SUPPORT PLATE |
| SUPT PL, CONN PL, TOP PL, END PL, PUSH PL, DOWER PIN PL | SUPPORT PLATE | SUPPORT PLATE |
| IMP. PL, IMP. BAFFLE | IMPINGEMENT PLATE | INTERNAL |
| BAFFLE / VORT. / DEFLECTOR / PASS PART, PASSPART. / SEAL(ING) STRIP / J CLOSER / AH-1,2 | BAFFLE / VORTEX BREAKER / DEFLECTOR / PASS PARTITION / SEALING STRIP / J CLOSER / AH PLATE | INTERNAL |
| COVER PL, CH_COVER | COVER PLATE | COVER |
| INS. RING / FIRE CLIP / COMP RING / TEMPLATE | INSULATION RING / FIRE CLIP / COMPRESSION RING / TEMPLATE | RING |
| INS. CLIP | INSULATION CLIP | CLIP |
| LADDER | LADDER | EXTERNAL |

노즐 마크 행은 `nozzle_mark`(M1, N11, K1A,K1B …)와 `nozzle_inch`(24, 3 …)를 별도 열로 뽑는다. `/24B`, `/22B` 의 B 는 인치 표기 변형으로 보고 제거.

## 3. size 파싱 (shape)

| size 표기 | shape | 추출 열 |
|---|---|---|
| `2800x2949` | rect | size_w, size_h |
| `695x930xR465` | rect_radius | size_w, size_h, size_r |
| `⌀1296` | disc | d_out |
| `⌀610x⌀800` | ring | d_in, d_out |
| `⌀3042x⌀3078/8` | ring_split | d_in, d_out, n_split=8 |

## 4. class 결정 (태그 행: 이름 + size)

```
family == HEAD                        → head
family == CONE                        → cone
name_norm ∈ {SHELL, L SHELL, CHANNEL SHELL, S SHELL, JACKET SHELL, CHANNEL, SKIRT, NOZZLE NECK}
      and shape ∈ {rect, unknown}     → cylinder
name_norm == NOZZLE (마크만):  ring/ring_split → ring,  rect → cylinder(넥),  disc → flat
shape ∈ {ring, ring_split}            → ring
shape == disc                         → flat   (원판 평판: IMP. PL, COVER 등)
그 외                                  → flat
```

`class_rule` 열에 어느 분기로 결정됐는지 남긴다.

## 5. 태그 없는 부품 (source = label)

parts.csv 의 자유 텍스트 `label` 에 `LABEL_KEYWORDS` 가 포함되면 사용. 숫자만 있는 라벨(부재번호 풍선)·재질/두께만 있는 라벨은 제외.
size 가 없으므로 기하로 결정한다.

```
HEAD → head,  CONE → cone,  SHELL → cylinder
PAD/RING 계열: bbox 가 정사각(|w−h|/max < 8 %) 이고 holes ≥ 1 → ring, 아니면 flat
나머지 → flat
```

`source=label` 행은 `source=tag` 행보다 신뢰도가 낮다. 특히 label 의 SHELL 은 CP 에 라벨이 `SHELL-1` 처럼 붙은 큰 직사각형이라 안전하지만, PAD 류는 기하 추정이다.

## 6. 이미지 품질 플래그

| 열 | 뜻 |
|---|---|
| `match` | unfold 추출 시 엔티티 수 일치(ok) / 불일치(diff). diff 는 이웃 부품 혼입 또는 ARC 누락 가능 |
| `outline_closed` | 전개 DXF 의 끝점 그래프가 모두 짝수 차수(닫힌 외곽)면 1 |
| `n_open_ends` | 홀수 차수 끝점 수. 0 이면 닫힘 |
| `n_loops`, `n_geom` | 자체 닫힌 도형(원·닫힌 폴리라인) 수 + 연결 루프 수, 기하 엔티티 수 |
| `recut` | 원본 unfold DXF 가 열려 있어 CP DXF 에서 끝점 기준으로 다시 잘라낸 경우 1. 그때 `geom_dxf` 는 `recut_dxf/` 를 가리킴 |

권장 필터: 학습에는 `outline_closed=1` 우선. `cone` 은 KD23028 처럼 부채꼴을 선분 분할로 그린 도면이 많아 열림으로 남지만 형상은 인식 가능하니 눈으로 확인 후 포함 여부 결정.
