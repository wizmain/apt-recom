# 안전점수 v2 — 진행 현황

> 작성일: 2026-04-05
> 설계 문서: `apt_eda/data/안전자료/safety-score-v2.md`

---

## 1. 배경

### v1 안전점수 (기존)

```
safety = 시설안전(60%) + 범죄안전(40%)
시설안전 = CCTV(50%) + 경찰서(25%) + 소방서(25%)
범죄안전 = 시군구별 가중 범죄율 (5대 범죄 × 심각도 가중 + 유동인구 보정)
```

**한계:**
- CCTV 밀도와 관공서 거리만 반영
- 교통사고, 야간 조명, 단지 내부 안전 미반영
- 시군구 단위와 반경 기반 데이터를 같은 층위에서 합산
- 극단값에 취약한 정규화

### v2 안전점수 (목표)

```
최종안전점수 = 미시환경(55%) + 접근성(20%) + 광역위험(15%) + 단지내부(10%)
```

4개 영역을 공간 해상도별로 분리하여 계산 후 통합.

---

## 2. v2 점수 구조

### 2.1 미시환경점수 (55점) — 아파트 반경 기반

| 항목 | 배점 | 데이터 | 상태 |
|------|------|--------|------|
| 범죄주의구간 | 20 | 생활안전지도 API | 추후 (API 승인 필요) |
| CCTV 밀도 | 12 | facilities(cctv) 32,060건 | **완료** |
| 보행/교통안전 | 13 | 교통사고 다발지역 5,294건 | **데이터 적재 완료** |
| 야간조명 | 10 | 보안등 42,822건 | **데이터 적재 완료** |

### 2.2 접근성점수 (20점) — 이동시간/거리

| 항목 | 배점 | 데이터 | 상태 |
|------|------|--------|------|
| 경찰 접근성 | 6 | facilities(police) 81건 | **완료** |
| 소방 접근성 | 7 | 소방서+119센터 1,024건 | **데이터 적재 완료** |
| 응급의료 접근성 | 7 | facilities(hospital) | **기존 데이터 활용** |

### 2.3 광역위험점수 (15점) — 시군구 단위

| 항목 | 배점 | 데이터 | 상태 |
|------|------|--------|------|
| 시군구 범죄율 | 6 | 경찰청 2024 범죄통계 CSV (134건) | **완료** |
| 교통사고율 | 4 | 교통사고 다발지역 시군구 집계 | **완료** |
| 지역안전지수 보정 | 2 | 행안부 생활안전점수 (133건) | **완료** |

### 2.4 단지내부점수 (10점) — K-APT 데이터

| 항목 | 배점 | 데이터 | 상태 |
|------|------|--------|------|
| 단지 CCTV | 4 | apt_kapt_info.cctv_cnt (6,002건) | **완료** |
| 경비관리 | 3 | apt_kapt_info + 관리비(경비비) | **완료** |
| 관리방식/출입통제 | 3 | apt_kapt_info.mgr_type | **완료** |

---

## 3. 수집 데이터 현황

### 3.1 신규 적재 완료

| 데이터 | 테이블 | 건수 | 출처 |
|--------|--------|------|------|
| 전국 보안등 | facilities(security_light) | 42,822건 | 전국보안등정보표준데이터.csv |
| 소방서/119센터 | facilities(fire_station/fire_center) | 1,024건 | 소방청_전국소방서 좌표현황.csv |
| 교통사고 다발지역 | traffic_accident_hotspot | 5,294건 | 17_24_lg.csv (TAAS) |

### 3.2 기존 활용 데이터

| 데이터 | 테이블 | 건수 |
|--------|--------|------|
| CCTV | facilities(cctv) | 32,060건 |
| 경찰서 | facilities(police) | 81건 |
| 병원 | facilities(hospital) | 12,491건 |
| 시군구 범죄 | sigungu_crime_detail | 77건 |
| K-APT 단지정보 | apt_kapt_info | 6,002건 (CCTV, 경비, 관리) |

### 3.3 추가 확인 완료 (미적재)

| 데이터 | 건수 | 비고 |
|--------|------|------|
| 경찰청 범죄통계 2024 | 38행 × 230지역 | 기존 2023 → 2024 교체 필요 |
| 119안전센터 현황 | 1,144건 | 좌표 없음 (Kakao 검색 필요) |
| 구급차 정보 | 1,480건 | 소방서별 구급차 수 → 소방 접근성 가중 |
| CCTV 통합관제 현황 | 78건 | 시군구 단위 (참고용) |

---

## 4. DB 변경 사항

### 4.1 신규 테이블

