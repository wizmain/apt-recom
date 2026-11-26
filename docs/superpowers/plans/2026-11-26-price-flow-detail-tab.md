# 가격흐름 — 상세 팝업 새 탭 + 상단 바로가기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단지 상세 팝업에 "가격흐름" 탭(면적대별 중위가격·변화·등급·차트)을 만들고, 홈 상단에 `/rising` 바로가기 "가격흐름"을 추가하며, 사용자에게 보이는 "오르는 단지" 이름을 "가격흐름"으로 바꾼다.

**Architecture:** 백엔드는 단지 요약 API `GET /api/rising/complex/{pnu}` 하나를 새로 만든다(대표 PNU 변환 + 전 면적대 요약 + 첫 면적대는 지도 API 규칙 재사용). 프론트는 새 훅으로 요약을 받고, 면적대 상세는 기존 `useRisingDetail` 과 `/rising` 드로어 구성 요소를 그대로 쓴다.

**Tech Stack:** FastAPI + psycopg2 raw SQL, Next.js 16 (frontend-next) + React 19 + Tailwind 4, axios `api`.

**Spec:** `docs/superpowers/specs/2026-11-26-price-flow-detail-tab-design.md`

## Global Constraints

- 사용자에게 보이는 이름은 **"가격흐름"**. 내부 식별자·URL·파일명·주석의 `rising`/"오르는 단지"는 바꾸지 않는다.
- 탭 순서: `기본정보 · 가격분석 · 가격흐름 · 관리비 · 주변시설 · 학군 · 안전 · 인구`.
- 첫 면적대 = 지도 API(`get_map_trends`, 필터 없음)의 `area_band` — 규칙을 새로 쓰지 않는다.
- 문구(그대로 사용):
  - 안내: `가격분석 탭은 면적별 평균, 여기는 면적대 중위가격(직거래·이상 거래 제외) 기준입니다.`
  - 집계 없음: `이 단지는 가격흐름 집계 대상이 아닙니다 (수도권 · 최근 실거래 기준).`
  - 집계 전: `집계 준비 중입니다.`
  - 비교 링크: `가격흐름에서 다른 단지와 비교 →` (`/rising`)
  - 면적대 상세 404: `이 면적대 거래 없음`
  - 지도 팝업 링크: `가격흐름에서 보기 →`
- 바로가기 계측: `logEvent('price_flow_shortcut_click', { view_mode })`.
- Python: `%s` 바인딩, ruff format/check. TS: `any` 금지, useEffect 안 직접 API 호출 금지(훅 사용).
- 커밋 메시지에 AI 작업자 표기 금지. main 직접 push 금지 — 브랜치 `feature/price-flow-tab`.
- 작성자 판단(스펙 보완): 탭 내용은 다른 탭과 같이 **탭을 떠나면 언마운트** — 돌아오면 다시 조회하고 첫 면적대로 시작한다(팝업 닫을 때 초기화보다 단순, 기존 탭 동작과 같음).

## Review Focus

1. **상세 팝업에서 다른 단지로 바뀜** — 이전 단지에서 고른 면적대가 새 단지에 없으면 새 단지의 첫 면적대를 보여야 한다(404 문구가 아니라). → Task 2 Step 3 의 파생 선택 규칙 + Task 4 확인.
2. **칩을 빠르게 바꿈** — 늦게 온 이전 면적대 응답이 현재 칩 화면을 덮으면 안 된다(`useRisingDetail` requestKey 로 막힘을 Task 4 에서 확인).
3. **비대표 PNU 로 연 상세** — 대표 단지 집계가 보여야 한다. → Task 1 테스트.
4. **집계 전(`base_ym` null)·비수도권 단지** — 오류가 아니라 안내 문구. → Task 1 테스트(빈 bands) + Task 2 분기.
5. **360px 폭 상단 바** — 바로가기 추가로 넘치거나 다른 버튼을 가리면 안 된다. 넘치면 숨기지 말고 사용자에게 보고. → Task 4.

---

### Task 1: 단지 요약 API `GET /api/rising/complex/{pnu}`

**Files:**
- Modify: `web/backend/services/rising.py` (`get_meta` 의 지역 행 조립 추출, 신규 `get_complex_summary`)
- Modify: `web/backend/routers/rising.py` (라우트 추가 — `/rising/{pnu}` 보다 위)
- Test: `web/backend/tests/test_core.py` (지도 추세 테스트 뒤, "실행" 구역 앞)

