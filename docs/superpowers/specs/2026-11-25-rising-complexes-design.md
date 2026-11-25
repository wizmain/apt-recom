# 오르는 단지 — 예산 안에서 최근 값이 오르는 단지 찾기 (설계)

- 작성일: 2026-11-25
- 상태: 설계 검토 중
- 참고 서비스: apt.nukk.net "어디가 오르나" (2026-11-25 분석, 지표 개념만 참고 — 화면·문구는 집토리 디자인으로 새로 만든다)

## 1. 의도와 이유

실수요자가 **"내 예산과 원하는 평형으로 살 수 있는 단지 중에 요즘 값이 오르는 곳"** 을 찾는 화면.
결과는 항상 "살 수 있는 단지"(예산·면적 조건 통과)로만 채운다. 출발점은 예산·면적 선택이다.

집토리만의 차별점: 행에서 우리 단지 상세(`/apartment/[pnu]` — 라이프 점수·넛지)로 이어져
"오르는 단지인가" 다음에 "살기 좋은 단지인가"를 바로 확인할 수 있다.

## 2. 목표 / 비목표 / 반목표

**목표**
- 면적대(59㎡급·84㎡급·대형 세부) + 매매 예산(하한~상한)으로 단지 목록을 거른다.
- 단지마다 3개월 중위가격, 6·12개월 변화, 지역 등급, 지역 내 단지 등급, 표본 신뢰도를 보여준다.
- 단지 상세 패널: 5년 월별 중위가격 + 거래량 차트, 최근 실거래, 우리 단지 상세로 가는 링크.

**비목표 (이번 범위 밖)**
- 가격 예측·추천 점수. 과거 사실만 보여준다(사용자 결정, A안).
- 전월세, 비수도권(구조는 확장 가능하게 두되 출시 범위는 수도권), 인스타 카드·MCP·챗봇 tool 연동(후속).

**반목표 (동작해도 실패로 보는 것)**
- 거래 1~2건짜리 급등이 신뢰도 표시 없이 목록 최상단을 차지하는 것.
- 동명 단지 거래 혼입 때문에 생긴 가짜 상승이 상위에 노출되는 것 → 출시 게이트(§8).
- "앞으로 오른다"로 읽히는 문구. 면책 문구 필수.
- 참고 서비스의 화면·문구를 그대로 복제하는 것.

## 3. 제약

- 백엔드: FastAPI + psycopg2 raw SQL, `routers → services → database.py`. ORM 없음.
- 프론트: `web/frontend-next`(Next.js). `web/frontend` 는 레거시라 손대지 않는다.
- 스키마는 `database.py:create_tables()` 에 추가(마이그레이션 프레임워크 없음).
- 분류값·임계값은 하드코딩 금지 — 면적대 정의는 `common_code`, 통계 임계값은 의미 있는 이름의 상수.
- 국토부 실거래는 신고 기한이 계약 후 30일이라 최근 달은 거래가 덜 잡힌다(지연 신고).
- `trade_history` 에 해제 여부(cdealType) 칼럼이 없다 — 해제 거래 제외는 이번 범위에서 불가(§10 후속).
- 운영 DB 접속(Railway)은 작업마다 사용자 허락 필요.

## 4. 접근 방식

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **1. 사전 집계 테이블 + API + Next 페이지 (채택)** | trade 배치가 집계 테이블을 갱신 → FastAPI 조회 → `/rising` 페이지 | 기존 스택과 동일, 챗봇·MCP 재사용 가능, 단지 상세 연결 자연스러움 | 테이블·배치·API·페이지 모두 새로 만든다 |
| 2. 정적 JSON → R2/CDN (참고 서비스 방식) | 배치가 JSON 생성, 브라우저 필터 | 서버 부하 0, 필터 즉시 반응 | 우리 구조 밖 별도 파이프라인, 재사용 불가 |
| 3. 홈 대시보드 탭 | `HomeShell` 에 탭 추가 | 진입 쉬움 | `HomeShell` 복잡도 증가, 표 너비 부족 |

사용자 선택: **1안**. 표시 방식은 **A안(과거 사실만)** + 집토리 추가 정렬 "지역 대비 상승률".

## 5. 지표 정의

모든 지표는 **면적대별**로 계산한다. 같은 크기끼리만 비교해야 가격·상승률이 의미가 있다
(대형은 ㎡당 단가가 구조적으로 낮다 — 인스타 value 시리즈 2026-08-01 실측과 같은 이유).

### 5.1 면적대

`common_code` group `area_band` 로 관리(code, name, extra 에 하한/상한). 초기값:

