# Hedonic 검증 리포트 (자동 생성)

- 생성: 2026-07-05T03:39:06.621402+00:00
- 표본: 21,077 (아파트 단위, 최근 2년 평균 ㎡당가)
- within R² (시군구 고정효과): 0.5127

## 거리 계수 (음수 = 가까울수록 비쌈)

| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |
|---|---|---|---|
| subway | -0.031537 | -9.37 | 0.1178 |
| bus | 0.021695 | 6.48 | 0.0815 |
| school | -0.019764 | -3.25 | 0.0409 |
| assigned_elementary | -0.015837 | -2.63 | 0.033 |
| kindergarten | -0.006091 | -1.75 | 0.022 |
| hospital | 0.01347 | 4.42 | 0.0556 |
| pharmacy | -0.005873 | -1.79 | 0.0225 |
| mart | -0.038762 | -11.88 | 0.1493 |
| convenience_store | 0.002601 | 0.79 | 0.0099 |
| park | -0.020261 | -6.35 | 0.0798 |
| library | -0.008953 | -2.71 | 0.034 |
| pet_facility | -0.008949 | -2.88 | 0.0362 |
| animal_hospital | -0.024071 | -7.14 | 0.0898 |
| cctv | 0.053821 | 15.54 | 0.1954 |
| police | 0.005895 | 1.55 | 0.0195 |
| fire_station | -0.004412 | -1.01 | 0.0127 |

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
