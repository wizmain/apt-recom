# 018. 오르는 단지 — 면적대·주택형 기준 변화율을 사전 집계 4테이블로 제공한다

- **상태**: Proposed
- **날짜**: 2026-11-25
- **설계 문서**: `docs/superpowers/specs/2026-11-25-rising-complexes-design.md`
- **관련**: [ADR-015](015-trade-key-official-id.md)(거래 키), [ADR-016](016-opennext-isr-r2-cache.md)(ISR 캐시), [ADR-017](017-inherited-mapping-physical-check.md)(매핑 물리 판정)

## 맥락

실수요자가 "내 예산과 원하는 평형으로 살 수 있는 단지 중 요즘 값이 오르는 곳"을 찾는 화면이 필요하다.
출발점은 예산·면적이고, 결과는 항상 예산·면적 조건을 통과한 단지로만 채운다. 행에서 단지 상세
(`/apartment/[pnu]`)로 이어져 "오르는가" 다음에 "살기 좋은가"를 바로 본다. 가격 예측은 하지 않고 과거
사실만 보여준다.

제약:

- 같은 크기끼리만 비교해야 가격·변화율이 의미가 있다(대형은 ㎡당 단가가 구조적으로 낮다).
- 거래 키에 동명 단지가 섞여 있어(ADR-015·017) 혼입이 가짜 상승으로 상위에 노출될 수 있다.
- 신고 기한이 계약 후 30일이라 최근 달은 거래가 덜 잡힌다.
- `trade_history` 에 해제 여부 칼럼이 없다.
- 운영 `/apartment` 는 ISR 이 매 요청 SSR 로 동작하고(ADR-016) Workers 무료 CPU 한도를 이미 넘는다.
- Railway 는 메모리(페이지 캐시 포함) 과금이라 테이블 크기가 비용이다.

## 결정

1. **사전 집계 테이블 4개 + API + Next 페이지.** trade 배치(`batch/trade/refresh_band_trend.py`)가 기준월 기준으로
   전체 재생성(DELETE + INSERT, 한 트랜잭션)하고, FastAPI(`routers/rising.py` → `services/rising.py`)는 집계만 읽는다.

   | 테이블 | 내용 |
   |---|---|
   | `apt_band_trend` | 단지×면적대 스냅샷(3개월 중위가, 6·12개월 변화, 지역 대비 상승률, 단지 등급) |
   | `region_band_trend` | 시군구×면적대 스냅샷(가격 수준, 변화, 지역 등급) |
   | `apt_band_monthly_price` | 상세 차트용 60개월 월별 시계열 |
   | `apt_band_trend_excluded_key` | 혼입 제외 키와 사유(감사·API 용). 스펙의 3테이블에서 늘었다 |

2. **면적대는 `common_code`(`rising_area_band`)** 로 관리하고 경계는 `extra "하한,상한"` 이다(59·84 와 대형 4구간).
   범위 시도는 `rising_scope_sido`(서울·인천·경기), 등급 라벨은 `rising_region_grade`(15단계)·
   `rising_complex_grade`(5단계)다. 스펙 §6 의 `price_grade` 그룹명은 이 둘로 대체됐다.
3. **변화율은 주택형(전용면적 소수 둘째 자리) 기준.** 최근 3개월 창과 6·12개월 전 같은 길이 창을 주택형별로 짝지어
   중위값 비율을 구하고 최근 창 거래 수로 가중평균한다. 짝이 없으면 NULL("비교 부족"). 지역 변화는 단지×주택형 짝.
4. **혼입 자동 제외(집계 단계, 매핑은 고치지 않음).**
   - 키 단위: `audit_mappings.find_violations`(`mismatch_confirmed`) 확정 키의 거래 전부 제외, 사유 `mapping_violation`.
   - 거래 단위: 거래 `build_year` 가 매핑 단지 준공연도와 `name_matching._BUILD_YEAR_TOLERANCE`(3년) 넘게 다르면
     그 거래만 제외, 사유 `build_year_mismatch`. **분양권 허용 오차(`PRESALE_TOLERANCE_YEARS`)는 쓰지 않는다** —
     국토부 매매 API 는 분양권을 포함하지 않는다(스펙 초안과 다름).
   - 두 사유 모두 `apt_band_trend_excluded_key` 에 기록한다. 상세 API 의 최근 실거래도 같은 제외를 적용해야 목록과
     어긋나지 않기 때문이다. 단 상세 API 는 **`mapping_violation` 키만 통째로 제외**하고, 건축년도 불일치는 거래 단위로
     같은 허용 오차를 직접 적용한다(혼입 키 안의 정상 거래 보존).
