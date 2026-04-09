# 넛지 점수 시스템 (Nudge Scoring System)

## 개요

넛지 점수 시스템은 사용자의 라이프스타일 선호도(교통, 교육, 의료 등)에 따라
아파트를 점수화하여 맞춤 추천하는 핵심 스코어링 엔진이다.

15종 시설의 **거리**(근접성)와 **밀도**(1km 내 개수)를 비선형 함수로 변환한 후,
사용자가 선택한 넛지 카테고리별 가중치로 가중 평균하여 최종 점수를 산출한다.

---

## 점수 계산 파이프라인

```
사용자 요청 (넛지 선택 + 필터)
  |
  v
[1단계] 아파트 후보 조회 (지역/키워드/필터)
  |
  v
[2단계] 시설 데이터 로드 (apt_facility_summary)
  |
  v
[3단계] 시설별 점수 계산 (거리 70% + 밀도 30% 블렌딩)
  |
  v
[4단계] 보조 점수 로드 (가격/안전/범죄)
  |
  v
[5단계] 넛지별 가중 평균 -> 멀티넛지 평균 -> 최종 점수
  |
  v
상위 N개 반환
```

---

## 1단계: 거리 점수 (Distance Score)

### 공식

```
distance_score = 100 * max(0, 1 - log(1 + d / decay) / log(1 + max_d / decay))
```

| 변수 | 의미 | 출처 |
|------|------|------|
| d | 아파트~시설 최근접 거리 (m) | apt_facility_summary.nearest_distance_m |
| decay | 시설별 로그 감쇠 파라미터 | FACILITY_DECAY 상수 (scoring.py) |
| max_d | 시설별 최대 유효 거리 (m) | common_code 테이블 (group_id='facility_distance') |

### 동작 원리

- 거리 0m일 때 100점
- max_d 이상이면 0점
- 로그 함수 특성상 가까운 구간에서 점수가 급격히 높고, 먼 구간에서 차이가 미미
- decay가 클수록 먼 거리에서도 점수가 천천히 감소 (중요 시설에 넓은 유효 범위)

### FACILITY_DECAY (시설별 감쇠 파라미터)

XGBoost 학습 결과(Feature Importance)를 기반으로 설정.
중요도가 높은 시설일수록 decay 값이 커서 먼 거리에서도 점수가 유지된다.

| 시설 | decay | ML 가중치 | 해석 |
|------|-------|----------|------|
| mart (대형마트) | 800 | 29.3% | 가장 중요, 넓은 유효 범위 |
| hospital (병원) | 700 | 13.2% | 의료 접근성 중요 |
| subway (지하철) | 500 | 11.5% | 교통 핵심 |
| pharmacy (약국) | 400 | 7.8% | |
| kindergarten (유치원) | 400 | 3.7% | |
| school (학교) | 400 | 3.1% | |
| animal_hospital (동물병원) | 350 | 5.2% | |
| convenience_store (편의점) | 350 | 4.8% | |
| library (도서관) | 350 | 3.4% | |
| bus (버스) | 300 | 4.2% | |
| pet_facility (반려시설) | 300 | 3.3% | |
| cctv | 300 | 3.2% | |
| park (공원) | 300 | 2.5% | |
| fire_station (소방서) | 250 | 2.7% | |
| police (경찰서) | 250 | 2.5% | |

### 거리 점수 곡선 예시

대형마트 (decay=800, max_d=3000):

```
거리(m)     점수
0           100.0
100          93.2
300          80.5
500          69.9
1000         46.8
1500         28.3
2000         14.2
2500          4.6
3000          0.0
```

지하철 (decay=500, max_d=3000):

```
거리(m)     점수
0           100.0
100          89.2
300          72.2
500          57.7
1000         27.0
1500          7.6
2000          0.0
```

---

## 2단계: 밀도 점수 (Density Score)

### 공식

```
density_score = min(100, count_1km * factor)
```