```sql
CREATE TABLE traffic_accident_hotspot (
    id SERIAL PRIMARY KEY,
    sigungu_name TEXT,
    spot_name TEXT,
    accident_cnt INTEGER,
    casualty_cnt INTEGER,
    death_cnt INTEGER,
    serious_cnt INTEGER,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    bjd_code TEXT
);
```

### 4.2 apt_safety_score 확장 컬럼

```sql
ALTER TABLE apt_safety_score ADD COLUMN micro_score DOUBLE PRECISION;    -- 미시환경
ALTER TABLE apt_safety_score ADD COLUMN access_score DOUBLE PRECISION;   -- 접근성
ALTER TABLE apt_safety_score ADD COLUMN macro_score DOUBLE PRECISION;    -- 광역위험
ALTER TABLE apt_safety_score ADD COLUMN complex_score DOUBLE PRECISION;  -- 단지내부
ALTER TABLE apt_safety_score ADD COLUMN data_reliability DOUBLE PRECISION; -- 데이터 신뢰도
```

### 4.3 facilities 테이블 추가 subtype

| subtype | 건수 | 용도 |
|---------|------|------|
| security_light | 42,822 | 야간조명 점수 |
| fire_center | 119센터 | 소방 접근성 |

---

## 5. 점수 계산 공식 (구현 예정)

### 5.1 미시환경점수

```
미시환경 = CCTV점수×0.34 + 보안등점수×0.29 + 교통안전점수×0.37
(범죄주의구간 20점은 추후 추가 시 비율 재조정)

CCTV점수 = percentile_rank(500m내 CCTV 수) × 12
보안등점수 = percentile_rank(500m내 보안등 수) × 10
교통안전점수 = (13 - percentile_rank(500m내 사고다발지역 건수) × 13)
```

### 5.2 접근성점수

```
접근성 = 경찰점수×0.30 + 소방점수×0.35 + 의료점수×0.35

경찰점수 = max(0, 6 - log_decay(최근접 경찰서 거리))
소방점수 = max(0, 7 - log_decay(최근접 소방서/119센터 거리))
의료점수 = max(0, 7 - log_decay(최근접 병원 거리))
```

### 5.3 광역위험점수

```
광역위험 = 범죄안전×0.55 + 교통사고안전×0.45
(자연재해, 안전지수는 추후)

범죄안전 = percentile_rank(100 - 시군구 가중범죄율) × 6
교통사고안전 = percentile_rank(100 - 시군구 사고율) × 4
```

### 5.4 단지내부점수

```
단지내부 = CCTV비율×0.40 + 경비수준×0.30 + 관리수준×0.30

CCTV비율 = percentile_rank(cctv_cnt / 세대수) × 4
경비수준 = percentile_rank(경비비 / 세대수) × 3
관리수준 = (위탁관리 3점, 자치관리 2점, 기타 1점)
```

### 5.5 정규화 (v2 권장)

```python
# 상위 95% 캡
clipped = np.clip(values, np.percentile(values, 5), np.percentile(values, 95))
# 로그 변환 (long-tail 분포)
logged = np.log1p(clipped)
# 0~100 정규화
normalized = (logged - logged.min()) / (logged.max() - logged.min()) * 100
```

---

## 6. 미완 작업

| 작업 | 파일 | 설명 |
|------|------|------|
| v2 점수 계산 | `batch/quarterly/recalc_summary.py` | 4개 영역 점수 계산 로직 구현 |
| 범죄통계 2024 적재 | `batch/safety/load_safety_data.py` | CSV→sigungu_crime_detail 갱신 |
| 상세보기 안전 탭 | `web/backend/routers/detail.py` | v2 세부 점수 반환 |
| 안전 탭 UI | `web/frontend/src/components/DetailModal.tsx` | 4개 영역 시각화 |
| 데이터 신뢰도 | `recalc_summary.py` | 최신성+완전성+좌표정확도+커버리지 |

---

## 7. 구현 스크립트

| 파일 | 설명 |
|------|------|
| `batch/safety/__init__.py` | 모듈 초기화 |
| `batch/safety/load_safety_data.py` | CSV 적재 (보안등, 소방서, 교통사고, 범죄) |
| `apt_eda/data/안전자료/safety-score-v2.md` | v2 설계 문서 |

---

## 8. 데이터 커버리지

v2 100점 중 **80점은 보유 데이터로 계산 가능** (범죄주의구간 20점만 추후):

```
미시환경 35/55점 (CCTV 12 + 보안등 10 + 교통안전 13)
접근성   20/20점 (경찰 6 + 소방 7 + 의료 7)
광역위험 10/15점 (범죄율 6 + 교통사고율 4)
단지내부 10/10점 (CCTV 4 + 경비 3 + 관리 3)
합계     75/100점
```

---

*다음 세션에서 "안전점수 v2 이어서 진행해"로 계속*
