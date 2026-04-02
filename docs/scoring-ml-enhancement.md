# 스코어링 모델 ML 기반 보완 작업 내역

> 작업일: 2026-04-01

## 개요

XGBoost ML 모델 학습 결과를 반영하여 넛지 스코어링 정확도를 개선하는 3단계 작업 수행.

**핵심 발견 (ML 분석)**:
- 대형마트 밀도가 아파트 가격에 가장 큰 영향 (29.3%), 기존 수동 가중치(10%)에서 크게 과소평가
- 지하철(45%→12%), 공원(50%→2.5%)은 크게 과대평가
- 시설 거리보다 밀도(count_1km)가 가격 설명력이 더 높음
- 가까운 거리에서의 가격 영향이 비선형적 (500m 이내 급격, 2000m 이후 미미)

---

## 1단계: 넛지 가중치 ML 기반 업데이트

### 변경 내용

`common_code` 테이블의 `nudge_weight` 49건을 ML Feature Importance 기반으로 재조정.

### 조정 방식

```
조정 가중치 = (기존 수동 가중치 × 60%) + (ML 학습 가중치 × 40%) → 정규화(합=1.0)
```

넛지별 목적(출퇴근=교통 중심, 학군=교육 중심 등)을 유지하면서 ML 가중치를 혼합.

### 주요 변경 예시

| 넛지 | 시설 | 변경 전 | 변경 후 | 방향 |
|------|------|---------|---------|------|
| 생활비 | 대형마트 | 10.0% | 20.5% | ↑ 대폭 상승 |
| 생활비 | 지하철 | 15.0% | 12.9% | ↓ |
| 신혼부부 | 대형마트 | 10.0% | 20.6% | ↑ 대폭 상승 |
| 반려동물 | 동물병원 | 30.0% | 21.7% | ↓ |
| 안전 | CCTV | 15.0% | 11.4% | ↓ |

### 파일

- `batch/ml/update_weights.py` — ML 가중치 → 넛지별 조정 → DB 반영 스크립트
- 실행: `.venv/bin/python -m batch.ml.update_weights [--dry-run] [--ml-ratio 0.4]`

---

## 2단계: 거리→점수 변환 비선형화

### 변경 전 (선형)

```python
score = 100 × (1 - distance / max_distance)
# 500m = 83점, 1000m = 67점, 2000m = 33점 (직선 감소)
```

### 변경 후 (로그 감쇠)

```python
score = 100 × max(0, 1 - log(1 + dist/decay) / log(1 + max_dist/decay))
```

- 가까운 거리에서 점수가 급격히 높고, 먼 거리에서는 차이가 미미한 비선형 곡선
- `decay` 파라미터로 시설별 유효 범위를 조절

### 시설별 decay 파라미터

ML Feature Importance에서 추출한 시설별 중요도를 반영:

| 시설 | ML 가중치 | decay | 의미 |
|------|----------|-------|------|
| 대형마트 | 29.3% | 800 | 넓은 유효 범위 (멀어도 중요) |
| 병원 | 13.2% | 700 | 의료 접근성 중요 |
| 지하철 | 11.5% | 500 | 교통 핵심 |
| 약국 | 7.8% | 400 | - |
| 유치원/학교 | 3.7%/3.1% | 400 | 교육 시설 |
| 편의점 | 4.8% | 350 | - |
| 공원 | 2.5% | 300 | 좁은 유효 범위 (가까워야 의미) |
| 경찰서/소방서 | 2.5%/2.7% | 250 | - |

### 점수 비교 (지하철, decay=500, max=3000m)

| 거리 | 선형 (전) | 로그감쇠 (후) | 차이 |
|------|----------|-------------|------|
| 100m | 96.7 | 90.6 | -6.1 |
| 500m | 83.3 | 64.4 | -18.9 |
| 1000m | 66.7 | 43.5 | -23.2 |
| 2000m | 33.3 | 17.3 | -16.0 |
| 2500m | 16.7 | 7.9 | -8.8 |

### 파일

- `web/backend/services/scoring.py` — `distance_to_score()` 함수 비선형화, `FACILITY_DECAY` 딕셔너리 추가

