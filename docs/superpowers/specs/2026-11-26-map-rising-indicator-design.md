# 지도 마커 상승·하락 표시 + 팝업 가격 추세 (설계)

- 작성일: 2026-11-26
- 상태: 설계 검토 중
- 관련: 오르는 단지(`docs/superpowers/specs/2026-11-25-rising-complexes-design.md`, ADR-018)

## 1. 의도

지도를 훑는 단계에서 **어디가 오르고 내리는지 바로 보이게** 하고(마커 ▲/▼), 단지를 누르면
**근거 숫자**(중위가격·변화율·등급·신뢰도)를 팝업에서 확인하게 한다. 데이터는 오르는 단지
집계(`apt_band_trend`·`region_band_trend`)를 그대로 쓴다.

## 2. 목표 / 비목표 / 반목표

**목표**
- 홈 지도 일반 마커에 6개월 변화 방향(▲ 상승 / ▼ 하락)과 변화율 표시.
- 마커 팝업(일반·추천 모드 공통)에 대표(또는 필터) 면적대의 가격 추세 요약 + "오르는 단지에서 보기" 링크.

**비목표**
- 추천(넛지) 모드 순위 핀의 화살표(이번 범위 밖 — 사용자 확인).
- 비수도권(집계 범위 밖 — 표시 없음), 새 집계 지표.

**반목표**
- 거래 1~2건·비교 불가 단지에 화살표가 붙어 "오른다"로 읽히는 것.
- 사용자가 고른 평형과 다른 평형 기준 화살표(필터 연동으로 방지).
- 추세 조회 실패가 지도 자체를 깨뜨리는 것.

## 3. 결정 사항 (사용자 확정)

| 항목 | 결정 |
|---|---|
| 화살표 기준 | **B안**: 지도 면적 필터(`min_area`/`max_area`)와 겹치는 면적대 중 최근 3개월 거래가 가장 많은 면적대. 필터 없으면 모든 면적대 중 최근 3개월 거래 최다(대표 면적대) |
| 기간 | 6개월 변화(`change_6m_pct`) |
| 보합 | ±2% 이내는 화살표 없음 |
| 표시 제외 | 변화값 없음(비교 부족) 또는 3개월 거래 ≤ 2건(표본 적음) |
| 구현 방식 | **1안**: 별도 요약 API + 프론트 훅 결합 (단지 목록 API 비변경) |

## 4. 작성자 판단 (바꾸려면 말씀)

- **색**: 오르는 단지 화면과 같게 상승 초록·하락 빨강(국내 관례와 반대 — 바꾸려면 오르는 단지 화면도 함께).
- **화살표는 일반 마커만**, 팝업 정보는 일반·추천 모드 공통.
- **요청 상한**: 화면 단지 수가 `MAP_TREND_MAX_PNUS`(예 2,000)를 넘으면 요약을 요청하지 않는다 —
  클러스터러 `minLevel` 5 이상 줌에서는 마커가 묶여 개별 화살표가 보이지 않는다. 개별 마커가 보이는
  레벨(≤4)에서는 화면 단지 수가 상한보다 훨씬 적다고 보고, 구현 시 서울 도심 레벨 4 화면 단지 수를
  실측해 상한을 정한다(실측이 상한에 가까우면 상한을 올린다 — 일부만 조회하는 방식은 쓰지 않는다).
- **요청 PNU 집합**: 일반 단지(`apartments`) ∪ 추천 순위 단지(`scoredApartments`) ∪ 챗 하이라이트 —
  팝업이 세 마커 모두에서 열리므로 같은 요약에서 찾는다. 상한은 합집합 크기에 적용.
- **group_pnu**: 집계는 대표 단지(group_pnu) 기준이다. 서버가 요청 PNU 를 `apartments.group_pnu` 로 바꿔
  조회하고 응답은 **요청한 원래 PNU 를 키로** 돌려준다(비대표 PNU 도 같은 단지 추세를 받는다).
