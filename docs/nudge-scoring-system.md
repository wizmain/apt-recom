# 넛지 점수 시스템 (Nudge Scoring System)

최종 갱신: 2026-08-05 (24종 시설 · 지역 프로필 · score_* 보조 축 · override-only 정책 반영)

## 개요

넛지 점수 시스템은 사용자의 라이프스타일 선호도(출퇴근, 교육, 안전 등)에 따라
아파트를 점수화하여 맞춤 추천하는 핵심 스코어링 엔진이다.

- **24종 시설**의 **거리**(근접성)와 **밀도**(1km 내 개수)를 비선형 함수로 변환
- 시설 관측치가 아닌 **score_\* 보조 축** 7종(가격/전세가율/안전/범죄/승강기/주차/대기질)을 결합
- **지역 프로필 3단계**(metro / major_city / provincial)로 수도권-지방 인프라 격차를 보정
- 사용자가 선택한 **넛지 카테고리**(9종)별 가중치로 가중 평균하여 최종 점수 산출

넛지 카테고리 (common_code `nudge_weight` 기준 9종):
`commute`(출퇴근) · `cost`(가성비) · `education`(교육) · `investment`(투자) ·
`nature`(자연) · `newlywed`(신혼) · `pet`(반려동물) · `safety`(안전) · `senior`(시니어)

각 넛지가 어떤 축을 어떤 가중치로 쓰는지는 DB가 단일 소스다 —
`GET /api/nudge/weights` 로 현행 값을 확인한다.

---

## 점수 계산 파이프라인

```
사용자 요청 (넛지 선택 + 필터)
  |
  v
[1단계] 아파트 후보 조회 (뷰포트/키워드/시군구/필터)
  |
  v
[2단계] 점수 조립 — build_facility_scores() (services/facility_scores.py, 공용 모듈)
  |        ├─ 시설 요약 bulk 조회 (apt_facility_summary, 요청 넛지가 참조하는 subtype 만)
  |        ├─ 시설별 점수 계산 (거리 70% + 밀도 30% 블렌딩, 프로필별 파라미터)
  |        ├─ 결측 중립화 (4a 지역 결측 / 4a-1 파생 지표 / 4e score_* 축)
  |        └─ score_* 보조 축 로드 (가격/안전/범죄/건축물대장/대기질)
  |
  v
[3단계] 넛지별 가중 평균 -> 멀티넛지 산술 평균 -> 최종 점수
  |
  v
정렬 + score_percentile 산출 -> 상위 N개 반환
```

점수 조립은 `services/facility_scores.py` 의 `build_facility_scores()` 로 공용화되어
세 호출측이 동일한 로직을 쓴다 (삼자 정합):

| 호출측 | 파일 | 비고 |
|--------|------|------|
| 웹 목록 | `routers/nudge.py` | 후보군 전체 대상, score_percentile 추가 산출 |
| 상세 | `routers/detail.py` | 단일 pnu, 전체 넛지 |
| MCP/챗봇 | `services/tools.py` | `mcp_server.py` 가 재사용 |

---

## 지역 프로필 (Region Profile)

시도코드 2자리 → 프로필 3단계. 매핑은 common_code(`region_profile`)가 단일 소스이며
`scoring.py` 의 `_DEFAULT_REGION_PROFILES` 는 DB 미적재 환경 폴백이다.

| 프로필 | 시도 | decay 배율 | density 배율 | max_dist 배율 |
|--------|------|-----------|-------------|--------------|
| metro | 서울(11)·인천(28)·경기(41) | ×1.0 | ×1.0 | ×1.0 |
| major_city | 부산·대구·광주·대전·울산·세종 | ×1.3 | ×1.5 | ×1.3 |
| provincial | 그 외 도 지역 | ×1.8 | ×2.0 | ×1.6 |

지방일수록 감쇠를 완만하게(멀어도 점수 유지), 밀도 환산을 후하게(적은 개수로도
점수 확보) 적용해 수도권 기준 절대평가로 인한 구조적 저평가를 막는다.

안전점수 배치(`batch/quarterly/recalc_summary.py`)의 수도권 판정도 같은
common_code(`region_profile`)를 읽는다 — 판정 기준 단일 소스.

---

## 파라미터 로딩: merge semantics + override-only 정책

decay / density factor / max_distance 는 프로필별로 다음과 같이 로드된다:

```
최종 파라미터 = { **(코드 기본값 × 프로필 배율), **(common_code 프로필 그룹 행) }
```

