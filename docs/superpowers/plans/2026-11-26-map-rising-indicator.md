# 지도 마커 상승·하락 표시 + 팝업 가격 추세 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 홈 지도 일반 마커에 6개월 변화 ▲/▼ 배지를, 모든 마커 팝업에 오르는 단지 가격 추세 요약을 보여준다.

**Architecture:** 백엔드에 `POST /api/rising/map`(요청 PNU → 면적대 선택 → 추세 요약 + 방향 판정)을 추가하고, 프론트는 `useMapTrends` 훅이 지도 단지 집합으로 요약을 받아 `MapView` 의 마커 생성·팝업에 넘긴다. 단지 목록 API(`/api/apartments`)는 바꾸지 않는다.

**Tech Stack:** FastAPI · psycopg2 raw SQL · Next.js 16 / React 19 · TypeScript · Tailwind 4 · axios · Kakao Maps(MarkerClusterer)

**Spec:** `docs/superpowers/specs/2026-11-26-map-rising-indicator-design.md`

## Global Constraints

- 단지 목록 API `/api/apartments` 와 그 응답 타입은 바꾸지 않는다.
- 방향 판정은 서버에서: `FLAT_THRESHOLD_PCT = 2.0`(|6개월 변화| ≤ 2.0 → `flat`), `THIN_SAMPLE_MAX_TRADES = 2`(3개월 거래 ≤ 2 → `none`), 변화값 NULL → `none`. 프론트 `app/rising/format.ts` 의 `THIN_SAMPLE_MAX_TRADES` 와 같은 값 — 양쪽에 출처 주석.
- 면적대 선택: 필터 `min_area`/`max_area`(㎡)와 면적대 [min, max) 가 겹치는 면적대 중 `trade_count_3m` 최다(동률이면 `area_band` 오름차순). 필터 없으면 전 면적대. `min_smallest_area` 는 쓰지 않는다.
- 집계는 대표 단지(`apartments.group_pnu`) 기준 — 요청 PNU 를 group_pnu 로 바꿔 조회, 응답 키는 요청 PNU.
- 요청 상한 `MAP_TREND_MAX_PNUS`(초기 2000, 서버·프론트 같은 값): 서버는 초과 시 422, 프론트는 초과 시 요청하지 않는다.
- 색: 상승 초록(`#059669` 계열, 오르는 단지 화면 emerald 와 같은 계열)·하락 빨강(red 계열). 화살표는 일반 마커만.
- 외부 노출 필드 snake_case, TS `any` 금지, 컴포넌트에서 API 직접 호출 금지(훅).
- raw SQL `%s`/`%(name)s` 바인딩, 문자열 결합에 사용자 입력 금지.

## Review Focus

1. **집계 밖 단지만 있는 화면**(비수도권·신축) — 요청은 200·`items: {}`, 마커는 기본 핀 그대로. (Task 1 테스트, Task 2 확인)
2. **어느 면적대와도 겹치지 않는 필터**(예: `max_area=40`) — `items: {}`, 화살표 없음, 오류 없음. (Task 1 테스트)
3. **대표가 아닌 PNU** — 같은 단지(group) 추세를 원래 PNU 키로 받는다. (Task 1 테스트)
4. **추세 API 실패·지연** — 지도·마커·팝업은 정상(추세 블록만 생략). (Task 2 확인)
5. **필터를 빠르게 바꿀 때** — 늦게 온 이전 응답이 새 필터 결과를 덮지 않는다. (Task 2 확인)

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `web/backend/services/rising.py` (수정) | `bands_for_area_filter`, `trend_direction`, `get_map_trends` |
| `web/backend/routers/rising.py` (수정) | `POST /rising/map` 요청 검증 |
| `web/backend/tests/test_core.py` (수정) | 통합 테스트 |
| `web/frontend-next/src/types/rising.ts` (수정) | `TrendDirection`, `MapTrend`, `MapTrendResponse` |
| `web/frontend-next/src/hooks/useMapTrends.ts` (신규) | 지도 단지 집합 → 추세 요약 조회 |
| `web/frontend-next/src/app/_home/Map/markers/createTrendMarker.ts` (신규) | ▲/▼ 배지 핀 (방향 없으면 기본 핀) |
| `web/frontend-next/src/app/_home/Map/InfoWindowTrend.tsx` (신규) | 팝업 추세 블록 |
| `web/frontend-next/src/app/_home/Map/MapView.tsx`, `InfoWindowBody.tsx`, `app/_home/HomeShell.tsx` (수정) | 연결 |

---

### Task 1: 추세 요약 API

**Files:**
- Modify: `web/backend/services/rising.py`, `web/backend/routers/rising.py`
- Test: `web/backend/tests/test_core.py`