| code | 표시 | 전용면적 |
|---|---|---|
| 59 | 59㎡급 | 50 ≤ a < 70 *(빌더 판단: 경계값은 참고 서비스 미공개, 국민평형 관행으로 설정)* |
| 84 | 84㎡급 | 70 ≤ a < 100 |
| 100 | 대형 100–125㎡ | 100 ≤ a < 125 |
| 125 | 대형 125–150㎡ | 125 ≤ a < 150 |
| 150 | 대형 150–175㎡ | 150 ≤ a < 175 |
| 175 | 대형 175㎡ 이상 | 175 ≤ a |

### 5.2 기준월(base month)

신고 기한이 지난 가장 최근 달. 집계일 기준 `월말 + 30일 < 집계일` 을 만족하는 가장 최근 달.
예: 2026-11-25 집계 → 10월은 11-30 까지 신고 가능 → 기준월 **2026-09**. 화면에 "2026.09 계약까지" 표시.

### 5.3 거래 필터 (모든 지표 공통)

- 직거래(`dealing_gbn = '직거래'`) 제외. NULL(2021.11 이전)은 유지 — 상세 차트에 "2021.11 이전 거래유형 미분류" 주석.
- 이상거래: 같은 단지·같은 면적대·같은 3개월 창의 중앙값에서 ±25% 넘게 벗어난 거래 제외
  (인스타 value 시리즈 `BAND_OUTLIER_MAX_DEVIATION` 과 같은 근거).
  *(작성자 판단)* "창"은 지표 창(최근 3개월, 6개월 전 3개월, 12개월 전 3개월)마다 **독립 판정**한다.
  60개월 월별 시계열은 해당 월로 끝나는 3개월 롤링 창의 중앙값으로 판정한다. 손계산 검증(§8.3)도 이 정의를 따른다.
- 거래 → 단지: `trade_apt_mapping`(apt_seq → pnu), 단지는 `group_pnu` 대표로 묶고 `APARTMENT_VISIBLE_CONDITIONS` 통과 단지만.
- **혼입 자동 제외** (사용자 결정: b안). 매핑 교정과 별개로, 집계 단계에서 혼입 의심 거래를 뺀다.
  - 키 단위: `batch/trade/mapping_checks.py` 의 `check_mapping` → `mismatch_confirmed` 가 참인 apt_seq 의 거래 전부 제외
    (면적 대조·층·준공 타임라인 등 물리 신호, 기존 순수 함수 재사용).
  - 거래 단위: 거래 `build_year` 가 단지 준공연도와 `name_matching._BUILD_YEAR_TOLERANCE` 넘게 다른 거래 제외
    (분양권·입주권 거래는 `PRESALE_TOLERANCE_YEARS` 허용 — 기존 상수 재사용, 새 임계값 만들지 않음).
  - 정상 거래가 빠질 위험(재건축 단지 등)이 있으므로 배치는 **제외 건수와 제외 키 목록**을 로그로 남기고,
    배치 결과 요약에 면적대별 제외 비율을 포함한다. 제외 비율이 비정상적으로 크면(빌더가 실측 후 기준 설정) 경고.
  - 이 장치는 매핑을 고치지 않는다 — 걸린 키의 실제 교정은 기존 방식(`reflect_*` 스크립트)으로 한다.

### 5.4 단지 지표

| 지표 | 정의 |
|---|---|
| 3개월 중위가격 `median_price_3m` | 기준월 포함 최근 3개월 거래 중위값(만원). 거래 건수 `trade_count_3m` 함께 저장 |
| 노출 조건 | `trade_count_3m ≥ MIN_RECENT_TRADES(2)` |
| 6·12개월 변화 `change_6m_pct`, `change_12m_pct` | 최근 3개월 창 vs 6·12개월 전 같은 길이 3개월 창. **주택형(전용면적 소수 둘째 자리 반올림)별로** 두 창 모두 거래가 있는 것만 짝지어 중위값 비율을 구하고, 최근 창 거래 수로 가중평균 |
| 비교 주택형 수 `matched_type_count_6m/12m` | 위 계산에 쓰인 주택형 수. 0 이면 변화값 NULL |
| 지역 대비 상승률 `relative_change_6m_pct` | 단지 6개월 변화 − 소속 시군구 같은 면적대 6개월 변화 (집토리 추가) |
| 지역 내 단지 등급 | 시군구·면적대 안에서 최근 6개월 중위가격 순위 → 십분위 → S/A/B/C/D(각 2분위씩). *(작성자 판단)* 순위 모집단은 6개월 거래가 `MIN_GRADE_TRADES` 이상인 단지만. 미달 단지는 12개월 중위가격을 그 모집단의 십분위 컷에 대입해 등급만 주고 순위는 비우며 `grade_window_months = 12`("12개월 참고"). 노출 조건(§5.4) 미달 단지도 6개월 조건을 채우면 모집단에 포함 |