- **merge**: DB 행이 있는 subtype 은 DB 값 우선, 없는 subtype 은 배율 적용 기본값.
  통째 교체가 아니라 subtype 단위 merge 다 (과거 dict 교체 방식은 Phase 2 신규
  subtype 이 비수도권 프로필에서 누락되는 회귀를 일으켰다 — scoring.py 주석 참조).
- **override-only 정책 (2026-07-31)**: DB 에는 **코드 기본값과 다른 값만** 행으로
  유지한다. 기본값과 동일한 행이 남아 있으면 코드 기본값을 수정해도 DB 가 이겨서
  변경이 조용히 무시된다. 기본값 중복 행 정리는
  `scripts/cleanup_scoring_param_duplicates.py` (dry-run 기본, 멱등).
- 운영 튜닝: 달라진 값을 common_code 에 INSERT 하면 된다 (백엔드 재기동 또는
  `invalidate_cache()` 필요 — 모듈 레벨 캐시).

common_code 그룹: `facility_decay_{profile}` / `density_factor_{profile}` /
`facility_distance`(글로벌) / `facility_distance_{profile}`

- 신규 subtype 은 반드시 `_DEFAULT_*` 딕셔너리에 등록한다. 어디에도 없는
  subtype 만 호출측 폴백(decay 400 / factor 10 / max_dist 3000)을 탄다.

---

## 1단계: 거리 점수 (Distance Score)

### 공식

```
distance_score = 100 * max(0, 1 - log(1 + d / decay) / log(1 + max_d / decay))
```

| 변수 | 의미 | 출처 |
|------|------|------|
| d | 아파트~시설 최근접 거리 (m) | apt_facility_summary.nearest_distance_m |
| decay | 시설별 로그 감쇠 파라미터 | `_DEFAULT_FACILITY_DECAY` × 프로필 배율 (+ DB 오버라이드) |
| max_d | 시설별 최대 유효 거리 (m) | `_DEFAULT_MAX_DISTANCE` × 프로필 배율 (+ DB 오버라이드) |

- 거리 0m일 때 100점, max_d 이상이면 0점
- 로그 특성상 가까운 구간에서 점수 급감, 먼 구간에서 완만
- decay가 클수록 먼 거리에서도 점수가 천천히 감소 (넓은 유효 범위)
- 순수 수식 커널은 `scoring.py` 의 `log_decay_score()` — ML 곡선 적합
  (`batch/ml/apply_curves.py`)과 동일해야 하며,
  `scripts/tests/test_scoring_formula_consistency.py` 가 CI 에서 일치를 검증한다

### 시설별 파라미터 (metro 기준 코드 기본값, 24종)

| 시설 | decay | max_dist | density factor | 성격 |
|------|-------|----------|----------------|------|
| general_hospital (종합병원) | 1500 | 6000 | 60 | 응급/중증 — 광역 시설 |
| mart (대형마트) | 800 | 2000 | 15 | |
| hospital (병원) | 700 | 3000 | 8 | |
| obgyn_clinic (산부인과) | 700 | 3000 | 15 | 정기 산전관리 — 넓은 통원권 |
| academy (입시·보습학원) | 700 | 3000 | 1 | 동네 경계를 넘는 통학권 |
| subway (지하철) | 500 | 3000 | 25 | |
| kids_cafe (키즈카페) | 500 | 3000 | 20 | 희소 업종 |
| pediatric_clinic (소아과) | 500 | 2000 | 8 | 일상 통원 — 도보권 중심 |
| pharmacy (약국) | 400 | 1500 | 8 | |
| kindergarten (유치원) | 400 | 2000 | 10 | |
| school (학교) | 400 | 2000 | 15 | |
| assigned_elementary (배정초교) | 400 | 2000 | 100 | 파생 지표 — 아래 참조 |
| pet_shop (펫샵) | 400 | 2000 | 12 | |
| fitness (피트니스) | 400 | 2000 | 10 | |
| animal_hospital (동물병원) | 350 | 3000 | 15 | |
| convenience_store (편의점) | 350 | 1000 | 5 | |
| library (도서관) | 350 | 3000 | 25 | |
| bus (버스) | 300 | 1500 | 5 | |
| pet_facility (반려시설) | 300 | 3000 | 15 | |
| cctv | 300 | 1000 | 3 | |
| park (공원) | 300 | 2000 | 10 | |
| cafe (카페) | 300 | 1000 | 3 | 초밀집 — 근거리만 유의미 |
| fire_station (소방서) | 250 | 5000 | 50 | |
| police (경찰서) | 250 | 3000 | 50 | |