**Interfaces:**
- Consumes: 기존 `AreaBand(code, name, min_area, max_area)`, `load_area_bands(conn)`, 테이블 `apt_band_trend`·`region_band_trend`·`apartments.group_pnu`.
- Produces:
  - `MAP_TREND_MAX_PNUS = 2000`, `FLAT_THRESHOLD_PCT = 2.0`, `THIN_SAMPLE_MAX_TRADES = 2` (services/rising.py 상수)
  - `bands_for_area_filter(bands: dict[str, AreaBand], min_area: float | None, max_area: float | None) -> list[str]`
  - `trend_direction(change_6m_pct: float | None, trade_count_3m: int | None) -> str` (`"up"|"down"|"flat"|"none"`)
  - `get_map_trends(conn, pnus: list[str], min_area: float | None, max_area: float | None) -> dict` → `{"base_ym": int|None, "items": {pnu: MapTrend}}`
  - HTTP `POST /api/rising/map`, 본문 `{"pnus": [str], "min_area": float|null, "max_area": float|null}`
  - `MapTrend` 필드: `area_band, area_band_name, median_price_3m, trade_count_3m, change_6m_pct, change_12m_pct, complex_grade, complex_rank, complex_rank_total, grade_window_months, region_grade, direction`

- [ ] **Step 1: 실패하는 테스트 작성** (`test_core.py` 의 `@test` + requests 스타일, 순수 함수는 직접 import)
  - `trend_direction`: `(2.01, 3) → "up"`, `(-2.01, 3) → "down"`, `(2.0, 3) → "flat"`, `(-2.0, 3) → "flat"`, `(10.0, 2) → "none"`, `(None, 9) → "none"`, `(5.0, None) → "none"`
  - `bands_for_area_filter`(load_area_bands 결과 사용): `(None, None)` → 6개 전부, `(60, 85)` → `["59", "84"]`, `(100, None)` → `["100","125","150","175"]`, `(None, 40)` → `[]`
  - API: `apt_band_trend` 에서 84㎡ 행이 있는 대표 PNU 하나를 골라 `POST {"pnus":[p]}` → 200, `items[p]["area_band"]` 가 그 PNU 의 `trade_count_3m` 최다 면적대, `direction ∈ {up,down,flat,none}`
  - API 필터: 같은 PNU 로 `min_area=60,max_area=85` → `area_band ∈ {"59","84"}`; `max_area=40` → `items == {}`
  - API 비대표 PNU: `apartments` 에서 `group_pnu <> pnu` 이고 group 에 집계 행이 있는 PNU 하나 → 응답 키가 그 비대표 PNU, 값의 `area_band` 가 group 의 것과 같음 (해당 데이터가 없으면 테스트는 skip 메시지 출력)
  - API 경계: `pnus: []` → 200 `items == {}`; 2001개 → 422; 집계 밖 PNU(예 비수도권 하나) → `items` 에 없음
- [ ] **Step 2: 실패 확인** — 백엔드 기동 후 `.venv/bin/python web/backend/tests/test_core.py` → 새 테스트 FAIL(404/ImportError)
- [ ] **Step 3: 구현**
  - `bands_for_area_filter`: 면적대 [bmin, bmax) 와 필터가 겹치면 포함 — `(max_area is None or bmin <= max_area) and (min_area is None or bmax is None or bmax > min_area)`, 순서는 `bands` 순서.
  - `get_map_trends`: pnus 비면 `{"base_ym": _latest_base_ym(conn), "items": {}}`. 선택 면적대 비면 같은 형태. 아니면 요청 PNU → `apartments.group_pnu` → `apt_band_trend` 조인, `area_band = ANY(%(bands)s)`, `DISTINCT ON (요청 pnu) ORDER BY 요청 pnu, trade_count_3m DESC, area_band`, `region_band_trend` LEFT JOIN 으로 `region_grade`. `area_band_name` 은 `bands[code].name`. `direction` 은 `trend_direction`.
  - 라우터: Pydantic 본문 모델(`pnus: list[str]`, `min_area/max_area: float | None`, `ge=0, le=` 면적 상한 상수 1000), `len(pnus) > MAP_TREND_MAX_PNUS` → 422, `min_area > max_area` → 422. `/rising/map` 이 `/rising/{pnu}` 보다 먼저 등록되도록(경로 충돌 방지 — POST 라 충돌은 없지만 순서 유지).
- [ ] **Step 4: 통과 확인** — 같은 명령, 새 테스트 PASS·기존 회귀 없음(알려진 `MCP detail 이미지 첨부` 제외), `ruff format`/`ruff check`
- [ ] **Step 5: 커밋** — `feat(api): 지도용 오르는 단지 추세 요약 API`

### Task 2: 지도 마커 ▲/▼ 배지

**Files:**
- Modify: `web/frontend-next/src/types/rising.ts`, `web/frontend-next/src/app/_home/Map/MapView.tsx`, `web/frontend-next/src/app/_home/HomeShell.tsx`
- Create: `web/frontend-next/src/hooks/useMapTrends.ts`, `web/frontend-next/src/app/_home/Map/markers/createTrendMarker.ts`

