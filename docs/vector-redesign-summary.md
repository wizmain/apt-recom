# 유사 아파트 추천 벡터 재설계 구현 요약

## 개요

기존 39차원 단일 벡터 + 코사인 유사도 방식을 **30차원 4개 서브벡터 그룹 + 4개 추천 모드** 체계로 전면 재설계했다.

### 해결한 문제

| 문제 | 해결 |
|------|------|
| 차원 수 불일치 (코드 34, 문서 39, tool 34) | 30차원으로 통일, FEATURE_GROUPS dict가 단일 진실 원천 |
| 가격 피처가 추천을 오염 | 모드별 피처 분리, combined에서도 가격 기본 제외 |
| CCTV 중복 반영 (cctv_dist + cctv_count + safety_score + cctv_500m) | safety 종합점수 제거, v3 세부 축(complex/access/regional_crime) 사용 |
| 거리/밀도 30차원 중복 | 밀도 15 + 핵심 시설 근접성 5 = 20차원으로 압축 |
| 단일 메트릭으로 모든 목적 커버 | 4개 모드별 최적 메트릭 (코사인/유클리디안/가중합) |
| XGBoost 가격설명 모델과 추천 목적 혼용 | XGBoost는 스코어링용, 추천은 별도 벡터 파이프라인으로 분리 |

---

## 피처 그룹 (30차원)

### basic (4차원)

| 피처 | 설명 | 소스 |
|------|------|------|
| building_age | 준공연수 | apartments.use_apr_day |
| max_floor | 최고층 | apartments.max_floor |
| total_hhld_cnt | 세대수 | apartments.total_hhld_cnt |
| avg_area | 평균 전용면적(m2) | apt_area_info.avg_area |

### price (3차원)

| 피처 | 설명 | 소스 |
|------|------|------|
| price_per_m2 | m2당 매매가 | apt_price_score.price_per_m2 |
| price_score | 가격점수 (시군구 내 백분위) | apt_price_score.price_score |
| jeonse_ratio | 전세가율 | apt_price_score.jeonse_ratio |

### facility (20차원)

**밀도 (15차원)** -- 전 시설 1km 내 개수:
subway, bus, school, kindergarten, hospital, park, mart, convenience_store, library, pharmacy, pet_facility, animal_hospital, police, fire_station, cctv

**근접성 (5차원)** -- 핵심 시설 최근접 거리(m):
subway, school, park, mart, hospital

결측 처리: count = 0, dist = 5000 (최대 탐색 반경)

### safety (3차원)

| 피처 | 설명 | 소스 | 만점 |
|------|------|------|------|
| complex_score | 단지내부 보안 | apt_safety_score.complex_score | 35 |
| access_score | 응급 접근성 | apt_safety_score.access_score | 30 |
| regional_crime_score | 지역안전 + 범죄보정 | regional_safety_score + crime_adjust_score | 35 |

NULL 대체: 각 축 만점의 50% (17.5, 15.0, 17.5)

---

## 추천 모드

### location (입지/생활권 유사도)

| 항목 | 내용 |
|------|------|
| 목적 | 주변 환경이 비슷한 아파트 |
| 피처 | facility(20) + safety(3) = 23차원 |
| 메트릭 | 그룹 가중 코사인 유사도 (facility 0.75, safety 0.25) |
| 기본 필터 | 면적 +/-30%, 세대수 +/-50% |
| 응답 필드 | similarity_pct (0~100) |

### price (가격대 유사도)

| 항목 | 내용 |
|------|------|
| 목적 | 가격 구조가 비슷한 아파트 |
| 피처 | price(3)만 사용 |
| 메트릭 | 유클리디안 거리 -> 1/(1+dist) 변환 |
| 기본 필터 | 면적 +/-20% |
| 응답 필드 | similarity_pct (0~100) |

basic(면적/연식/세대수)은 hard filter로 동질성을 확보하고 유사도 계산에는 포함하지 않는다.

### lifestyle (선호도 랭킹)

| 항목 | 내용 |
|------|------|
| 목적 | 사용자 넛지 가중치 기반 인프라 랭킹 |
| 피처 | facility(20) x 넛지 가중치 |
| 메트릭 | 가중 합산 점수 (유사도가 아닌 절대 점수) |
| 기본 필터 | 없음 |
| 응답 필드 | preference_score |

유사도 검색이 아닌 선호도 랭킹이다.
target 아파트와 비슷한 곳이 아니라 사용자가 중시하는 인프라가 우수한 곳을 찾는다.

넛지 카테고리 -> 시설 매핑:

| 카테고리 | 밀도 피처 | 근접성 피처 |
|----------|----------|------------|
| 교통 | subway, bus | subway_dist |
| 교육 | school, kindergarten, library | school_dist |
| 의료 | hospital, pharmacy | hospital_dist |
| 생활편의 | mart, convenience_store | mart_dist |
| 자연환경 | park | park_dist |
| 반려동물 | pet_facility, animal_hospital | - |
| 안전 | police, fire_station, cctv | - |

### combined (종합 유사도)

| 항목 | 내용 |
|------|------|
| 목적 | 전체 특성이 고르게 비슷한 아파트 |
| 피처 | basic(4) + facility(20) + safety(3) = 27차원 |
| 메트릭 | 그룹 가중 코사인 유사도 (basic 0.25, facility 0.50, safety 0.25) |
| 기본 필터 | 면적 +/-30%, 준공연도 +/-5년 |
| 옵션 | include_price=true 시 price(3) 추가 -> 30차원 |
| 응답 필드 | similarity_pct (0~100) |

