# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-08-07T00:05:20.909271+00:00
- 표본: 24,457 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5367

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.049322 | -15.09 | 0.1236 |
| bus | 0.018333 | 5.37 | 0.044 |
| school | -0.011858 | -2.64 | 0.0216 |
| assigned_elementary | -0.019407 | -5.47 | 0.0448 |
| kindergarten | 0.004636 | 1.59 | 0.0131 |
| hospital | 0.026231 | 7.52 | 0.0616 |
| pharmacy | -0.004233 | -1.44 | 0.0118 |
| mart | -0.027712 | -9.15 | 0.075 |
| convenience_store | -0.00257 | -0.85 | 0.0069 |
| park | -0.016015 | -5.41 | 0.0443 |
| library | -0.003829 | -1.28 | 0.0105 |
| pet_facility | -0.003671 | -1.2 | 0.0098 |
| animal_hospital | -0.015682 | -5.14 | 0.0421 |
| cctv | 0.052428 | 15.2 | 0.1246 |
| police | 0.003296 | 0.96 | 0.0079 |
| fire_station | -0.002275 | -0.57 | 0.0047 |
| cafe | 0.017891 | 7.15 | 0.0586 |
| kids_cafe | -0.022085 | -7.75 | 0.0635 |
| pet_shop | -0.005516 | -1.89 | 0.0155 |
| fitness | -0.013331 | -4.61 | 0.0378 |
| pediatric_clinic | -0.007876 | -2.05 | 0.0168 |
| obgyn_clinic | -0.011975 | -3.78 | 0.0309 |
| general_hospital | -0.029163 | -7.35 | 0.0602 |
| academy | -0.020007 | -8.58 | 0.0703 |

> 해석: |t|≥2 면 유의. 시장 중요도는 넛지 가중치 조정의 참고 근거 (1-2 대체).

## 다중공선성 진단 — dist_* 피처 간 피어슨 상관 상위 10쌍 (demean 후)

| feature_a | feature_b | r |
|---|---|---|
| dist_hospital | dist_pediatric_clinic | 0.7286 |
| dist_school | dist_assigned_elementary | 0.5213 |
| dist_hospital | dist_pet_facility | 0.5136 |
| dist_pet_facility | dist_pediatric_clinic | 0.4977 |
| dist_pediatric_clinic | dist_obgyn_clinic | 0.4959 |
| dist_fitness | dist_pediatric_clinic | 0.4575 |
| dist_hospital | dist_fitness | 0.4516 |
| dist_hospital | dist_obgyn_clinic | 0.4476 |
| dist_pharmacy | dist_animal_hospital | 0.4275 |
| dist_pet_facility | dist_fitness | 0.4246 |

> |r| 이 높은 쌍은 개별 계수 해석 주의 (부호 왜곡 가능).