**Interfaces:**
- Consumes: Task 1 HTTP 계약.
- Produces:
  - 타입 `TrendDirection = "up" | "down" | "flat" | "none"`, `MapTrend`(Task 1 필드 그대로), `MapTrendResponse = { base_ym: number | null; items: Record<string, MapTrend> }`
  - `useMapTrends(pnus: string[], minArea: number | undefined, maxArea: number | undefined): Record<string, MapTrend>` — `MAP_TREND_MAX_PNUS = 2000` 초과·빈 배열이면 요청 없이 `{}`; PNU 집합(정렬 후 키)·면적이 바뀔 때 디바운스 300ms 후 `api.post("/api/rising/map")`, 이전 요청 abort, 실패 시 `{}` + `console.warn`
  - `createTrendMarker(position: kakao.maps.LatLng, title: string, trend: MapTrend | undefined, onClick: () => void): kakao.maps.Marker` — `direction` 이 up/down 이면 SVG 핀(기본 핀과 같은 크기·앵커) 위에 배지 `▲3.2%`/`▼1.8%`(소수 1자리, 상승 초록·하락 빨강), 아니면 `createBasicMarker` 결과 반환
  - `MapView` 새 prop `trends: Record<string, MapTrend>`

- [ ] **Step 1: 타입·훅 작성** — 훅의 PNU 입력은 HomeShell 이 `apartments ∪ nudgeResults ∪ chatHighlights` 의 pnu 를 합쳐(중복 제거) 넘긴다. 면적은 store `filters.min_area`/`filters.max_area`.
- [ ] **Step 2: `createTrendMarker`** — 배지 문자열은 `app/rising/format.ts` 의 `formatChange` 를 쓰지 않고(부호 대신 화살표) 절댓값 소수 1자리.
- [ ] **Step 3: `MapView` 연결** — 일반 마커 effect 에서 `createBasicMarker` 대신 `createTrendMarker(…, trends[apt.pnu], …)`; effect 의존성에 `trends` 추가(순위·챗 마커는 그대로).
- [ ] **Step 4: 확인** — `cd web/frontend-next && npm run lint && npm run build` 통과. 로컬 백엔드+`npm run dev` 로 수도권 레벨 4 확대 시 배지 표시, FilterPanel 면적 변경 시 배지 갱신, 비수도권은 기본 핀, 백엔드를 끈 상태에서 지도·마커 정상(Review Focus 4), 면적 필터를 연속 변경해 마지막 필터 기준 배지인지(Review Focus 5). 서울 도심 레벨 4 화면 단지 수를 콘솔로 실측해 `MAP_TREND_MAX_PNUS` 가 충분한지 보고서에 기록.
- [ ] **Step 5: 커밋** — `feat(web): 지도 마커 상승·하락 배지`

### Task 3: 팝업 추세 블록

**Files:**
- Create: `web/frontend-next/src/app/_home/Map/InfoWindowTrend.tsx`
- Modify: `web/frontend-next/src/app/_home/Map/InfoWindowBody.tsx`, `web/frontend-next/src/app/_home/Map/MapView.tsx`

**Interfaces:**
- Consumes: `MapTrend`, `MapView` 의 `trends`, `app/rising/format.ts`(`formatEok`, `formatChange`, `isThinSample`, `THIN_SAMPLE_TEXT`), `app/rising/GradeBadge.tsx`(`GradeBadge`).
- Produces: `InfoWindowTrend({ trend }: { trend: MapTrend })`; `InfoWindowBody` 에 선택 prop `trend?: MapTrend`.

- [ ] **Step 1: `InfoWindowTrend`** — 순서: 면적대명 · 3개월 중위가격(`formatEok`)·`N건`(표본 적음이면 `THIN_SAMPLE_TEXT`) · 6개월 변화 / 12개월 변화(`formatChange`, null 이면 "비교 부족") · 지역 가격 등급(`GradeBadge`) · 지역 내 단지 등급(grade_window_months 12 → "12개월 참고", null → "등급 없음") · 링크 "오르는 단지에서 보기 →" (`next/link`, href `/rising`). 팝업 최소 폭 기존(180px) 유지, 블록은 버튼 위.
- [ ] **Step 2: 연결** — `MapView.showInfo` 가 `trends[apt.pnu]` 를 `InfoWindowBody` 에 넘기고, `InfoWindowBody` 는 `trend` 가 있을 때만 블록 렌더. 일반·순위·챗 마커 모두 같은 `showInfo` 경로.
- [ ] **Step 3: 확인** — lint·build 통과, 브라우저에서 일반·추천(넛지 실행 후)·챗 마커 팝업 모두 블록 표시, 집계 밖 단지는 블록 없음, 링크 이동.
- [ ] **Step 4: 커밋** — `feat(web): 지도 팝업 가격 추세 요약`