include_price=true일 때 가중치: price 0.15, basic 0.2125, facility 0.425, safety 0.2125

---

## API

### GET /api/apartment/{pnu}/similar

location, price, combined 3개 모드 지원.

```
GET /api/apartment/{pnu}/similar
    ?mode=location|price|combined  (기본: combined)
    &top_n=5                       (1~20)
    &exclude_same_sigungu=false
    &include_price=false           (combined 전용)
    &area_range=0.3                (면적 필터, 0=비활성)
    &hhld_range=0.5                (세대수 필터)
    &age_range=5                   (준공연도 필터)
```

응답:

```json
{
  "pnu": "1168010600009850000",
  "mode": "location",
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

### POST /api/apartment/{pnu}/similar/lifestyle

lifestyle 모드 전용 (nudge_weights가 한국어 키를 포함한 JSON이므로 POST 분리).

```json
{
  "nudge_weights": {"교통": 0.9, "교육": 0.7},
  "top_n": 5,
  "exclude_same_sigungu": false
}
```

응답:

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
      "lng": 127.01
    }
  ]
}
```

---

## Hard Filter

### 모드별 기본 필터

| 모드 | 필터 | 기준 |
|------|------|------|
| location | 면적 +/-30%, 세대수 +/-50% | avg_area, total_hhld_cnt |
| price | 면적 +/-20% | avg_area |
| lifestyle | 없음 | - |
| combined | 면적 +/-30%, 준공 +/-5년 | avg_area, building_age |

- SQL WHERE 절로 유사도 계산 전에 적용
- API 파라미터로 범위 변경 또는 비활성화(=0) 가능
- 후보 부족 시 필터 1.5배 확장 후 재쿼리 (최대 1회)
- 확장 시 응답에 `filters_expanded: true` 포함

---

## 벡터 저장 구조

### apt_vectors 테이블

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

### 스케일러 파일

```
models/
  scaler_basic.joblib
  scaler_price.joblib
  scaler_facility.joblib
  scaler_safety.joblib
```

그룹별 독립 StandardScaler. 증분 업데이트 시 동일 기준으로 정규화 가능.

### 벡터 버전 관리

| vector_version | 변경 내용 | 날짜 |
|---|---|---|
| 1 | 초기 버전: 4그룹 30차원 | 2026-04-07 |

---

## 코드 구조

### 배치

| 파일 | 역할 |
|------|------|
| `batch/ml/build_vectors.py` | 4그룹 서브벡터 생성, 스케일러 저장, atomic rename 마이그레이션 |

### 백엔드

| 파일 | 역할 |
|------|------|
| `web/backend/services/similarity.py` | 순수 계산 모듈: 모드별 메트릭, 넛지 가중치 매핑, 그룹 가중치 |
| `web/backend/routers/similar.py` | API 엔드포인트, hard filter SQL, 필터 확장 로직 |
| `web/backend/services/tools.py` | 챗봇 tool: 4개 모드 지원, LLM이 의도에 따라 모드 자동 선택 |

### 테스트

| 파일 | 테스트 |
|------|--------|
| `web/backend/tests/test_core.py` | 서브벡터 구조, location/price/lifestyle/combined 모드 검증 (5건) |

---

## 마이그레이션

atomic rename 방식으로 무중단 교체:

1. `apt_vectors_new` 테이블 생성 (새 스키마)
2. 전체 벡터 INSERT
3. 건수 검증: 기존 대비 80% 이상 (기존 테이블 있을 때만)
4. 검증 통과 시:
   - `apt_vectors` -> `apt_vectors_old`
   - `apt_vectors_new` -> `apt_vectors`
   - `apt_vectors_old` 삭제
5. 검증 실패 시: `apt_vectors_new` 삭제, 기존 테이블 유지

---

## 실행 명령

```bash
# 벡터 재생성
uv run python -m batch.ml.build_vectors

# 통합 테스트
uv run python web/backend/tests/test_core.py
```

---

## 검증 결과

| 항목 | 결과 |
|------|------|
| 벡터 생성 | 22,990건 (v1, 30차원) |
| atomic rename | 기존 22,805 -> 신규 22,990 (정상 교체) |
| 가격 데이터 미보유 | 3,355건 (기본값 적용, 로그 경고) |
| 신규 테스트 | 5/5 PASS |
| 기존 테스트 | 변경 영향 없음 |

---

## 챗봇 모드 자동 선택

| 사용자 발화 | 추론 모드 |
|-------------|----------|
| "비슷한 아파트 추천해줘" | combined |
| "이 동네와 비슷한 곳" | location |
| "이 가격대에서 비슷한 아파트" | price |
| "아이 키우기 좋은 곳" | lifestyle (교육 가중) |
| "반려동물 키우기 좋은 곳" | lifestyle (반려동물 가중) |

---

## 향후 작업 (별도 스펙)

- 거리 곡선 단조 보정 (Isotonic Regression) -- 넛지 스코어링 개선
- 사용자 피드백 기반 추천 품질 평가 지표
- 학습된 similarity (pairwise ranking, metric learning)