5. **월별 시계열은 노출되는 (pnu, 면적대) 쌍만 저장한다.** 상세는 목록에서만 진입하므로 노출 조건 미달 단지는 불필요하고,
   전수 저장 시 약 77MB 인 테이블이 약 42MB 로 준다(Railway 메모리 비용).
6. **단지 등급은 모집단이 5곳 미만이면 등급·순위를 NULL**(`MIN_COMPLEX_GRADE_POPULATION`, 12개월 대입 단지 포함).
   십분위 기반 5등급은 소규모 모집단에서 의미가 없다(1곳이면 유일 단지가 D). UI 는 "등급 없음"을 표시한다.
7. **정적 셸 + 클라이언트 조회.** `/rising` 은 제목·설명·면책만 정적으로 두고 데이터는 `useRising` 이 API 로 가져온다.
   필터 조합이 서버 렌더를 타지 않게 하기 위함이다(ADR-016 맥락). 필터 상태는 URL 에 넣지 않는다 — 정적 셸은 쿼리별
   noindex 를 줄 수 없으므로 쿼리 URL 자체를 만들지 않고 canonical 은 `/rising` 하나다.
8. **`sync_from_railway` 는 새 테이블을 복사하지 않는다.** 동기화 후 로컬에서 재생성한다(기존
   `refresh_dashboard_stats` 와 같은 패턴). 스펙 §7.1 의 "동기화 대상 포함"을 대체했다.
9. **배치 등록**: `batch/run.py` trade 체인의 `refresh_dashboard_stats` 다음 단계. 대시보드 집계와 같이 별도 커넥션으로
   격리하고 실패는 warning 이다. 면적대별 제외 비율이 `EXCLUSION_RATIO_WARN`(8%)을 넘으면 요약에 경고한다.

## 대안

- **정적 JSON → R2/CDN**(참고 서비스 방식) — 서버 부하 0, 필터 즉시 반응이나 별도 파이프라인이고 챗봇·MCP 재사용이 안
  된다. 기각.
- **홈 대시보드 탭** — 진입은 쉬우나 `HomeShell` 복잡도가 늘고 표 너비가 부족하다. 기각.
- **혼입 키를 매핑 교정 후에만 노출** — 교정은 건별 수작업·운영 DB 반영이라 출시를 막는다. 집계 단계 제외를 두고 교정은
  기존 방식으로 병행한다.

## 트레이드오프와 알려진 위험

- **오탐 제외 가능성.** 재건축·재개발 단지의 정상 거래가 건축년도 불일치로 빠질 수 있다. 제외 건수·키 목록을 로그와
  `apt_band_trend_excluded_key` 에 남기고, 출시 게이트에서 오탐을 기록해 규칙 조정 근거로 쓴다.
- **해제(취소) 거래 미반영.** `trade_history` 에 `cdealType`·`cdealDay` 가 없다. 수집 단계 적재가 후속 과제다.
- **직거래 제외의 비대칭.** `dealing_gbn` 커버리지가 부분적이다(로컬 실측: 2021~22 0%, 2023~25 약 30%, 2026 약 75%).
  직거래 제외가 최근 창에만 사실상 적용돼 상승률이 상향 편향될 수 있다. **출시 게이트에서 Railway 커버리지를
  확인**하고(운영 DB 접속은 건별 허락), 부족하면 재수집을 후속 이슈로 둔다.
- **거래 지연 신고.** 기준월을 `월말 + 30일 < 집계일` 인 가장 최근 달로 당기고 화면에 "YYYY.MM 계약까지"를 표시한다.
- **배치·백엔드 상수 중복.** web/backend 는 batch 를 import 할 수 없어(배포 제약) 다음 값이 양쪽에 복제돼 있다. 한쪽을
  바꾸면 반드시 함께 바꾼다(각 위치에 출처 주석).
  - `VISIBLE_APARTMENT_CONDITIONS`(batch) ↔ `APARTMENT_VISIBLE_CONDITIONS`(`routers/apartments.py`)
  - `_BUILD_YEAR_TOLERANCE`(batch `name_matching`) ↔ `BUILD_YEAR_TOLERANCE_YEARS`(`services/rising.py`)
  - `EXCLUDED_DEALING_GBN`(`band_trend_calc`) ↔ `DIRECT_DEAL_GBN`(`services/rising.py`)
  - 혼입 제외 사유 `mapping_violation`(`band_trend_aggregate`) ↔ `MAPPING_VIOLATION_REASON`(`services/rising.py`)
  - `parse_band_extra`(`band_trend_calc`) ↔ `_parse_band_extra`(`services/rising.py`)
  - 인스타 value 시리즈의 `BAND_OUTLIER_MAX_DEVIATION` 과의 공통 모듈화는 후속.