max_distance 는 `max_distance/decay` 비율 대역으로 설계됐다
(근린 밀집형 ~2.9-3.3 / 도보 통학권 5.0 / 광역·희소형 ~4.3-6.0 / 응급·행정형 12-20).
개별 값의 결정 근거는 `scoring.py` 의 각 딕셔너리 주석에 실측 데이터와 함께 기록돼 있다.

- `assigned_elementary` 는 단일 시설이라 밀도 개념이 없다 — 배치가 count_1km 을
  0/1 로 적재하고 factor 100 을 곱해 "1km 도보권 보너스"(0 또는 100)로 쓴다.

---

## 2단계: 밀도 점수 (Density Score)

```
density_score = min(100, count_1km * factor)
```

- count_1km: 1km 반경 내 해당 시설 개수 (apt_facility_summary.count_1km)
- factor: 위 표의 density factor × 프로필 배율
- 밀집 업종(카페·편의점)은 낮은 factor, 희소 시설(경찰서·종합병원)은 높은 factor —
  factor 값은 포화율(캡 도달 비율) 실측으로 결정한다 (scoring.py 주석에 근거 기록)

---

## 3단계: 시설 점수 블렌딩

```
facility_score = distance_score * 0.7 + density_score * 0.3
```

### subway 특례 (비수도권 인프라 부재 중립화)

비수도권(metro 외) 아파트에서 지하철이 결측이거나 컷오프 밖이고 1km 내 0개면
0점 대신 **중립 50점**을 준다 — 인프라가 아예 없는 지역에서 해당 축이 변별력
없이 전체 점수만 깎는 것을 막는다 (`facility_score()` 내부).

### 계산 예시 (metro, 대형마트 500m + 1km 내 4개)

```
distance_score = 100 * (1 - log(1 + 500/800) / log(1 + 2000/800))
density_score  = min(100, 4 * 15) = 60.0
facility_score = distance_score * 0.7 + 60.0 * 0.3
```

---

## 4단계: score_* 보조 축 (가격/안전/범죄/건물품질/대기질)

시설 관측치가 아닌 별도 테이블 유래 축. **어떤 로더가 실행될지는 요청 넛지의
가중치(nudge_weight)가 실제로 참조하는 score_\* 축에서 파생된다** — 넛지 ID
하드코딩이 아니므로, 신규 넛지를 DB 에 추가하면 코드 수정 없이 필요한 축이
자동으로 로드된다.

| 축 | 소스 | 정규화 |
|----|------|--------|
| score_price | apt_price_score.price_score | 시군구 평균 대비 `clip(0,100,(2-ratio)×50)` — 배치에서 계산, 싼 단지가 고점 |
| score_jeonse | apt_price_score.jeonse_ratio | `jeonse_ratio_to_score()`: 40% 이하 0점 ~ 90% 이상 100점 선형 |
| score_safety | apt_safety_score.safety_score (v3) | 원값 (0~100). v3 = 단지내부(35)+응급접근성(30)+지역안전(20)+범죄(15) |
| score_crime | sigungu_crime_detail.crime_safety_score | 전국 268개 시군구 백분위 (구 sigungu_crime_score 77행 테이블은 커버리지 부족으로 폐기) |
| score_elevator | apt_building_register | `elevator_to_score()`: 승강기 1대당 25세대 이하 만점, 0대는 실제 열위로 0점 |
| score_parking | apt_building_register.parking_per_hhld | `parking_ratio_to_score()`: 0.4대/세대 이하 0점 ~ 1.3대 이상 100점 선형 |
| score_air | apt_air_score.score_air | PM2.5 역방향 백분위 (배치에서 계산) |

---

## 결측 중립화 (INFRA_MISSING_NEUTRAL_SCORE = 50)

"변별력이 없는 축은 중립"이라는 원칙으로 결측을 0점 페널티 대신 50점 처리한다.