| 변수 | 의미 | 출처 |
|------|------|------|
| count_1km | 1km 반경 내 해당 시설 개수 | apt_facility_summary.count_1km |
| factor | 시설별 밀도 환산 계수 | DENSITY_FACTOR 상수 (scoring.py) |

### DENSITY_FACTOR (시설별 밀도 환산 계수)

평균 밀도가 높은 시설(편의점 등)은 factor가 낮고,
희소한 시설(경찰서 등)은 factor가 높아서 1개만 있어도 높은 점수를 받는다.

| 시설 | factor | 평균 밀도 | 100점 기준 |
|------|--------|----------|-----------|
| cctv | 3 | ~20개/1km | 34개 |
| convenience_store | 5 | ~15개/1km | 20개 |
| bus | 5 | ~12개/1km | 20개 |
| pharmacy | 8 | ~8개/1km | 13개 |
| hospital | 8 | ~6개/1km | 13개 |
| kindergarten | 10 | ~5개/1km | 10개 |
| park | 10 | ~5개/1km | 10개 |
| mart | 15 | ~3개/1km | 7개 |
| school | 15 | ~3개/1km | 7개 |
| pet_facility | 15 | ~3개/1km | 7개 |
| animal_hospital | 15 | ~3개/1km | 7개 |
| subway | 25 | ~2개/1km | 4개 |
| library | 25 | ~2개/1km | 4개 |
| police | 50 | ~1개/1km | 2개 |
| fire_station | 50 | ~1개/1km | 2개 |

---

## 3단계: 시설 점수 블렌딩

### 공식

```
facility_score = distance_score * 0.7 + density_score * 0.3
```

거리 점수(근접성)에 70%, 밀도 점수(주변 풍부도)에 30%를 부여한다.

### 계산 예시

**대형마트가 500m 거리에 있고, 1km 내에 4개가 있는 경우:**

```
distance_score = 100 * (1 - log(1 + 500/800) / log(1 + 3000/800))
               = 100 * (1 - log(1.625) / log(4.75))
               = 100 * (1 - 0.486 / 1.558)
               = 100 * 0.688
               = 68.8

density_score  = min(100, 4 * 15) = 60.0

facility_score = 68.8 * 0.7 + 60.0 * 0.3
               = 48.2 + 18.0
               = 66.2
```

**지하철이 200m 거리에 있고, 1km 내에 3개가 있는 경우:**

```
distance_score = 100 * (1 - log(1 + 200/500) / log(1 + 3000/500))
               = 100 * (1 - log(1.4) / log(7.0))
               = 100 * (1 - 0.336 / 1.946)
               = 100 * 0.827
               = 82.7

density_score  = min(100, 3 * 25) = 75.0

facility_score = 82.7 * 0.7 + 75.0 * 0.3
               = 57.9 + 22.5
               = 80.4
```

---

## 4단계: 보조 점수 (가격/안전/범죄)

특정 넛지 카테고리는 시설 외에 추가 데이터를 사용한다.

| 넛지 | 추가 피처 | 소스 |
|------|----------|------|
| cost, investment | score_price (가격 점수) | apt_price_score.price_score |
| cost, investment | score_jeonse (전세가율) | apt_price_score.jeonse_ratio |
| cost, newlywed, senior, safety | score_safety (안전 점수) | apt_safety_score.safety_score |
| safety | score_crime (범죄 안전) | sigungu_crime_score.crime_safety_score |

이 점수들은 `facility_scores` dict에 추가되어 넛지 가중 평균에 포함된다.

---

## 5단계: 넛지 점수 계산

### 단일 넛지 점수 (가중 평균)

```
nudge_score = sum(facility_score[subtype] * weight[subtype]) / sum(weight[subtype])
```

| 변수 | 의미 | 출처 |
|------|------|------|
| facility_score[subtype] | 3단계에서 계산한 시설별 블렌딩 점수 | scoring.facility_score() |
| weight[subtype] | 넛지 내 시설별 가중치 | common_code (group_id='nudge_weight') 또는 사용자 커스텀 |

### 멀티 넛지 점수 (산술 평균)

