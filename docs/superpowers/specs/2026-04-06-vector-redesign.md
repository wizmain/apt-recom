# 아파트 유사도 벡터 재설계

## 배경

현재 추천 시스템은 39차원 단일 벡터 + 코사인 유사도로 동작하며 다음 문제가 있다:
- 차원 수가 문서/코드 간 불일치 (docstring 34, 문서 39, tools.py 34)
- 가격 피처가 추천을 오염시킴 (가격대만 비슷한 결과 편향)
- CCTV 관련 중복 피처 (cctv_dist, cctv_count_1km, safety_score, cctv_count_500m)
- 거리/밀도 피처 동시 포함으로 중복 축 발생 (30→15차원으로 축소 가능)
- PDP 기반 거리 곡선이 비단조적 (거리 증가인데 점수 증가 구간 존재)
- XGBoost 가격설명 모델과 추천 벡터의 목적 혼용

## 설계 결정

### 접근법: 피처 그룹별 서브벡터 + 모드별 조합

4개 피처 그룹(`basic`, `price`, `facility`, `safety`)으로 나눠 서브벡터를 저장한다.
각 그룹은 독립적으로 StandardScaler 정규화한다.
검색 시 모드가 필요한 그룹만 선택해서 concat + 메트릭 적용한다.

선택 근거:
- 모드별 피처와 메트릭이 다르므로 독립 스케일링이 필수 (단일 벡터 방식 탈락)
- 4개 테이블 관리는 과도한 복잡도 (독립 테이블 방식 탈락)
- 피처 그룹이 자연스럽게 4개로 나뉘고, 모드별 조합이 명확함

---

## 1. 피처 그룹 재설계 (39→30차원)

### basic 그룹 (4차원)

| 피처 | 설명 |
|------|------|
| building_age | 준공연수 |
| max_floor | 최고층 |
| total_hhld_cnt | 세대수 |
| avg_area | 평균 전용면적(m2) |

### price 그룹 (3차원)

| 피처 | 설명 |
|------|------|
| price_per_m2 | m2당 매매가 |
| price_score | 가격점수 (시군구 내 백분위) |
| jeonse_ratio | 전세가율 |

### facility 그룹 (20차원)

거리와 밀도를 모두 유지하되, 핵심 시설 5종에만 nearest_distance를 추가한다.
근접성은 "1km 내 1개"와 "20m 앞 1개"를 구분하는 데 중요하며,
밀도만으로는 이 차이를 포착할 수 없다.

핵심 시설 5종 선정 기준: 일상 이용 빈도가 높고 근접성이 체감 차이에 직결되는 시설.

**밀도 피처 (15차원)** — 전 시설:

| 피처 | 설명 |
|------|------|
| subway_count_1km | 지하철역 1km 내 개수 |
| bus_count_1km | 버스정류장 |
| school_count_1km | 학교 |
| kindergarten_count_1km | 유치원 |
| hospital_count_1km | 병원 |
| park_count_1km | 공원 |
| mart_count_1km | 대형마트 |
| convenience_store_count_1km | 편의점 |
| library_count_1km | 도서관 |
| pharmacy_count_1km | 약국 |
| pet_facility_count_1km | 반려시설 |
| animal_hospital_count_1km | 동물병원 |
| police_count_1km | 경찰서 |
| fire_station_count_1km | 소방서 |
| cctv_count_1km | CCTV |

**근접성 피처 (5차원)** — 핵심 시설만:

| 피처 | 설명 |
|------|------|
| subway_dist | 최근접 지하철역 거리(m) |
| school_dist | 최근접 학교 거리(m) |
| park_dist | 최근접 공원 거리(m) |
| mart_dist | 최근접 대형마트 거리(m) |
| hospital_dist | 최근접 병원 거리(m) |

**facility 결측값 처리**:

| 피처 유형 | 결측 조건 | 대체값 | 근거 |
|---|---|---|---|
| count_1km | apt_facility_summary에 해당 subtype 행 없음 | 0 | 시설 없음 = 0개 |
| nearest_dist | apt_facility_summary에 해당 subtype 행 없음 | 5000 | 최대 탐색 반경(5km) = 사실상 없음 |
| nearest_dist | 행 존재하나 nearest_distance_m이 NULL | 5000 | 위와 동일 |