| 단계 | 대상 | 조건 |
|------|------|------|
| 4a | 시설 축 | **후보군 전체**에서 관측 0건인 subtype → 지역 인프라 부재로 보고 전원 50점. 일부 후보에만 없는 축은 실제 원거리로 간주해 0점 유지 |
| 4a-1 | 파생 지표 (`assigned_elementary`) | quarterly 배치 전 신규 아파트의 개별 결측 → 50점 ("행 없음"이 "아직 계산 안 됨"을 뜻하므로) |
| 4e | score_* 축 | 원천 테이블에 해당 아파트·시군구가 없는 개별 결측 → 50점 |

주의: 단일 pnu 조회(상세/MCP)에서는 4a 가 "이 아파트에 없는 축 전부 50점"으로
동작해 목록 검색과 semantics 가 다르다 — 코드에 의도된 선택으로 문서화돼 있다
(`detail.py`, `tools.py` 주석).

---

## 5단계: 넛지 점수 계산

```
nudge_score       = sum(score[subtype] * weight[subtype]) / sum(weight[subtype])
multi_nudge_score = mean(nudge_score_1, nudge_score_2, ...)
```

상세/목록 응답에는 넛지별 기여 상위 3개 시설(`top_contributors`,
contribution = score × 정규화 가중치)이 함께 반환된다.

---

## 넛지 가중치 관리

### 저장 구조 (common_code)

```sql
-- group_id = 'nudge_weight'
-- code = '{nudge_id}:{subtype}', name = subtype, extra = weight (문자열)
INSERT INTO common_code VALUES
  ('nudge_weight', 'commute:subway', 'subway', '0.4642', 0),
  ('nudge_weight', 'commute:bus',    'bus',    '0.3317', 0);
```

- 서버 프로세스 시작 시 1회 로드 후 모듈 캐시. 수정 시 `invalidate_cache()` 필요
- API 요청의 `weights` 파라미터로 기본 가중치 override 가능 (커스텀 가중치)

### 가중치 변경 스크립트

가중치 재배분은 `scripts/weight_update_lib.py` 공용 라이브러리를 쓴다:

- `apply_weight_additions()` — 신규 축 추가 시 기존 축을 shrink 비례 축소.
  all-or-nothing 가드 / 합 검증(±0.02) / 누적 희석 floor 가드(0.05) 내장
- `set_nudge_weights()` — 넛지 축 구성 전체 재설정 (DELETE + INSERT)
- 신규 스크립트는 additions dict 정의 + `run_cli()` 호출의 얇은 래퍼로 작성

### ML 블렌딩

`batch/ml/update_weights.py` 가 학습된 가중치를 기존 가중치에 블렌딩한다:

```
new = 기존 × (1 - ml_ratio) + ML × ml_ratio    # 기본 ml_ratio = 0.4
```

`learned_weights.json` 에 없는 subtype(score_* 축, 신규 파생 지표)은 블렌딩하지
않고 유지 후 전체 재정규화한다.

---

## ML 학습 파이프라인

`batch/run.py --type ml` 오케스트레이션:
`train_scoring` → `hedonic_validation` → `apply_curves` → `update_weights`
(뒤 2개는 `--apply` 없으면 dry-run)

| 단계 | 산출물 | 런타임 반영 경로 |
|------|--------|-----------------|
| `train_scoring.py` — XGBoost 가격 회귀 (라벨: ㎡당 평균 매매가, 피처: 기본 4 + 15 subtype × 거리/밀도) | `models/learned_weights.json`, `models/distance_curves.json`(PDP 곡선), `models/scoring_model.joblib` | 파일 직접 사용 안 함 |
| `apply_curves.py` — PDP 곡선을 로그감쇠 1파라미터로 최소자승 적합 (적합 RMSE > 20 이면 skip) | common_code `facility_decay_{profile}` upsert | DB 경유 (재기동 필요) |
| `update_weights.py` — ML 가중치 블렌딩 (위 참조) | common_code `nudge_weight` UPDATE | DB 경유 |
| `hedonic_validation.py` — 시군구 고정효과 OLS 로 현행 가중치와 시장 중요도 비교 | `models/hedonic_report.json`, `docs/analysis/hedonic-validation-latest.md` | 리포트 전용 (DB 쓰기 없음) |

**중요**: Railway 백엔드는 `web/backend/` 만 배포되어 `models/` 파일에 접근할 수
없다 — ML 결과의 런타임 반영은 항상 common_code(DB) 를 경유한다.
`models/scoring_model.joblib` 은 재학습용 아티팩트일 뿐 서빙에 쓰이지 않는다.

---

## API

### POST /api/nudge/score

**요청:**