**Interfaces:**
- Produces:
  - `_to_region(row: dict, sgg_names: dict[str, str]) -> dict` — `region_band_trend` 행(sigungu_code, median_price_3m, trade_count_3m, change_6m_pct, change_12m_pct, region_grade, region_rank, region_rank_total) → `RisingRegion` 모양(+`sigungu_name`, `sido_code`). `get_meta` 도 이것을 쓴다.
  - `get_complex_summary(conn, pnu: str) -> dict | None` — 요청 PNU 가 `apartments` 에 없으면 `None`.
  - 응답 `{ base_ym: int|None, pnu: <대표 PNU>, name: str, address: str|None, default_band: str|None, bands: [{ area_band, area_band_name, item: RisingItem, region: RisingRegion|None }] }`, `bands` 는 `load_area_bands` 순서.
  - 라우트 `GET /api/rising/complex/{pnu}` — `None` 이면 404 `"단지를 찾을 수 없습니다"`.

- [ ] **Step 0: 브랜치 + 문서 커밋**

```bash
git switch -c feature/price-flow-tab
git add docs/superpowers/specs/2026-11-26-price-flow-detail-tab-design.md docs/superpowers/plans/2026-11-26-price-flow-detail-tab.md
git commit -m "docs: 가격흐름 상세 탭·바로가기 설계·구현 계획"
```
(`docs/adr/README.md` 의 미커밋 변경은 사용자 것 — 스테이징하지 않는다.)

- [ ] **Step 1: 실패하는 테스트 작성** — `RISING_COMPLEX_API = f"{RISING_API}/complex"`

```python
@test("가격흐름 요약: 면적대 정의 순서, 첫 면적대 = 지도 API, 지표·지역 포함")
def test_rising_complex_summary():
    # conn 으로 _top_band_pnu(conn) → pnu; order = list(load_area_bands(conn))
    resp = requests.get(f"{RISING_COMPLEX_API}/{pnu}")
    assert resp.status_code == 200, resp.text          # /rising/{pnu} 에 가로채이면 422
    data = resp.json()
    codes = [b["area_band"] for b in data["bands"]]
    assert codes == sorted(codes, key=order.index), codes
    map_item = requests.post(RISING_MAP_API, json={"pnus": [pnu]}).json()["items"][pnu]
    assert data["default_band"] == map_item["area_band"], (data["default_band"], map_item)
    assert data["pnu"] == pnu and data["base_ym"] is not None
    for band in data["bands"]:
        assert band["item"]["median_price_3m"] is not None or band["item"]["trade_count_3m"] is not None
        assert band["area_band_name"].endswith("㎡급"), band
        if band["region"] is not None:
            assert {"sigungu_name", "sido_code", "region_rank", "region_rank_total"} <= band["region"].keys()

@test("가격흐름 요약: 비대표 PNU 는 대표 단지 요약을 받는다")
def test_rising_complex_group_member():
    # test_rising_map_group_member 와 같은 쿼리로 (pnu, group_pnu); 없으면 skip 출력
    member = requests.get(f"{RISING_COMPLEX_API}/{row['pnu']}").json()
    rep = requests.get(f"{RISING_COMPLEX_API}/{row['group_pnu']}").json()
    assert member["pnu"] == row["group_pnu"] and member == rep, (member, rep)

@test("가격흐름 요약: 집계 없는 단지는 빈 목록, 없는 PNU 는 404")
def test_rising_complex_empty_and_missing():
    # apartments 에 있으나 COALESCE(group_pnu, pnu) 의 apt_band_trend 행이 없는 PNU 1건
    data = requests.get(f"{RISING_COMPLEX_API}/{empty_pnu}").json()
    assert data["bands"] == [] and data["default_band"] is None, data
    resp = requests.get(f"{RISING_COMPLEX_API}/0000000000000000000")
    assert resp.status_code == 404, resp.status_code
```

- [ ] **Step 2: 실패 확인** (로컬 백엔드 `:8000` 이 `--reload` 로 떠 있어야 한다 — CLAUDE.md 실행 정책)

Run: `.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -A2 "가격흐름 요약"`
Expected: 세 테스트 FAIL (첫 테스트는 422 — `/rising/{pnu}` 가 `complex` 를 pnu 로 받음)

- [ ] **Step 3: `_to_region` 추출 + `get_meta` 가 사용하도록 수정** — 반환 모양 변화 없음(meta 기존 테스트가 회귀를 잡는다).

- [ ] **Step 4: `get_complex_summary(conn, pnu)` 구현** — 순서:
  1. `SELECT COALESCE(group_pnu, pnu) AS rep_pnu FROM apartments WHERE pnu = %s` — 없으면 `None`.
  2. 대표 단지 이름·주소: `SELECT a.display_name AS name, {_ADDRESS_SQL} AS address FROM apartments a WHERE a.pnu = %s`.
  3. 면적대 행: `SELECT {_ITEM_COLUMNS_SQL}, t.area_band {_ITEM_FROM_SQL} WHERE t.pnu = %s`, `load_area_bands` 순서로 정렬, `area_band_name` 은 `AreaBand.name`.
  4. 지역 행: 첫 행의 `sigungu_code` 로 `region_band_trend WHERE sigungu_code = %s AND area_band = ANY(%s)` 한 번 조회 → `_to_region` → 면적대별 매칭(없으면 `None`). `sgg_names` 는 `_sigungu_names(conn)`.
  5. `default_band = get_map_trends(conn, [pnu], None, None)["items"].get(pnu, {}).get("area_band")`.
  6. `base_ym = _latest_base_ym(conn)`.