- **운영 비용.** 매 배치 전량 재생성이라 dead tuple 이 쌓인다 — 운영 후 autovacuum 을 관찰한다.
- **지역 등급은 상승세가 아니라 가격 수준이다.** 화면 툴팁에 명시한다.

## 출시 게이트 (스펙 §8)

1. Railway 거래 키 rekey 완료(`docs/guides/trade-key-rekey-runbook.md`) — 선행 조건, 구현과 병행 가능.
2. rekey 후 운영 데이터로 84㎡급 6개월 변화 상위 50 수기 점검(혼입·이상 급등 0건), 자동 제외 오탐 기록, `dealing_gbn` 커버리지 확인.
3. 표본 단지 3곳을 원천 거래로 손계산해 지표 일치 확인.

## 후속

- 수집 단계 `cdealType`·`cdealDay` 적재 후 해제 거래 제외.
- 거래 필터 상수 공통 모듈화(인스타 value 시리즈와 공유), 비수도권 확장.
- MCP tool·챗봇·인스타 카드 연동, 지역 허브(`/region/[code]`)에서 진입 링크.

## 부기 (2026-11-28) — 변화율 주의 배지: 순위는 그대로, 착시는 배지로 알린다

**맥락.** 상승 이유 분석의 1단계 검증(84㎡급 기준월 202609, 로컬)에서 6개월 상승 상위 50곳 중 최근 3개월 거래
3건 이하가 60%(전체 37%), 최근 거래 평균층이 6개월 전보다 1.5배 이상 높은 단지가 38%(전체 14%)였다. 상위
목록을 가장 많이 설명하는 것은 실제 상승 요인이 아니라 소표본과 층 구성 변화라는 착시였다. 상승 이유를 붙이기
전에 이 점을 먼저 알려야 한다.

**결정.** 순위·노출 조건은 바꾸지 않고(사용자 결정), 배치가 판정한 주의 코드를 목록·상세에 배지로 보인다.

- `apt_band_trend` 에 `avg_floor_3m`·`avg_floor_past_6m`(변화율과 같은 창·같은 이상거래 제외 후 지상층 평균)과
  `caution_codes TEXT[]` 를 더한다. 판정은 `band_trend_calc.caution_codes` 한 곳에만 있다.
  - `low_sample`: 최근 3개월 거래 3건 이하(`LOW_SAMPLE_MAX_TRADES`). 노출 하한(2건)보다 한 건 넓다.
  - `floor_mix_up`: 6개월 변화가 플러스이고 최근 평균층이 6개월 전의 1.5배 이상·3층 이상 높음.
    하락 단지의 저층 편중은 쓰는 화면이 없어 판정하지 않는다.
- 배지 문구·설명은 `common_code rising_caution`(name·extra). 배치는 적재 전에 코드-표시명 짝을 검증하고,
  API 는 코드를 `cautions: [{code, name, description}]` 로 바꿔 내보낸다(화면은 기준값을 갖지 않는다).
- 기존 프론트 "표본 적음"(2건 이하, `format.ts`)은 이 배지로 대체했다. 지도 팝업·지도 화살표는 범위 밖이라
  2건 규칙을 지도 전용 상수로 유지한다(`InfoWindowTrend.tsx` ↔ `services/rising.py THIN_SAMPLE_MAX_TRADES`).

**영향.** 로컬 재집계 기준 84㎡급 3,180단지 중 `low_sample` 1,527·`floor_mix_up` 248, 상위 50곳 중 37곳에 배지가
붙는다. 배치 로그의 면적대별 커버리지 줄에 주의 코드별 단지 수를 함께 남겨 기준 조정 근거로 쓴다.

**후속.** 층 보정 변화율(주의가 아니라 지표 자체를 보정), 홈 지도 팝업에 같은 배지 노출, 상승 신호(지역 동반 분해·
재건축 연한·역세권) 표시는 별도 과제.