```json
{
  "nudges": ["commute", "education"],
  "weights": null,
  "top_n": 20,
  "sw_lat": 37.48, "sw_lng": 126.95, "ne_lat": 37.52, "ne_lng": 127.05,
  "keywords": ["강남구"],
  "min_area": 60, "max_area": 85,
  "built_after": 2010
}
```

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| nudges | O | 넛지 ID 목록 (9종 중 선택) |
| weights | X | 커스텀 가중치 override (`{nudge_id: {subtype: weight}}`) |
| top_n | X | 반환 건수 (기본 20) |
| sw_lat/sw_lng/ne_lat/ne_lng | X | 지도 뷰포트 영역 |
| keyword / keywords | X | 지역/아파트명 키워드 |
| sigungu_code / bjd_code | X | 행정구역 코드 직접 지정 |
| min_area / max_area | X | 면적 필터 (㎡) |
| min_smallest_area | X | 최소 공급면적 하한 |
| min_price / max_price | X | 가격 필터 |
| min_floor / min_hhld / max_hhld | X | 층수·세대수 필터 |
| built_after / built_before | X | 준공연도 범위 |

**응답:**

```json
[
  {
    "pnu": "1168010600009850000",
    "bld_nm": "래미안대치팰리스",
    "lat": 37.4935, "lng": 127.0628,
    "total_hhld_cnt": 1608,
    "score": 78.5,
    "score_breakdown": {"commute": 82.3, "education": 74.7},
    "top_contributors": [{"subtype": "subway", "score": 92.1, "contribution": 30.4}],
    "score_percentile": 99.2
  }
]
```

- `score_percentile`: 후보군 내 백분위(1위=100.0). 상위권 절대점수가 1~4점 폭으로
  압축되는 문제를 보완하는 표시 보조 지표 — score/순위 자체는 변경하지 않는다.

### GET /api/nudge/weights

현행 넛지 가중치 설정 전체를 반환한다 (DB 가 단일 소스).

---

## 코드 구조

| 파일 | 역할 |
|------|------|
| `web/backend/services/scoring.py` | 핵심 엔진: log_decay_score, distance_to_score, density_to_score, facility_score, calculate_nudge_score, calculate_multi_nudge_score, get_top_contributors, 파라미터 로더/캐시, 정규화 함수(jeonse/parking/elevator) |
| `web/backend/services/facility_scores.py` | 점수 조립 공용 모듈: build_facility_scores (시설 bulk 조회 → 블렌딩 → 결측 중립화 → score_* 축 로드) |
| `web/backend/routers/nudge.py` | 목록 API: 후보 조회, 조립 호출, score_percentile |
| `web/backend/routers/detail.py` / `services/tools.py` | 상세 / MCP·챗봇 호출측 (동일 조립 재사용) |
| `batch/quarterly/recalc_summary.py` | apt_facility_summary + 안전점수 v3 재계산 (BallTree) |
| `batch/ml/train_scoring.py` | XGBoost 학습, Feature Importance·PDP 곡선 추출 |
| `batch/ml/apply_curves.py` | PDP 곡선 → decay 적합 → common_code 반영 |
| `batch/ml/update_weights.py` | ML 가중치 블렌딩 → nudge_weight 반영 |
| `batch/ml/hedonic_validation.py` | 시군구 고정효과 OLS 검증 리포트 |
| `scripts/weight_update_lib.py` | 가중치 재배분/재설정 공용 라이브러리 |
| `scripts/cleanup_scoring_param_duplicates.py` | common_code 기본값 중복 행 정리 (override-only 정책) |
| `scripts/tests/test_scoring_formula_consistency.py` | 웹·배치 복제 수식 일치 CI 검증 |

---

## 전체 공식 요약

```
[파라미터]
  decay/factor/max_d = (코드 기본값 × 프로필 배율) ← common_code 오버라이드 merge

[시설 점수]
  distance_score = 100 * max(0, 1 - log(1 + d/decay) / log(1 + max_d/decay))
  density_score  = min(100, count_1km * factor)
  facility_score = distance_score * 0.7 + density_score * 0.3
  (subway 특례: 비수도권 인프라 부재 시 중립 50)

[보조 축]
  score_price / score_jeonse / score_safety / score_crime /
  score_elevator / score_parking / score_air  (결측 시 중립 50)

[넛지 점수]
  nudge_score       = sum(score * weight) / sum(weight)
  multi_nudge_score = mean(nudge_score_1, nudge_score_2, ...)
```