```
multi_nudge_score = mean([nudge_score_1, nudge_score_2, ...])
```

사용자가 여러 넛지를 동시에 선택하면 각 넛지 점수의 산술 평균을 최종 점수로 사용한다.

### 계산 예시

**사용자가 "교통" 넛지를 선택한 경우:**

교통 넛지의 가중치 (common_code에서 로드):
- subway: 0.45
- bus: 0.35

특정 아파트의 시설 점수:
- subway: 80.4 (200m, 3개)
- bus: 55.2 (400m, 8개)

```
교통 넛지 점수 = (80.4 * 0.45 + 55.2 * 0.35) / (0.45 + 0.35)
              = (36.18 + 19.32) / 0.80
              = 69.4
```

---

## 넛지 가중치 관리

### 저장 구조 (common_code 테이블)

```sql
-- group_id = 'nudge_weight'
-- code = '{nudge_id}:{subtype}'
-- name = subtype
-- extra = weight (문자열)

INSERT INTO common_code VALUES
  ('nudge_weight', 'family:kindergarten', 'kindergarten', '0.3', 1),
  ('nudge_weight', 'family:school',       'school',       '0.3', 2),
  ('nudge_weight', 'family:park',         'park',         '0.2', 3),
  ('nudge_weight', 'family:library',      'library',      '0.2', 4);
```

### 로딩 및 캐싱

```python
# scoring.py에서 모듈 레벨 캐시로 1회 로드
_nudge_weights = {
    "family": {"kindergarten": 0.3, "school": 0.3, "park": 0.2, "library": 0.2},
    "transport": {"subway": 0.45, "bus": 0.35, ...},
    ...
}
```

- 서버 프로세스 시작 시 1회 로드, 이후 메모리 캐시 사용
- `invalidate_cache()` 호출 시 캐시 리셋 (관리자 API에서 가중치 수정 시)

### 사용자 커스텀 가중치

API 요청 시 `weights` 파라미터로 기본 가중치를 override할 수 있다:

```json
{
  "nudges": ["family"],
  "weights": {
    "family": {"school": 0.5, "kindergarten": 0.3, "park": 0.2}
  }
}
```

---

## 최대 유효 거리

### 저장 구조 (common_code 테이블)

```sql
-- group_id = 'facility_distance'
-- code = subtype
-- name = 최대 거리 (미터, 문자열)

INSERT INTO common_code VALUES
  ('facility_distance', 'subway',  '3000', '', 1),
  ('facility_distance', 'hospital','2500', '', 2),
  ('facility_distance', 'mart',    '3000', '', 3);
```

- 이 거리 이상이면 점수 0
- 미등록 시설은 기본값 3000m 적용
- 코드 변경 없이 DB에서 시설별 유효 범위 조정 가능

---

## ML 학습 기반 파라미터

### XGBoost 가격 회귀 모델

넛지 점수의 decay 파라미터와 가중치 기준은 XGBoost 회귀 모델의 Feature Importance에서 도출했다.

| 항목 | 값 |
|------|---|
| 학습 데이터 | 14,013개 아파트 x 34 피처 |
| 라벨 (y) | m2당 평균 매매가 |
| 모델 | XGBoost (n_estimators=300, max_depth=6) |
| 성능 | R2=0.59, MAE=187만원/m2 |

### 학습된 시설별 가중치 (learned_weights.json)

| 순위 | 시설 | ML 가중치 |
|------|------|----------|
| 1 | 대형마트 | 29.3% |
| 2 | 병원 | 13.0% |
| 3 | 지하철 | 11.5% |
| 4 | 약국 | 7.8% |
| 5 | 동물병원 | 5.2% |
| 6 | 편의점 | 4.8% |
| 7 | 버스 | 4.0% |
| 8 | 유치원 | 3.7% |
| 9 | 도서관 | 3.4% |
| 10 | 반려시설 | 3.3% |
| 11 | CCTV | 3.2% |
| 12 | 학교 | 3.1% |
| 13 | 소방서 | 2.7% |
| 14 | 공원 | 2.5% |
| 15 | 경찰서 | 2.5% |