**신뢰도 표시** (UI 문구는 프론트 결정, 의미는 고정):
- 변화값 NULL → "비교 부족"
- `matched_type_count = 1` 이고 비교 창 거래 합이 적음 → "한 주택형만 비교"
- 거래 건수는 가격 아래 항상 표시

### 5.5 지역(시군구) 지표

| 지표 | 정의 |
|---|---|
| 지역 가격 수준 `median_price_3m` | 시군구·면적대 최근 3개월 거래 중위값 |
| 지역 6·12개월 변화 | 단지와 같은 방식(주택형 대신 단지×주택형 짝) |
| 지역 등급 | 면적대별 지역 가격 수준 순위를 15단계(S+~D-)로 균등 분할. 표본이 `MIN_REGION_TRADES` 미만이면 등급 없음 |

지역 등급은 **비싼 동네 등급**이지 상승세 등급이 아니다 — 화면 툴팁에 명시.

*(작성자 판단)* 계산 범위와 등급 모집단은 **설정된 시도 목록**(초기값 서울·경기·인천, `common_code` 로 관리)이다.
배치도 이 범위만 계산한다 — Railway 메모리 비용(테이블 크기) 때문. 비수도권으로 넓히면 등급은 새 모집단으로
재산정된다(등급은 상대값이고 매 배치 재계산이므로 수용).

## 6. 데이터 설계 (db-architect)

신규 테이블 3개. 모두 trade 배치가 기준월 기준으로 전체 재생성(DELETE + INSERT, 한 트랜잭션).

```
apt_band_monthly_price      -- 상세 차트용 60개월 시계열
  pnu TEXT, area_band TEXT, deal_ym INTEGER(YYYYMM),
  median_price INTEGER, trade_count INTEGER, refreshed_at TIMESTAMPTZ
  PK (pnu, area_band, deal_ym)

apt_band_trend              -- 목록용 단지 스냅샷 (기준월 1개)
  pnu TEXT, area_band TEXT, sigungu_code TEXT, base_ym INTEGER,
  median_price_3m INTEGER, trade_count_3m INTEGER, trade_count_6m INTEGER,
  change_6m_pct DOUBLE PRECISION, change_12m_pct DOUBLE PRECISION,
  matched_type_count_6m INTEGER, matched_type_count_12m INTEGER,
  relative_change_6m_pct DOUBLE PRECISION,
  complex_grade TEXT, complex_rank INTEGER, complex_rank_total INTEGER,
  grade_window_months INTEGER, refreshed_at TIMESTAMPTZ
  PK (pnu, area_band)
  INDEX (area_band, median_price_3m), INDEX (area_band, sigungu_code)

region_band_trend           -- 시군구 스냅샷
  sigungu_code TEXT, area_band TEXT, base_ym INTEGER,
  median_price_3m INTEGER, trade_count_3m INTEGER,
  change_6m_pct, change_12m_pct DOUBLE PRECISION,
  region_grade TEXT, region_rank INTEGER, region_rank_total INTEGER, refreshed_at TIMESTAMPTZ
  PK (sigungu_code, area_band)
```

- 대형 면적대는 한 단지가 여러 구간에 걸치므로 PK 에 `area_band` 가 들어가 자연스럽게 행이 나뉜다.
- 등급 컷(15단계·5단계 라벨)은 `common_code` group `price_grade` 로 관리.

## 7. 배치 / API / 화면

### 7.1 배치
- `batch/trade/refresh_band_trend.py` (신규): 위 3개 테이블 재생성. `batch/run.py` trade 체인의
  `refresh_dashboard_stats` 다음 단계로 등록.
- 거래 필터(§5.3) 상수는 이 모듈에 정의. 인스타 value 시리즈와의 공통화는 후속(§10).
- `sync_from_railway` 가 새 테이블을 동기화 대상에 포함.

### 7.2 API (api-developer) — `routers/rising.py` → `services/rising.py`
- `GET /api/rising/meta` — 기준월, 면적대 목록, 면적대별 지역 목록(등급·가격수준·변화).
- `GET /api/rising` — 파라미터 `area_band`, `budget_min`, `budget_max`(억), `sido`, `sgg`(복수), `q`, `sort`, `page`.
  응답: 단지 행 + 지역별 "예산 범위 내 단지 수". 페이지 크기 20.
  정렬: 6개월 변화(기본) · 12개월 변화 · 지역 대비 상승률 · 지역 가격대 · 지역 내 가격 순위 · 가격 낮은 순 · 예산 상한에 가까운 순. 변화값 NULL 은 항상 뒤로.