`apt_facility_summary`에 행 자체가 없는 경우는 해당 시설 유형이 탐색 반경 내에 없다는 의미.
결측 대체 후 StandardScaler에 입력하므로, 5000m는 "매우 먼 거리"로 정규화된다.
0개/5000m는 기존 `build_vectors.py`의 현행 로직과 동일하며 변경 없음.

### safety 그룹 (3차원)

종합점수(safety_score)를 제거하고 v3의 독립적인 세부 축 3개를 사용한다.
safety_score = complex_score + access_score + regional_safety_score + crime_adjust_score이므로
종합점수와 세부 축을 동시에 넣으면 중복 반영된다.

v3 안전점수 구조 (`batch/quarterly/recalc_summary.py:364`):
- complex_score: 단지내부보안 (35점) — K-APT CCTV/보안/관리/주차
- access_score: 응급접근성 (30점) — 소방서/병원/경찰서 거리 감쇠
- regional_safety_score: 행안부 지역안전지수 3분야 (20점)
- crime_adjust_score: 범죄율 보정 (15점)

3차원 구성: 서로 독립적인 소스를 가진 3축을 선택한다.
regional_safety_score와 crime_adjust_score는 모두 시군구 단위 통계이므로
합산하여 1축으로 압축한다.

| 피처 | 설명 | 소스 컬럼 | 만점 |
|------|------|-----------|------|
| complex_score | 단지내부 보안 (CCTV/보안인력/관리/주차) | apt_safety_score.complex_score | 35 |
| access_score | 응급 접근성 (소방서/병원/경찰서) | apt_safety_score.access_score | 30 |
| regional_crime_score | 지역안전 + 범죄보정 합산 | apt_safety_score.regional_safety_score + crime_adjust_score | 35 |

regional_crime_score는 벡터 생성 시 두 원시값(0~20, 0~15)을 합산한 0~35 범위의 원시값을
그대로 StandardScaler에 넣는다. 다른 safety 피처도 각각 원시 점수(0~35, 0~30)를 입력하므로
스케일러가 스케일 차이를 자동 보정한다.

데이터 소스: `batch/quarterly/recalc_summary.py`의 `_calc_safety_v3()` 함수.
v3에서 `micro_score = None`, `macro_score = None`이므로 이 피처는 사용하지 않는다.
score_version < 3인 아파트는 v3 세부 축이 NULL이므로
벡터 생성 시 NULL일 경우 각 축 만점의 50%로 대체한다
(complex_score=17.5, access_score=15, regional_crime_score=17.5).

---

## 2. 추천 모드 (4개)

### location (입지/생활권 유사도)

- **목적**: 주변 환경이 비슷한 아파트
- **피처**: facility + safety (23차원)
- **메트릭**: 코사인 유사도
- **기본 필터**: 면적 +/-30%, 세대수 +/-50%

### price (가격대 유사도)

- **목적**: 가격 구조가 비슷한 아파트
- **피처**: price (3차원)만 사용
- **메트릭**: 유클리디안 거리 -> `1 / (1 + dist)` 변환
- **기본 필터**: 면적 +/-20%
- **설계 근거**: basic(면적/연식/세대수)은 hard filter로 동질성을 확보하고,
  유사도 계산은 순수 가격 지표(m2당가격, 가격점수, 전세가율)만으로 수행한다.
  가격과 스펙을 같은 메트릭에 섞으면 "가격대 유사"가 아닌 "가격+스펙이 대충 비슷한" 결과가 되므로 분리.

### lifestyle (라이프스타일)

**모드 성격**: 유사도 검색이 아닌 **선호도 랭킹**.
대상 아파트와 비슷한 곳을 찾는 것이 아니라,
사용자가 중시하는 시설 인프라가 우수한 곳을 점수 순으로 랭킹한다.

"아이 키우기 좋은 곳"이라는 요청에서 target 아파트와 유사한 곳이 아니라
교육 인프라 자체가 좋은 곳을 찾아야 하기 때문이다.

경로의 `{pnu}`는 결과에서 자기 자신을 제외하고, 응답의 기준 아파트 컨텍스트를 제공하는 용도로만 사용한다.
유사도 계산에는 사용하지 않는다.

