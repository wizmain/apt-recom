# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-07-03T12:58:15.024904+00:00
- 표본: 21,077 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5115

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.031571 | -9.37 | 0.1173 |
| bus | 0.021263 | 6.35 | 0.0794 |
| school | -0.019782 | -3.25 | 0.0407 |
| assigned_elementary | -0.016291 | -2.7 | 0.0338 |
| kindergarten | -0.006109 | -1.76 | 0.022 |
| hospital | 0.013648 | 4.48 | 0.056 |
| pharmacy | -0.006136 | -1.87 | 0.0234 |
| mart | -0.038908 | -11.91 | 0.1491 |
| convenience_store | 0.002773 | 0.84 | 0.0105 |
| park | -0.020436 | -6.4 | 0.08 |
| library | -0.00921 | -2.78 | 0.0348 |
| pet_facility | -0.008735 | -2.81 | 0.0351 |
| animal_hospital | -0.024113 | -7.15 | 0.0895 |
| cctv | 0.054361 | 15.68 | 0.1963 |
| police | 0.005976 | 1.57 | 0.0197 |
| fire_station | -0.004333 | -0.99 | 0.0124 |

> 해석: |t|≥2 면 유의. 시장 중요도는 넛지 가중치 조정의 참고 근거 (1-2 대체).

## 다중공선성 진단 — dist_* 피처 간 피어슨 상관 상위 10쌍 (demean 후)

| feature_a | feature_b | r |
|---|---|---|
| dist_school | dist_assigned_elementary | 0.9155 |
| dist_hospital | dist_pet_facility | 0.7439 |
| dist_pharmacy | dist_convenience_store | 0.7334 |
| dist_bus | dist_cctv | 0.7235 |
| dist_assigned_elementary | dist_kindergarten | 0.6886 |
| dist_school | dist_cctv | 0.6856 |
| dist_convenience_store | dist_cctv | 0.685 |
| dist_school | dist_kindergarten | 0.6806 |
| dist_hospital | dist_pharmacy | 0.6795 |
| dist_pharmacy | dist_animal_hospital | 0.6763 |

> |r| 이 높은 쌍은 개별 계수 해석 주의 (부호 왜곡 가능).
