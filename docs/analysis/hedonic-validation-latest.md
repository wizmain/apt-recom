# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-07-06T13:29:05.599931+00:00
- 표본: 21,077 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5239

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.031342 | -9.27 | 0.0875 |
| bus | 0.009796 | 2.88 | 0.0272 |
| school | -0.024439 | -4.05 | 0.0382 |
| assigned_elementary | -0.018494 | -3.1 | 0.0293 |
| kindergarten | -0.006531 | -1.9 | 0.0179 |
| hospital | 0.023646 | 6.66 | 0.0628 |
| pharmacy | -0.003639 | -1.11 | 0.0105 |
| mart | -0.031469 | -9.58 | 0.0905 |
| convenience_store | -0.001722 | -0.52 | 0.0049 |
| park | -0.020009 | -6.31 | 0.0596 |
| library | -0.008805 | -2.68 | 0.0253 |
| pet_facility | -0.00447 | -1.42 | 0.0134 |
| animal_hospital | -0.019415 | -5.77 | 0.0545 |
| cctv | 0.045164 | 12.97 | 0.1225 |
| police | 0.002726 | 0.72 | 0.0068 |
| fire_station | -0.005687 | -1.31 | 0.0124 |
| cafe | 0.018173 | 6.93 | 0.0654 |
| kids_cafe | -0.02089 | -6.77 | 0.0639 |
| pet_shop | -0.007232 | -2.32 | 0.0219 |
| fitness | -0.01831 | -6.03 | 0.0569 |
| pediatric_clinic | -0.006747 | -1.76 | 0.0166 |
| obgyn_clinic | -0.013663 | -4.0 | 0.0378 |
| general_hospital | -0.033382 | -7.82 | 0.0738 |

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