- **피처**: facility (20차원) x 넛지 가중치
- **메트릭**: 가중 합산 점수 (유사도가 아닌 절대 점수 랭킹)
- **기본 필터**: 없음

계산 방식:
```
score(candidate) = sum(vec_facility[i] * weight[i] for i in range(20))
```

각 후보 아파트의 facility 서브벡터에 가중치를 곱해 합산한 점수로 랭킹한다.
StandardScaler 정규화된 값이므로 양수/음수 모두 나오며,
높은 점수 = 해당 카테고리 인프라가 평균 대비 우수함을 의미한다.

넛지 가중치 소스: `common_code` 테이블(group_id='nudge_weight')에서
`nudge_id:subtype` 형태로 관리. `_load_nudge_weights()`로 로드.

넛지 카테고리 -> 피처 컬럼 매핑:

| 넛지 카테고리 | 매핑 시설 | 밀도 피처 (count_1km) | 근접성 피처 (dist) |
|---|---|---|---|
| 교통 | subway, bus | subway_count_1km, bus_count_1km | subway_dist |
| 교육 | school, kindergarten, library | school_count_1km, kindergarten_count_1km, library_count_1km | school_dist |
| 의료 | hospital, pharmacy | hospital_count_1km, pharmacy_count_1km | hospital_dist |
| 생활편의 | mart, convenience_store | mart_count_1km, convenience_store_count_1km | mart_dist |
| 자연환경 | park | park_count_1km | park_dist |
| 반려동물 | pet_facility, animal_hospital | pet_facility_count_1km, animal_hospital_count_1km | 없음 |
| 안전 | police, fire_station, cctv | police_count_1km, fire_station_count_1km, cctv_count_1km | 없음 |

가중치 분배 규칙:
- 카테고리 가중치를 해당 카테고리의 **피처 컬럼 수**로 균등 배분
- 예: 교통 가중치 0.9, 소속 피처 3개(subway_count, bus_count, subway_dist) -> 각 0.3
- 근접성 피처(dist)는 부호가 반전됨(가까울수록 좋음)이므로 가중치에 -1을 곱함
  (StandardScaler 후 거리가 클수록 양수 -> 가중치를 음수로 하면 가까운 쪽이 높은 점수)
- 매핑되지 않은 시설의 가중치는 기본값 0.1 (완전 제외하지 않음)

### combined (종합 유사도)

- **목적**: 전체 특성이 고르게 비슷한 아파트
- **피처**: basic + facility + safety (27차원, 가격 기본 제외)
- **메트릭**: 그룹별 가중 코사인 유사도
- **기본 필터**: 면적 +/-30%, 준공연도 +/-5년
- **옵션**: `include_price=true`로 가격 포함 시 30차원

**그룹별 가중치**: 단순 concat 시 facility(20차원)이 basic(4)+safety(3)를 지배한다.
각 그룹의 서브벡터를 concat 전에 그룹 가중치로 스케일링하여 영향력을 조절한다.

```
combined_vec = concat(
    vec_basic * w_basic,
    vec_facility * w_facility,
    vec_safety * w_safety
)
```

기본 그룹 가중치 (v1):

| 그룹 | 가중치 | 근거 |
|------|--------|------|
| basic | 0.25 | 규모/연식은 hard filter로도 반영되므로 유사도에서 비중 낮춤 |
| facility | 0.50 | 입지/생활 인프라가 종합 유사도의 핵심 |
| safety | 0.25 | 안전은 중요하지만 3차원이므로 과대 반영 방지 |

이 가중치는 추후 사용자 피드백/오프라인 평가로 조정 가능.
`include_price=true` 시 price 그룹 가중치 0.15를 추가하고 나머지를 비례 축소:
- price=0.15, basic=0.2125, facility=0.425, safety=0.2125 (각각 원래 값 * 0.85)

**location 모드도 동일 원칙 적용**: facility(20) + safety(3) concat 시
facility 가중치 0.75, safety 가중치 0.25.

---

## 3. 벡터 저장 구조

### 테이블

