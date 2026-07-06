# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-07-06T12:12:17.199733+00:00
- 표본: 21,077 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5214

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.033198 | -9.88 | 0.1002 |
| bus | 0.012791 | 3.8 | 0.0385 |
| school | -0.023634 | -3.91 | 0.0396 |
| assigned_elementary | -0.016911 | -2.83 | 0.0287 |
| kindergarten | -0.00624 | -1.81 | 0.0184 |
| hospital | 0.018384 | 5.88 | 0.0596 |
| pharmacy | -0.004306 | -1.32 | 0.0134 |
| mart | -0.036183 | -11.15 | 0.113 |
| convenience_store | 0.000123 | 0.04 | 0.0004 |
| park | -0.018877 | -5.95 | 0.0604 |
| library | -0.009126 | -2.78 | 0.0282 |
| pet_facility | -0.004724 | -1.5 | 0.0152 |
| animal_hospital | -0.021083 | -6.28 | 0.0636 |
| cctv | 0.04709 | 13.61 | 0.1379 |
| police | 0.004213 | 1.12 | 0.0113 |
| fire_station | -0.005866 | -1.36 | 0.0138 |
| cafe | 0.016681 | 6.37 | 0.0646 |
| kids_cafe | -0.024955 | -8.19 | 0.0831 |
| pet_shop | -0.009853 | -3.17 | 0.0321 |
| fitness | -0.022816 | -7.7 | 0.0781 |

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