- [ ] **Step 5: 라우트 추가** — `routers/rising.py` 에서 `@router.get("/rising/{pnu}")` **위**에 `@router.get("/rising/complex/{pnu}")`.

- [ ] **Step 6: 통과 확인**

Run: `.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -E "가격흐름 요약|오르는 단지|지도 추세"`
Expected: 가격흐름 요약 3건·오르는 단지·지도 추세 전부 PASS (비대표 PNU 는 skip 가능)

- [ ] **Step 7: 포맷 + 커밋**

```bash
ruff format web/backend/services/rising.py web/backend/routers/rising.py web/backend/tests/test_core.py
ruff check --fix web/backend/services/rising.py web/backend/routers/rising.py web/backend/tests/test_core.py
git add web/backend/services/rising.py web/backend/routers/rising.py web/backend/tests/test_core.py
git commit -m "feat(api): 가격흐름 단지 요약 API — 대표 단지 전 면적대 + 지도 기준 첫 면적대"
```

---

### Task 2: 상세 팝업 "가격흐름" 탭

**Files:**
- Modify: `web/frontend-next/src/types/rising.ts`
- Create: `web/frontend-next/src/hooks/useRisingComplex.ts`
- Create: `web/frontend-next/src/app/_home/PriceFlowTab.tsx`
- Modify: `web/frontend-next/src/app/_home/DetailModalClient.tsx:143` (`TABS`), `:274` 근처(렌더 분기 한 줄)

**Interfaces:**
- Consumes: Task 1 응답; 기존 `useRisingDetail(pnu: string | null, areaBand: string)`, `DetailMetrics({ item, region })`, `BandPriceChart({ monthly })`, `MonthlyTable({ monthly })`, `RecentTradesTable({ trades })` (모두 `app/rising/`).
- Produces:
  - 타입 `RisingComplexBand { area_band: string; area_band_name: string; item: RisingItem; region: RisingRegion | null }`, `RisingComplexSummary { base_ym: number | null; pnu: string; name: string; address: string | null; default_band: string | null; bands: RisingComplexBand[] }`.
  - `useRisingComplex(pnu: string): { summary: RisingComplexSummary | null; loading: boolean; error: string | null }` — `useRisingDetail` 과 같은 requestKey·AbortController 패턴, 오류 문구 `"가격흐름 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."`.
  - `export default function PriceFlowTab({ pnu }: { pnu: string })`.

- [ ] **Step 1: 타입 추가** (`types/rising.ts`, 기존 `RisingDetail` 근처)

- [ ] **Step 2: `useRisingComplex` 작성** — `GET /api/rising/complex/{encodeURIComponent(pnu)}`.

- [ ] **Step 3: `PriceFlowTab` 작성** — 분기 순서: loading → error → `base_ym === null`(집계 전 문구) → `bands.length === 0`(집계 없음 문구 + 비교 링크) → 본문.
  본문 위→아래: 안내 문구 · 면적대 칩(파일 안 작은 컴포넌트, `RisingFilterBar` 의 `segmentClass` 와 같은 모양) · `DetailMetrics` · `BandPriceChart` · `MonthlyTable` · `RecentTradesTable` · 비교 링크.
  선택 면적대는 **파생**으로 정한다(Review Focus 1):

```ts
const [picked, setPicked] = useState<string | null>(null);
const bands = summary?.bands ?? [];
const activeBand =
  bands.find((b) => b.area_band === picked) ??
  bands.find((b) => b.area_band === summary?.default_band) ??
  bands[0] ?? null;
const { detail, loading: detailLoading, notFound, error: detailError } =
  useRisingDetail(activeBand ? summary!.pnu : null, activeBand?.area_band ?? "");
```
  지표는 `activeBand.item`/`activeBand.region`(요약 값)으로 바로 그리고, 차트·표만 `detail` 을 기다린다.

- [ ] **Step 4: `DetailModalClient` 연결** — `TABS` 에 `'가격흐름'` 을 `'가격분석'` 다음에, 렌더 `{activeTab === '가격흐름' && <PriceFlowTab pnu={pnu} />}` (가격분석 줄 바로 아래). 기존 탭 코드는 건드리지 않는다.