```sql
CREATE TABLE apt_vectors (
    pnu TEXT PRIMARY KEY,
    vec_basic DOUBLE PRECISION[4],
    vec_price DOUBLE PRECISION[3],
    vec_facility DOUBLE PRECISION[20],
    vec_safety DOUBLE PRECISION[3],
    vector_version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

기존 `vector DOUBLE PRECISION[]` 단일 컬럼 + `feature_names TEXT` 컬럼을 제거하고
4개 서브벡터 컬럼으로 교체한다.

`vector_version` 컬럼으로 벡터 정의 버전을 추적한다.
배치 재생성 시 버전을 올리면 백엔드가 이전 버전 벡터와 혼용하지 않도록 WHERE 조건에 포함.
피처 순서 정의는 `build_vectors.py`의 `FEATURE_GROUPS` dict가 단일 진실 원천이며,
버전 변경 이력은 이 문서에 기록한다.

### 스케일러 파일

```
models/
├── scaler_basic.joblib
├── scaler_price.joblib
├── scaler_facility.joblib
├── scaler_safety.joblib
├── scoring_model.joblib       (기존 유지)
├── distance_curves.json       (단조 보정 후 저장)
└── learned_weights.json       (기존 유지)
```

스케일러를 저장하는 이유: 증분 업데이트 시 동일 기준으로 정규화 가능.

### 버전 관리

| vector_version | 변경 내용 | 날짜 |
|---|---|---|
| 1 | 초기 버전: 4그룹 30차원 (basic 4 + price 3 + facility 20 + safety 3) | 2026-04-06 |

버전 변경 시 이 표를 업데이트하고, build_vectors.py의 `VECTOR_VERSION` 상수도 함께 올린다.

---

## 4. 거리 곡선 단조 보정 (별도 작업)

> 이 섹션은 추천 벡터 재설계와 직접 연결되지 않는 넛지/스코어링 개선이다.
> 추천 벡터 개편과 별도 배치/배포 단계로 분리하여 진행한다.
> 여기에는 설계만 기록하고, 구현 계획에서는 별도 페이즈로 취급한다.

### 현재 문제

`train_scoring.py`에서 PDP 예측값을 `[::-1]` 단순 반전하여
"거리 증가인데 점수 증가" 구간이 발생. 넛지 스코어링의 `distance_to_score()`에 영향.

### 보정 방법

1. PDP 해석을 **가격 변화량 기반**으로 개선:
   ```python
   baseline = predictions[0]  # 거리 0m 예측가격
   price_drop = (baseline - predictions) / baseline
   raw_scores = (1 - price_drop) * 100
   ```

2. Isotonic Regression으로 단조 감소 강제:
   ```python
   from sklearn.isotonic import IsotonicRegression
   iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
   monotone_scores = iso.fit_transform(distances, raw_scores)
   ```

3. 0~100 스케일링 후 `distance_curves.json`에 저장.

---

## 5. Hard Filter

### 모드별 기본 필터

| 모드 | 필터 | 기준 |
|------|------|------|
| location | 면적 +/-30% | avg_area |
| location | 세대수 +/-50% | total_hhld_cnt |
| price | 면적 +/-20% | avg_area |
| lifestyle | 없음 | - |
| combined | 면적 +/-30% | avg_area |
| combined | 준공 +/-5년 | building_age |

### 적용 위치

벡터 유사도 계산 **전**에 SQL WHERE 절로 적용.

### 필터 Override

API 파라미터로 범위 변경 또는 비활성화(`_range=0`) 가능.

### 최소 후보 보장

후보군이 `top_n * 2` 미만이면 필터 범위를 1.5배 확장해 재쿼리.
최대 1회만 확장하고, 그래도 부족하면 있는 만큼만 반환.

확장 발생 시 응답에 명시:
```json
{
  "filters_applied": {"area_range": 0.3, "hhld_range": 0.5},
  "filters_expanded": true,
  "filters_final": {"area_range": 0.45, "hhld_range": 0.75},
  "similar": [...]
}
```

모드별 확장 단계:
- location: 면적 -> 세대수 순으로 개별 확장 (면적 먼저, 세대수는 이미 넓으므로)
- price: 면적만 확장
- lifestyle: 필터 없으므로 해당 없음
- combined: 면적 -> 준공연도 순으로 개별 확장

### exclude_same_sigungu 모드별 기본값

| 모드 | 기본값 | 이유 |
|------|--------|------|
| location | false | 같은 시군구 내 입지 유사 후보가 가장 많음 |
| price | false | 가격대 비교는 지역 무관 |
| lifestyle | false | 취향 기반이므로 지역 제한 불필요 |
| combined | false | 종합 유사성은 지역 무관 |

모든 모드에서 기본 false. 사용자가 명시적으로 true로 설정 가능.

---

## 6. 검색 파이프라인

### 흐름

```
API 요청 -> 모드 결정 -> 대상 아파트 벡터 조회
  -> hard filter SQL 실행 -> 후보군 벡터 로드
  -> 서브벡터 concat -> 메트릭 계산 -> Top N 반환
