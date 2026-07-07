# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-07-07T01:27:33.834614+00:00
- 표본: 21,077 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5243

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.031561 | -9.34 | 0.0884 |
| bus | 0.009872 | 2.91 | 0.0275 |
| school | -0.024885 | -4.12 | 0.039 |
| assigned_elementary | -0.018105 | -3.03 | 0.0287 |
| kindergarten | -0.00646 | -1.88 | 0.0178 |
| hospital | 0.023644 | 6.66 | 0.063 |
| pharmacy | -0.003753 | -1.15 | 0.0109 |
| mart | -0.031152 | -9.49 | 0.0898 |
| convenience_store | -0.00186 | -0.56 | 0.0053 |
| park | -0.020184 | -6.37 | 0.0603 |
| library | -0.008412 | -2.56 | 0.0243 |
| pet_facility | -0.004667 | -1.48 | 0.014 |
| animal_hospital | -0.019475 | -5.79 | 0.0548 |
| cctv | 0.04556 | 13.08 | 0.1238 |
| police | 0.002669 | 0.71 | 0.0067 |
| fire_station | -0.00552 | -1.28 | 0.0121 |
| cafe | 0.018124 | 6.91 | 0.0654 |
| kids_cafe | -0.02088 | -6.77 | 0.0641 |
| pet_shop | -0.007176 | -2.3 | 0.0218 |
| fitness | -0.018112 | -5.96 | 0.0564 |
| pediatric_clinic | -0.00684 | -1.79 | 0.0169 |
| obgyn_clinic | -0.012931 | -3.78 | 0.0358 |
| general_hospital | -0.033048 | -7.74 | 0.0733 |

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