---

## 3단계: 시설 밀도(count_1km) 반영

### 변경 전

- `nearest_distance_m`(최근접 거리)만 사용하여 점수 산출
- 근처에 시설이 1개든 20개든 동일한 점수

### 변경 후

거리 점수(70%)와 밀도 점수(30%)를 블렌딩:

```python
distance_score = distance_to_score(nearest_m, subtype)      # 로그 감쇠
density_score  = min(100, count_1km × density_factor)        # 시설별 factor
final_score    = distance_score × 0.7 + density_score × 0.3
```

### 시설별 밀도 환산 계수 (density_factor)

| 시설 | factor | 기준 (평균 밀도) |
|------|--------|----------------|
| 편의점 | 5 | ~15개/1km |
| 버스 | 5 | ~12개/1km |
| CCTV | 3 | ~20개/1km |
| 약국/병원 | 8 | ~6~8개/1km |
| 대형마트 | 15 | ~3개/1km |
| 학교/유치원 | 10~15 | ~3~5개/1km |
| 지하철/도서관 | 25 | ~2개/1km |
| 경찰서/소방서 | 50 | ~1개/1km |

### 새 함수

```python
def density_to_score(count_1km, facility_subtype) -> float
def facility_score(distance_m, count_1km, facility_subtype, distance_ratio=0.7) -> float
```

### 파일

- `web/backend/services/scoring.py` — `density_to_score()`, `facility_score()` 함수 추가, `DENSITY_FACTOR` 딕셔너리
- `web/backend/routers/nudge.py` — `count_1km` 쿼리 추가, `facility_score()` 사용
- `web/backend/routers/detail.py` — `facility_score()` 사용
- `web/backend/services/tools.py` — `count_1km` 쿼리 추가, `facility_score()` 사용

---

## 실제 아파트 점수 비교 (무궁화APT, 15종 시설)

| 시설 | 거리 | 밀도 | 선형 (전) | 로그+밀도 (후) | 변화 |
|------|------|------|----------|-------------|------|
| bus | 76m | 63 | 97.5 | 91.2 | -6.3 |
| hospital | 104m | 50 | 96.5 | 94.2 | -2.3 |
| pharmacy | 104m | 18 | 96.5 | 89.6 | -6.9 |
| park | 463m | 14 | 84.6 | 67.9 | -16.7 |
| mart | 981m | 3 | 67.3 | 38.8 | -28.5 |
| subway | 1294m | 0 | 56.9 | 24.1 | -32.8 |
| police | 1346m | 0 | 55.1 | 19.4 | -35.7 |

**특징:**
- 가까운 시설(100m 이내): 점수 유지 (86~94점)
- 중간 거리(1000m): 선형 대비 크게 하락 — 실제 가격 영향에 부합
- 밀도 높은 시설: 밀도 점수가 블렌딩되어 일부 보전
- 먼 시설(1300m+): 선형 55→19로 크게 하락 — ML 분석 결과와 일치

---

## 수정 파일 요약

| 파일 | 변경 내용 |
|------|----------|
| `batch/ml/update_weights.py` | 신규: ML 가중치 → 넛지별 조정 → DB 업데이트 |
| `web/backend/services/scoring.py` | `distance_to_score()` 비선형화 + `facility_score()` 블렌딩 함수 추가 |
| `web/backend/routers/nudge.py` | `facility_score()` 사용, `count_1km` 쿼리 추가 |
| `web/backend/routers/detail.py` | `facility_score()` 사용 |
| `web/backend/services/tools.py` | `facility_score()` 사용, `count_1km` 쿼리 추가 |

---

## 검증

- 통합 테스트 29/29 통과
- Before/After 스코어 비교 정상 확인
- ML 분석 결과(Feature Importance)와 스코어링 경향 일치 확인

---

## 향후 개선

- ML 학습된 PDP(Partial Dependence Plot) 거리 곡선을 직접 적용하여 시설별 더 정밀한 비선형 곡선 사용
- A/B 테스트를 통한 사용자 만족도 비교 (선형 vs 비선형)
- 사용자 피드백 기반 개인화 가중치 학습
