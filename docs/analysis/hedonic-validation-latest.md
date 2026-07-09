# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-07-08T15:33:43.003537+00:00
- 표본: 21,077 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5267

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.033321 | -9.87 | 0.0902 |
| bus | 0.009011 | 2.66 | 0.0243 |
| school | -0.023872 | -3.96 | 0.0362 |
| assigned_elementary | -0.015237 | -2.56 | 0.0234 |
| kindergarten | -0.003965 | -1.15 | 0.0105 |
| hospital | 0.022404 | 6.32 | 0.0578 |
| pharmacy | -0.004146 | -1.27 | 0.0116 |
| mart | -0.031739 | -9.69 | 0.0885 |
| convenience_store | -0.002291 | -0.7 | 0.0064 |
| park | -0.019922 | -6.3 | 0.0576 |
| library | -0.008289 | -2.53 | 0.0231 |
| pet_facility | -0.00472 | -1.5 | 0.0137 |
| animal_hospital | -0.01893 | -5.64 | 0.0516 |
| cctv | 0.043876 | 12.61 | 0.1152 |
| police | 0.001345 | 0.36 | 0.0033 |
| fire_station | -0.00654 | -1.52 | 0.0139 |
| cafe | 0.022277 | 8.36 | 0.0764 |
| kids_cafe | -0.019481 | -6.32 | 0.0578 |
| pet_shop | -0.004456 | -1.43 | 0.013 |
| fitness | -0.014636 | -4.79 | 0.0438 |
| pediatric_clinic | -0.002506 | -0.65 | 0.006 |
| obgyn_clinic | -0.013691 | -4.01 | 0.0367 |
| general_hospital | -0.032148 | -7.55 | 0.069 |
| academy | -0.018689 | -7.67 | 0.0701 |

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