```

### 메트릭 상세

- **location**: `cosine(concat(facility*0.75, safety*0.25))` -- 23차원, 그룹 가중 코사인
- **price**: `1 / (1 + euclidean(price, price))` -- 3차원 (basic은 hard filter로 분리)
- **lifestyle**: `sum(facility * nudge_weights)` -- 20차원, 가중 합산 점수 랭킹 (유사도 아님)
- **combined**: `cosine(concat(basic*0.25, facility*0.50, safety*0.25))` -- 27차원, 그룹 가중 코사인 (가격 옵션 시 30차원)

### 성능 예상

- hard filter 후 후보군 감소로 현재(50ms)보다 빠를 것
- 15,000건 규모에서 ANN 불필요. 10만건 넘으면 재검토.

---

## 7. 코드 구조 변경

### 배치

| 파일 | 변경 내용 |
|------|----------|
| `batch/ml/build_vectors.py` | FEATURE_GROUPS dict 기반 서브벡터 생성, 그룹별 스케일러 저장, apt_vectors 테이블 구조 변경 |
| `batch/ml/train_scoring.py` | 거리 곡선 단조 보정 (별도 페이즈, 섹션 4 참조) |

### 백엔드

| 파일 | 변경 내용 |
|------|----------|
| `web/backend/routers/similar.py` | 모드 파라미터 추가, hard filter SQL, similarity.py 호출로 위임 |
| `web/backend/services/similarity.py` | 신규 -- 모드별 메트릭 계산, 서브벡터 concat, 넛지 가중치 매핑 |
| `web/backend/services/tools.py` | tool description 변경, mode 파라미터 추가 |

### 문서

| 파일 | 변경 내용 |
|------|----------|
| `docs/ml-features.md` | 30차원 피처 그룹 + 4개 모드 설명으로 전체 재작성 |

---

## 8. API 설계

```
GET /api/apartment/{pnu}/similar
    ?mode=location|price|lifestyle|combined  (기본: combined)
    &top_n=5                                 (1~20)
    &exclude_same_sigungu=false
    &include_price=false                     (combined 모드 전용)
    &area_range=0.3                          (면적 필터 비율, 0=비활성)
    &hhld_range=0.5                          (세대수 필터 비율)
    &age_range=5                             (준공연도 필터, 년)

POST /api/apartment/{pnu}/similar/lifestyle
    body: {"nudge_weights": {"교통": 0.9, "교육": 0.7}, "top_n": 5}