### 주요 발견

1. **대형마트 밀도가 가격에 가장 큰 영향** -- 생활 인프라의 핵심 지표
2. **지하철/공원은 체감 대비 과대평가** -- 실제 가격 기여도 대비 수동 가중치가 높았음
3. **병원 접근성이 예상보다 중요** -- 의료 인프라가 주거 품질의 핵심
4. **시설 거리보다 밀도(count_1km)가 더 중요** -- "가까운 것 1개"보다 "주변에 많은 것"

### 거리 곡선 (distance_curves.json)

XGBoost PDP(Partial Dependence Plot)로 추출한 시설별 비선형 거리-점수 곡선.
각 시설에 대해 0~5000m 구간의 50개 점수 샘플을 저장한다.

현재 scoring.py에서는 직접 사용하지 않고 FACILITY_DECAY 상수를 사용하며,
향후 단조 보정(Isotonic Regression) 적용 후 활용 예정이다.

---

## API

### POST /api/nudge/score

넛지 점수 계산 및 상위 N개 반환.

**요청:**

```json
{
  "nudges": ["family", "transport"],
  "weights": null,
  "top_n": 20,
  "sw_lat": 37.48, "sw_lng": 126.95,
  "ne_lat": 37.52, "ne_lng": 127.05,
  "keywords": ["강남구"],
  "min_area": 60,
  "max_area": 85,
  "built_after": 2010
}
```

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| nudges | O | 넛지 ID 목록 |
| weights | X | 커스텀 가중치 override |
| top_n | X | 반환 건수 (기본 20) |
| sw_lat/sw_lng/ne_lat/ne_lng | X | 지도 뷰포트 영역 |
| keywords | X | 지역/아파트명 키워드 |
| min_area / max_area | X | 면적 필터 (m2) |
| min_price / max_price | X | 가격 필터 (억원) |
| min_floor | X | 최소 층수 |
| min_hhld / max_hhld | X | 세대수 범위 |
| built_after / built_before | X | 준공연도 범위 |

**응답:**

```json
[
  {
    "pnu": "1168010600009850000",
    "bld_nm": "래미안대치팰리스",
    "lat": 37.4935,
    "lng": 127.0628,
    "total_hhld_cnt": 1608,
    "score": 78.5,
    "score_breakdown": {
      "family": 82.3,
      "transport": 74.7
    }
  }
]
```

### GET /api/nudge/weights

현재 넛지 가중치 설정 반환.

```json
{
  "family": {"kindergarten": 0.3, "school": 0.3, "park": 0.2, "library": 0.2},
  "transport": {"subway": 0.45, "bus": 0.35}
}
```

---

## 코드 구조

| 파일 | 역할 |
|------|------|
| `web/backend/services/scoring.py` | 핵심 엔진: distance_to_score, density_to_score, facility_score, calculate_nudge_score, calculate_multi_nudge_score |
| `web/backend/routers/nudge.py` | API 엔드포인트: 아파트 조회, 시설 데이터 로드, 점수 계산 오케스트레이션 |
| `batch/ml/train_scoring.py` | XGBoost 학습, Feature Importance 추출, 거리 곡선 생성 |
| `models/learned_weights.json` | ML 학습된 시설별 가중치 |
| `models/distance_curves.json` | PDP 기반 비선형 거리 곡선 (50구간/시설) |
| `models/scoring_model.joblib` | XGBoost 모델 파일 |

---

## 전체 공식 요약

```
[시설 점수]
  distance_score = 100 * max(0, 1 - log(1 + d/decay) / log(1 + max_d/decay))
  density_score  = min(100, count_1km * factor)
  facility_score = distance_score * 0.7 + density_score * 0.3

[넛지 점수]
  nudge_score = sum(facility_score * weight) / sum(weight)

[최종 점수]
  multi_nudge_score = mean(nudge_score_1, nudge_score_2, ...)
```