- [ ] **Step 5: 정적 검사**

Run: `cd web/frontend-next && npm run lint && npx tsc --noEmit && npm run build`
Expected: 오류 0, 빌드 성공

- [ ] **Step 6: 커밋**

```bash
git add web/frontend-next/src/types/rising.ts web/frontend-next/src/hooks/useRisingComplex.ts web/frontend-next/src/app/_home/PriceFlowTab.tsx web/frontend-next/src/app/_home/DetailModalClient.tsx
git commit -m "feat(web): 상세 팝업 가격흐름 탭"
```

---

### Task 3: 상단 바로가기 + 이름 바꾸기

**Files:**
- Modify: `web/frontend-next/src/app/_home/NudgeBar.tsx` (`ViewTabs`, 약 131–146행)
- Modify: `web/frontend-next/src/app/rising/page.tsx` (`metadata.title`, `<h1>`)
- Modify: `web/frontend-next/src/app/_home/Map/InfoWindowTrend.tsx:47` (링크 문구)

**Interfaces:**
- Consumes: `logEvent(eventType: string, payload?: Record<string, unknown>)` (`@/lib/logEvent`), `next/link`.
- Produces: 없음(화면 변경만).

- [ ] **Step 1: `ViewTabs` 에 바로가기** — 지도·실거래대시보드 버튼 뒤 같은 그룹 안에 `<Link href="/rising">가격흐름</Link>`. 선택 상태 없음(비선택 버튼과 같은 글자색), 이동 링크 표시는 작게(예: `↗`, `aria-hidden`). `onClick` 에서 `logEvent('price_flow_shortcut_click', { view_mode: viewMode })`. 라벨은 상수 `PRICE_FLOW_LABEL = '가격흐름'`.

- [ ] **Step 2: 이름 바꾸기** — `page.tsx` 의 `title: "가격흐름"`, `<h1>` "가격흐름"(부제·description 은 문장 그대로 두되 "오르는 단지" 단어가 있으면 "가격흐름"으로). `InfoWindowTrend` 링크 `가격흐름에서 보기 →`.

- [ ] **Step 3: 남은 노출 문구 확인**

Run: `grep -rn "오르는 단지" web/frontend-next/src web/frontend-next/public --include='*.tsx' --include='*.txt' | grep -v '//\|/\*\|\* '`
Expected: 출력 없음(주석만 남음)

- [ ] **Step 4: 정적 검사** — Task 2 Step 5 와 같은 명령, 같은 기대.

- [ ] **Step 5: 커밋**

```bash
git add web/frontend-next/src/app/_home/NudgeBar.tsx web/frontend-next/src/app/rising/page.tsx web/frontend-next/src/app/_home/Map/InfoWindowTrend.tsx
git commit -m "feat(web): 상단 가격흐름 바로가기, 오르는 단지 표시명을 가격흐름으로"
```

---

### Task 4: 브라우저 통합 확인

**Files:** 없음(문제 발견 시 해당 Task 파일 수정 후 `fix:` 커밋)

- [ ] **Step 1: 서버 기동** — 백엔드 `cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000`, 프론트 `cd web/frontend-next && npm run dev`.

- [ ] **Step 2: 상세 탭 확인** (각 항목 스크린샷)
  - 수도권 단지(예: Task 1 의 `_top_band_pnu` 단지): 탭 순서, 안내 문구, 칩, 지표, 차트, 표, 링크.
  - 지도 배지 ▲% == 탭 첫 화면 "6개월 변화" (같은 단지).
  - 칩 빠르게 연속 전환 → 마지막 칩의 데이터만 남음(Review Focus 2).
  - 탭 연 상태로 다른 단지 상세로 바뀜 → 새 단지 첫 면적대, 404 문구 없음(Review Focus 1).
  - 비대표 PNU 단지 → 대표 단지 집계 표시.
  - 비수도권 단지 → 집계 없음 문구 + 링크.

- [ ] **Step 3: 상단 바로가기 확인** — 지도·대시보드 모드 모두에서 클릭 → `/rising`, 페이지 제목·h1 "가격흐름", 지도 팝업 링크 문구.

- [ ] **Step 4: 360px·390px 폭** — 상단 바 한 줄 유지, 버튼 겹침·가로 스크롤 없음. 넘치면 **숨기지 말고 멈추고 사용자에게 보고**(Review Focus 5).

- [ ] **Step 5: 전체 백엔드 테스트**

Run: `.venv/bin/python web/backend/tests/test_core.py 2>&1 | tail -5`
Expected: 새 실패 없음(기존 환경성 실패 "MCP detail 이미지 첨부"·부분 sync 후 대시보드 드리프트는 이번 변경과 무관 — 변경 전후 동일한지 비교)
