# ML 기반 기능 가이드

## 개요

집토리 서비스에 적용된 ML 기능:
1. **유사 아파트 추천** — 아파트 특성 벡터 기반 코사인 유사도 검색
2. **넛지 스코어링 모델** — 실거래가 기반 비선형 가중치 학습

---

## 1. 유사 아파트 추천

### 원리

아파트를 30차원 특성 벡터로 표현하고, 4가지 추천 모드에서 각각 다른 메트릭과 기본 필터를 통해 가장 비슷한 아파트를 찾습니다.

### 피처 그룹 (30차원)

| 그룹 | 피처 | 설명 | 차원 |
|------|------|------|-----|
| **basic** | 준공연수, 최고층, 세대수, 평균면적 | 아파트 기본 특성 | 4 |
| **price** | ㎡당 가격, 가격점수, 전세가율 | 가격 관련 지표 | 3 |
| **facility (밀도)** | 15종 시설 1km 내 개수 | 지하철, 버스, 학교, 유치원, 병원, 공원, 마트, 편의점, 도서관, 약국, 반려시설, 동물병원, 경찰서, 소방서, CCTV | 15 |
| **facility (근접성)** | 지하철, 학교, 공원, 마트, 병원 최근접 거리 | 주요 시설까지의 최단거리 | 5 |
| **safety** | 단지내부보안, 응급접근성, 지역안전+범죄보정 | 안전 관련 스코어 | 3 |
| **합계** | | | **30** |

### 추천 모드 (4개)

| 모드 | 활용 피처 | 차원 | 유사도 메트릭 | 기본 필터 |
|------|----------|------|--------------|-----------|
| **location** | facility + safety | 23 | 그룹 가중 코사인 | 면적 ±30%, 세대수 ±50% |
| **price** | price | 3 | 유클리디안 거리 | 면적 ±20% |
| **lifestyle** | facility (밀도+근접) | 20 | 가중 합산 점수 (넛지 가중치) | 없음 |
| **combined** | basic + facility + safety | 27 | 그룹 가중 코사인 | 면적 ±30%, 준공 ±5년 |

### 정규화

- **그룹별 독립 StandardScaler** — 각 그룹(basic, price, facility, safety)마다 평균 0, 표준편차 1로 정규화
- 스케일러 저장: `models/scaler_{basic,price,facility,safety}.joblib`
- 코사인 유사도 및 가중 합산 계산에 최적화

### API

```
GET /api/apartment/{pnu}/similar?mode=location&top_n=5
POST /api/apartment/{pnu}/similar/lifestyle
Content-Type: application/json
{
  "nudge_weights": {
    "facility_density": 1.2,
    "facility_proximity": 0.8,
    ...
  }
}
```

**응답 예시:**
```json
{
  "pnu": "1168010600009850000",
  "mode": "location",
  "similar": [
    {
      "pnu": "1165010100032760000",
      "bld_nm": "한진로즈힐",
      "sigungu_name": "서초구(서울)",
      "similarity_score": 0.982,
      "price_per_m2": 14895791
    }
  ]
}
```

### 챗봇 연동

```
사용자: "래미안대치하이스턴과 비슷한 아파트 추천해줘"
→ tool: get_similar_apartments(query="래미안대치하이스턴", mode="location", top_n=5)
```

### 성능

- 벡터 생성: 15,465건 × 30차원 = **1초**
- 유사도 검색: 필터링 + Top N = **<100ms**
- 메모리: ~1.5MB (numpy 배열)
- GPU 불필요

### 벡터 재생성

시설/가격/안전 데이터가 변경되면 벡터 재생성 필요:

```bash
uv run python -m batch.ml.build_vectors
```

---

## 2. 넛지 스코어링 모델

### 현재 vs ML 스코어링

```
현재 (선형):
  score = 100 × (1 - distance / max_distance)
  → 0m = 100점, 3000m = 0점 (직선)

ML (비선형):
  score = XGBoost 모델이 학습한 곡선
  → 500m 이내 급격히 중요, 2000m 이후 차이 미미
```

### 학습 데이터

- **X (피처)**: 아파트 기본정보(4) + 시설 거리(15) + 시설 밀도(15) = 34차원
- **y (라벨)**: 아파트별 평균 ㎡당 매매가 (trade_history에서 산출)
- **데이터 수**: 14,013건 (Train 11,210 / Val 2,803)

### 모델 성능