- **`min_smallest_area` 필터는 면적대 선택에 쓰지 않는다** — 단지 구성(가장 작은 주택형) 조건이지
  사용자가 보는 평형이 아니고, FilterPanel 에도 노출되지 않는 딥링크 전용 필터다.

## 5. 설계

### 5.1 API — `POST /api/rising/map`
- 요청 본문: `{ "pnus": [...], "min_area": number|null, "max_area": number|null }` (pnus 최대 `MAP_TREND_MAX_PNUS`, 초과 시 422).
  GET 쿼리스트링은 수천 개 PNU 를 담기 어려워 POST.
- 응답: `{ "base_ym": int|null, "items": { [pnu]: MapTrend } }` — 지표 없는 PNU 는 키 없음.
  `MapTrend = { area_band, area_band_name, median_price_3m, trade_count_3m, change_6m_pct, change_12m_pct,
  complex_grade, complex_rank, complex_rank_total, grade_window_months, region_grade, direction }`
  - `direction` ∈ `up` | `down` | `flat` | `none` — 서버에서 판정(보합 ±2%, 비교 부족·표본 적음은 `none`).
    임계값은 서비스 상수(`FLAT_THRESHOLD_PCT = 2.0`, `THIN_SAMPLE_MAX_TRADES = 2` — 프론트 `format.ts` 와 같은 값, 출처 주석).
- 면적대 선택(SQL): `apt_band_trend` 에서 요청 PNU 중, 필터가 있으면 면적대 [min,max) 가 필터 범위와 겹치는 행만,
  PNU 별 `trade_count_3m DESC, area_band` 첫 행(`DISTINCT ON (pnu)`). 면적대 경계는 `rising_area_band` common_code.
- 위치: `routers/rising.py`(검증) → `services/rising.py` 신규 함수 `get_map_trends`. 기존 `region_grade` 조인 재사용.

### 5.2 프론트
- 타입: `types/rising.ts` 에 `MapTrend`, `MapTrendResponse`, `TrendDirection`.
- 훅: `hooks/useMapTrends.ts` — `apartments`(지도 단지)·`filters.min_area/max_area` 변화 시 디바운스 후 POST, 이전 요청 취소,
  `Record<pnu, MapTrend>` 반환. 실패 시 빈 객체(지도 영향 없음) + 콘솔 경고. 상한 초과 시 요청 안 함.
- 마커: `Map/markers/createTrendMarker.ts` 신규 — `direction` 이 up/down 이면 SVG 핀 + 상단 배지(▲3.2% / ▼1.8%),
  flat/none/미존재면 기존 `createBasicMarker` 와 같은 기본 핀. MarkerClusterer 등록은 그대로.
- `MapView`: 일반 마커 생성 시 `trends[apt.pnu]` 로 마커 선택. `trends` 가 바뀌면 일반 마커 재생성.
- 팝업: `InfoWindowBody` 에 `trend?: MapTrend` 를 받아 **추세 블록**(별도 컴포넌트 `InfoWindowTrend.tsx`):
  면적대명 · 3개월 중위가격(N건, 표본 적음) · 6개월/12개월 변화 · 지역 가격 등급 · 지역 내 단지 등급 ·
  "오르는 단지에서 보기 →" (`/rising` — 해당 단지 자동 선택은 범위 밖, 링크만). trend 없으면 블록 생략.
- 공용 포맷: `app/rising/format.ts`(formatEok·formatChange·isThinSample)와 `GradeBadge` 재사용.

## 6. 검증
- 백엔드 통합 테스트(test_core): 필터 없음 대표 면적대 선택, 필터 범위 면적대 선택, direction 판정 경계(±2%, 표본 2건), 상한 초과 422, 빈 pnus.
- 프론트: lint·build, 브라우저에서 수도권 확대 시 화살표 표시·필터 변경 시 갱신·팝업 블록·비수도권 무표시 확인.

## 7. 빌더에게 맡기는 것
- 배지 SVG 디자인(크기·폰트), 디바운스 시간, `MAP_TREND_MAX_PNUS` 정확한 값(실측 후).
- 팝업 블록 레이아웃 세부.