```

lifestyle 모드만 POST로 분리한다. 이유:
- nudge_weights는 한국어 키를 포함한 JSON 객체이므로 GET 쿼리 URL encoding이 번거로움
- LLM tool 호출에서도 body로 전달하는 것이 자연스러움
- 다른 3개 모드(location/price/combined)는 GET 유지

### 응답 (location / price / combined)

```json
{
  "pnu": "1168010600009850000",
  "mode": "location",
  "filters_applied": {"area_range": 0.3, "hhld_range": 0.5},
  "similar": [
    {
      "pnu": "1165010100032760000",
      "bld_nm": "한진로즈힐",
      "sigungu_name": "서초구(서울)",
      "similarity_pct": 95.2,
      "lat": 37.49,
      "lng": 127.01,
      "total_hhld_cnt": 450,
      "use_apr_day": "20100315",
      "price_per_m2": 14895791
    }
  ]
}
```

### 응답 (lifestyle)

lifestyle은 유사도가 아닌 선호도 점수이므로 `similarity_pct` 대신 `preference_score`를 사용한다.

```json
{
  "pnu": "1168010600009850000",
  "mode": "lifestyle",
  "nudge_weights_applied": {"교통": 0.9, "교육": 0.7},
  "results": [
    {
      "pnu": "1165010100032760000",
      "bld_nm": "한진로즈힐",
      "sigungu_name": "서초구(서울)",
      "preference_score": 8.34,
      "lat": 37.49,
      "lng": 127.01,
      "total_hhld_cnt": 450,
      "use_apr_day": "20100315",
      "price_per_m2": 14895791
    }
  ]
}
```

---

## 9. 챗봇 연동

### tool description

```
선택한 아파트와 유사한 아파트를 추천합니다.
4가지 모드: location(입지 유사), price(가격대 유사), lifestyle(선호 인프라 랭킹), combined(종합 유사).
사용자 의도에 맞는 mode를 선택하세요.
lifestyle은 유사도가 아닌 선호도 랭킹입니다.
```

### 모드 자동 선택

| 사용자 발화 | 추론 모드 |
|---|---|
| "비슷한 아파트 추천해줘" | combined |
| "이 동네와 비슷한 곳" | location |
| "이 가격대에서 비슷한 아파트" | price |
| "아이 키우기 좋은 곳" | lifestyle (교육 가중) |
| "반려동물 키우기 좋은 곳" | lifestyle (반려동물 가중) |
| "여기랑 비슷한데 교통 좋은 곳" | location + lifestyle 순차 적용은 미지원, combined 사용 |

모드 추론은 LLM tool 호출 판단에 맡기되, description에 모드별 용도를 명확히 기술.

---

## 10. 배치 실행 순서

### Phase 1: 추천 벡터 개편 (이 스펙의 범위)

```bash
# 추천 벡터 재생성
uv run python -m batch.ml.build_vectors
```

### Phase 2: 거리 곡선 보정 (별도 작업)

```bash
# 스코어링 모델 재학습 + 거리 곡선 보정
uv run python -m batch.ml.train_scoring
```

---

## 11. 마이그레이션

기존 apt_vectors 테이블은 스키마가 완전히 변경되므로 (vector -> vec_basic/price/facility/safety)
`CREATE TABLE IF NOT EXISTS`만으로는 새 스키마가 적용되지 않는다.

### 안전한 마이그레이션 절차 (rename 방식)

배치 중 추천 API가 빈 상태가 되는 것을 방지하기 위해
새 테이블을 별도로 생성한 뒤 rename으로 교체한다.

1. `build_vectors.py` 시작 시 `apt_vectors_new` 테이블을 새 스키마로 CREATE
2. 전체 벡터 재생성 후 `apt_vectors_new`에 INSERT
3. 건수 검증 (기존 테이블이 존재할 때만 적용):
   - `apt_vectors_new`의 행 수가 기존 `apt_vectors` 대비 80% 이상인지 확인
   - 미달 시 `apt_vectors_new` DROP 후 에러 종료 (기존 테이블 유지)
   - 기존 테이블이 없으면 (최초 실행) 검증 건너뜀
4. 검증 통과 시 트랜잭션 내에서 atomic rename:
   ```sql
   BEGIN;
   DROP TABLE IF EXISTS apt_vectors_old;
   ALTER TABLE apt_vectors RENAME TO apt_vectors_old;
   ALTER TABLE apt_vectors_new RENAME TO apt_vectors;
   COMMIT;
   ```
5. 정상 확인 후 `apt_vectors_old` DROP (수동 또는 다음 배치에서 자동)

### 백엔드 graceful fallback

rename 완료 전까지 백엔드는 기존 `apt_vectors`를 계속 참조한다.
rename은 DDL이므로 순간적으로 테이블 잠금이 발생하지만,
SELECT 쿼리 수준에서는 ms 단위이므로 실질적 다운타임 없음.

만약 배치가 실패하여 `apt_vectors`가 아예 없는 상황이 되면
(최초 실행 시 기존 테이블이 없는 경우),
similar.py 라우터에서 테이블 부재 시 빈 결과 + 에러 메시지를 반환한다.

### 최초 실행 (기존 테이블 없음)

기존 `apt_vectors` 테이블이 없으면 rename 절차를 건너뛰고
`apt_vectors_new`를 바로 `apt_vectors`로 rename한다.