- `GET /api/rising/{pnu}?area_band=` — 60개월 시계열 + 최근 3개월 실거래(직거래 포함 여부 표시) + 단지 지표.
- `main.py` 에 라우터 등록.

### 7.3 화면 (frontend-developer) — `web/frontend-next/src/app/rising/`
```
[면적대 59|84|대형▾]  [예산 하한 ~ 상한 · 슬라이더 · 프리셋]        2026.09 계약까지
┌ 지역 ─────────────┐ ┌ N개 단지 · M개 지역   [검색] [정렬▾] ─────────────────────┐
│ 전체|서울|경기|인천│ │ 단지명/주소 | 지역등급 | 지역내등급 | 3개월 중위 | 6개월 | 12개월 │
│ 등급순 지역 목록   │ │ ...                                         (20개/페이지)  │
│ (예산 내 단지 수)  │ └───────────────────────────────────────────────────────────┘
└───────────────────┘
상세 패널: 지표 5칸 → 5년 차트(중위가격 선 + 거래량 막대) → 최근 실거래 → [이 단지 자세히 보기 → /apartment/[pnu]]
```
- 데이터 호출은 hooks 패턴(`useRising`), `useEffect` 직접 호출 금지.
- *(작성자 판단)* **정적 셸 + 클라이언트 조회.** ISR 은 운영에서 매 요청 SSR 로 동작하고(ADR-016 Proposed,
  `x-nextjs-cache: MISS`) Workers 무료 CPU 10ms 를 이미 넘으므로, 필터 조합이 서버 렌더를 타지 않게 한다.
  페이지 셸(제목·설명·면책)만 정적으로 두고 데이터는 `useRising` 이 API 로 가져온다.
- 색인: `/rising` 기본 URL 만 sitemap 포함. 필터 쿼리 URL 은 canonical 을 `/rising` 으로 두고 noindex.
- 면책 문구(접이식): 국토부 실거래 기반 참고 정보, 등급·변화율은 집토리 계산값,
  신고 시점·거래 정정·건수에 따라 달라짐, 매매 판단은 이용자 몫.
- 모바일: 표 → 카드 리스트, 지역 패널 → 상단 선택 시트.

## 8. 출시 게이트

1. **Railway 거래 키 rekey 완료** (사용자 결정: 출시 전 진행) — `docs/guides/trade-key-rekey-runbook.md` 순서
   (remap → rekey → VACUUM FULL). 각 단계 운영 DB 접속은 건별 허락.
   *(작성자 판단)* 코드 작업이 아니라 기존 런북으로 수행하는 **선행 조건**이다. 구현 계획에서는 게이트로만 추적하고,
   구현(테이블·배치·API·화면)과 병행할 수 있다.
2. rekey 후 운영 데이터로 84㎡급 6개월 변화 상위 50개 단지 수기 점검 — 혼입·이상 급등 0건 확인.
   자동 제외(§5.3)를 통과해 남은 혼입은 `reflect_*` 방식으로 교정하고 재점검. 자동 제외로 빠진 키 중
   정상 단지(오탐)가 있으면 기록해 제외 규칙 조정 근거로 쓴다.
3. 지표 검증: 표본 단지 3곳(예: 동탄역포레너스 84㎡급)을 원천 거래로 손계산해 일치 확인.

## 9. 빌더에게 맡기는 것

- 면적대 경계값 세부, 최소 표본 상수(`MIN_RECENT_TRADES`, `MIN_GRADE_TRADES`, `MIN_REGION_TRADES`)의 정확한 값 — 실데이터 분포를 보고 정하고 근거를 주석으로.
- 주택형 반올림 자릿수(기본 소수 둘째 자리) — 같은 주택형이 다르게 신고되는 사례를 보고 조정.
- 예산 슬라이더 눈금과 프리셋, 차트 컴포넌트(기존 Recharts 계열 재사용).
- URL 쿼리 파라미터로 필터 상태 보존 여부.

## 10. 후속 (별도 이슈)

- 해제 거래 제외: 수집 단계에서 `cdealType`·`cdealDay` 적재.
- 거래 필터 상수 공통 모듈화 (인스타 value 시리즈와 공유).
- 비수도권 확장, MCP tool·챗봇 연동, 인스타 카드 시리즈 연동, 지역 허브(`/region/[code]`)에서 진입 링크.
- 설계 결정은 ADR-018 로 기록(사전 집계 + 면적대·주택형 기준 변화율 정의).