| 지표 | 값 |
|------|---|
| R² (결정계수) | **0.59** |
| MAE (평균 절대 오차) | **187만원/㎡** |
| 학습 시간 | <1초 (XGBoost, CPU) |

### Feature Importance (학습된 시설별 가격 기여도)

| 순위 | 시설 | ML 가중치 | 현재 수동 | 차이 |
|------|------|----------|----------|------|
| 1 | **대형마트 밀도** | **29.3%** | 10% | 과소평가됨 |
| 2 | **병원** | **13.2%** | 5~25% | 적정 |
| 3 | **지하철** | **11.5%** | 15~45% | 과대평가됨 |
| 4 | 약국 | 7.8% | 5% | 과소평가 |
| 5 | 동물병원 | 5.2% | 30% (반려) | 과대평가 |
| 6 | 편의점 | 4.8% | 5~20% | 적정 |
| 7 | 버스 | 4.2% | 10~35% | 과대평가 |
| 8 | 유치원 | 3.7% | 20~25% | 과대평가 |
| 9 | 도서관 | 3.4% | 25% | 과대평가 |
| 10 | 반려시설 | 3.3% | 25~35% | 크게 과대평가 |
| 11 | CCTV | 3.2% | 15% | 과대평가 |
| 12 | 학교 | 3.1% | 10~30% | 과대평가 |
| 13 | 소방서 | 2.7% | 10~30% | 과대평가 |
| 14 | **공원** | **2.5%** | **5~50%** | **크게 과대평가** |
| 15 | 경찰서 | 2.5% | 15% | 과대평가 |

### 주요 발견

1. **대형마트 밀도가 가격에 가장 큰 영향** — 생활 인프라의 핵심 지표
2. **지하철/공원은 과대평가** — 실제 가격 기여도 대비 수동 가중치가 높음
3. **병원 접근성이 생각보다 중요** — 의료 인프라가 주거 품질의 핵심
4. **시설 거리보다 밀도(count_1km)가 더 중요** — "가까운 것 1개"보다 "주변에 많은 것"

### 모델 파일

```
models/
├── scoring_model.joblib       # XGBoost 모델 (1.2MB)
├── distance_curves.json       # 비선형 거리→점수 곡선 (시설별 50구간)
└── learned_weights.json       # 학습된 시설별 가중치
```

### 모델 재학습

거래 데이터가 축적되면 주기적 재학습 권장:

```bash
.venv/bin/python -m batch.ml.train_scoring
```

---

## 3. 파일 구조

```
batch/ml/
├── __init__.py
├── build_vectors.py      # 아파트 벡터 생성 (30차원, 4모드용)
├── train_scoring.py      # 스코어링 모델 학습 (XGBoost)
└── vector_service.py     # 벡터 저장/로드, 유사도 계산

models/
├── apartment_vectors_30d.npy      # 벡터 저장소 (30차원)
├── apartment_vectors_index.json   # PNU → 벡터 인덱스 매핑
├── scaler_basic.joblib            # basic 피처 정규화기
├── scaler_price.joblib            # price 피처 정규화기
├── scaler_facility.joblib         # facility 피처 정규화기
├── scaler_safety.joblib           # safety 피처 정규화기
├── scoring_model.joblib           # 학습된 XGBoost 모델
├── distance_curves.json           # PDP 기반 비선형 거리→점수 곡선
└── learned_weights.json           # 시설별 학습된 가중치

web/backend/
├── routers/similar.py    # GET/POST /api/apartment/{pnu}/similar
└── services/tools.py     # 챗봇 tool: get_similar_apartments
```

---

## 4. 의존성

```
scikit-learn    # StandardScaler, 코사인 유사도
xgboost         # Gradient Boosting 회귀 모델
joblib          # 모델 직렬화
numpy           # 벡터 연산
```

---

## 5. 향후 개선 방향

### 단기

- ML 가중치를 `common_code` nudge_weight에 반영하여 A/B 비교
- 거리 곡선 단조성 보정 (별도 이슈) — 학습된 비선형 거리→점수 곡선의 단조성 위반 검토 및 보정

### 중기

- 사용자 피드백 기반 개인화 가중치 학습
- 아파트 클러스터링 (K-Means) → 유형별 추천 ("이 아파트는 학군형입니다")
- 4모드별 사용자 선호도 학습

### 장기

- 가격 예측 모델 (XGBoost → "이 아파트 예상 시세: 5억2천")
- 투자 수익률 예측 (시계열 모델)
- 실시간 모델 업데이트 (배치 학습 → 온라인 학습)
