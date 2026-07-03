# E(마찰 제거) + D(큐레이션 딥링크 갤러리) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 첫 방문 사용자가 헤매지 않고 첫 추천에 도달하도록 — (E) 기존 관문의 마찰 제거 3건 + (D) "지역 × 라이프스타일" 큐레이션 딥링크 갤러리(`/explore`)를 구현한다.

**Architecture:** 프론트엔드(web/frontend-next) 중심. 추천 실행은 기존 `setSelectedNudges` + `selectRegion` → `useNudge` 자동 스코어 파이프라인을 재사용하고, 딥링크 소비는 기존 `useBridgeParams`(#127)를 그대로 쓴다. 프리셋/기본 넛지 정의는 하드코딩 금지 원칙에 따라 `common_code` 테이블(신규 그룹 2개)에 두고 시드 스크립트로 관리한다. 측정은 기존 `POST /api/log/event`(event_type 자유 문자열)로 신규 이벤트만 적재 — 백엔드/DB 스키마 변경 없음.

**Tech Stack:** Next.js 16 (App Router), React 19, zustand, Tailwind CSS 4, Playwright e2e (mock-api), Python(psycopg2) 시드 스크립트.

**Spec:** `docs/prd/2026-07-03-entry-barrier-reduction-proposals.md` §5(D), §6(E)

## Global Constraints

- 커밋은 feature 브랜치 `feature/entry-friction-quickwins` 에만 한다. main 직접 push 금지. push 는 사용자 요청 시에만.
- 커밋 메시지: Conventional Commits, 한국어 제목 허용. **AI 작업자 표기(Co-Authored-By 등) 절대 금지.**
- TypeScript `any` 금지. useEffect 내 직접 API 호출 금지(hooks/스토어 액션 경유).
- 변수/키: snake_case(API/DB), camelCase(TS 변수), 소문자 시작. `_` prefix 금지(외부 노출 값).
- 하드코딩 금지: 프리셋·기본 넛지 세트는 common_code(DB)에서 로드. localStorage 키는 기존 관례 `apt_*` prefix.
- Python 실행은 항상 루트 `.venv` 사용 (`.venv/bin/python`). pip 직접 사용 금지.
- production(Railway) DB 반영 스크립트는 작성만 하고 **실행은 사용자가 직접** 한다 (dry-run 기본).
- e2e 실행: `cd web/frontend-next && npx playwright test` (사전 1회: `npx playwright install chromium`). 프론트 검증: `npm run lint`, `npm run build`.
- 신규 이벤트 타입(모두 이 플랜에서 정의): `nudge_chip_blocked`, `search_coach_shown` 대신 코치는 blocked 이벤트로 대체, `recent_banner_recommend_click`, `explore_view`, `explore_tile_click`, `first_run_hint_shown`. (백엔드는 event_type 자유 문자열 — `web/backend/routers/log.py:24` — 등록 절차 불필요)

## File Structure (전체 지도)

| 구분 | 경로 | 책임 |
|------|------|------|
| Create | `web/frontend-next/src/lib/logEvent.ts` | 클라이언트 행동 이벤트 로깅 (fire-and-forget) |
| Create | `web/frontend-next/src/app/_home/SearchCoach.tsx` | E1: 검색 유도 인라인 코치 (표시 전담) |
| Create | `web/frontend-next/src/app/_home/FirstRunHint.tsx` | E2: 첫 실행 빈 상태 힌트 (1회성 + /explore 링크) |
| Create | `web/frontend-next/src/lib/explorePreset.ts` | D: common_code extra(JSON) → ExplorePreset 파서 |
| Create | `web/frontend-next/src/app/explore/page.tsx` | D: 갤러리 라우트 (서버 fetch + SEO metadata) |
| Create | `web/frontend-next/src/app/explore/PresetTiles.tsx` | D: 타일 그리드 (클라이언트, 클릭/뷰 로깅) |
| Create | `scripts/seed_explore_presets.py` | D/E3: common_code 시드 (explore_preset, recommend_default) |
| Create | `web/frontend-next/e2e/entry-flows.spec.ts` | 이 플랜 전체의 e2e 테스트 |
| Modify | `web/frontend-next/e2e/fixtures.mjs` | 그룹별 codes fixture + dashboard recent fixture |
| Modify | `web/frontend-next/e2e/mock-api.mjs` | `/api/codes/:group` 그룹별 응답, recent/log 라우트 |
| Modify | `web/frontend-next/src/app/_home/NudgeBar.tsx` | E1: alert 제거 → 코치 트리거, D: 둘러보기 링크 |
| Modify | `web/frontend-next/src/app/_home/RecentTradesBanner.tsx` | E3: sgg_cd 수신 + "이 지역 추천" 액션 |
| Modify | `web/frontend-next/src/app/_home/HomeShell.tsx` | E2/E3: FirstRunHint 렌더 + 지역 추천 핸들러 |
| Modify | `web/frontend-next/src/hooks/useCodes.ts` | `CodeItem` 인터페이스 export (파서가 소비) |

데이터 흐름: 타일/배너 클릭 → (딥링크 or store 액션) → `selectedNudges`/`selectedRegion` 변경 → `useNudge` effect → `POST /api/nudge/score` → `nudgeResults` → ResultCards. 신규 배관 없음.

백엔드 변경 없음 — `/api/dashboard/recent` 는 이미 `sgg_cd` 를 반환한다 (`web/backend/routers/dashboard.py:541`).

---

### Task 1: 브랜치 생성 + e2e mock 인프라 (그룹별 codes / recent fixture)

이후 모든 태스크의 e2e 전제조건. 현재 mock 은 모든 `/api/codes/*` 에 빈 배열을 반환해 넛지 칩이 아예 렌더되지 않는다.

**Files:**
- Modify: `web/frontend-next/e2e/fixtures.mjs`
- Modify: `web/frontend-next/e2e/mock-api.mjs`

**Interfaces:**
- Produces: fixtures export `codesByGroup: Record<string, CodeItem[]>` (`nudge` 9종 / `recommend_default` 3종 / `explore_preset` 3행 중 1행은 의도적으로 깨진 extra), `dashboardRecent` (sgg_cd 포함 1건). 이후 태스크의 e2e 는 이 fixture 값(칩 라벨 "가성비", 지역명 "서울 종로구", 타일 제목 "강남구 · 학군과 안전")에 의존한다.

- [ ] **Step 1: 브랜치 생성**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
git checkout -b feature/entry-friction-quickwins
```

- [ ] **Step 2: fixtures.mjs 에 그룹별 codes + recent fixture 추가**

`export const codes = [];` (61행) 를 삭제하고 아래로 대체:

```js
/**
 * common_code 그룹별 fixture — mock-api 가 `/api/codes/:group` 을 그룹별로 응답.
 * nudge 코드/이름은 실 DB(common_code group='nudge')와 동일 체계.
 */
export const nudgeCodes = [
  { code: "cost", name: "가성비", extra: "", sort_order: 1 },
  { code: "commute", name: "출퇴근", extra: "", sort_order: 2 },
  { code: "education", name: "학군", extra: "", sort_order: 3 },
  { code: "newlywed", name: "신혼", extra: "", sort_order: 4 },
  { code: "pet", name: "반려동물", extra: "", sort_order: 5 },
  { code: "senior", name: "시니어", extra: "", sort_order: 6 },
  { code: "investment", name: "투자", extra: "", sort_order: 7 },
  { code: "nature", name: "자연", extra: "", sort_order: 8 },
  { code: "safety", name: "안전", extra: "", sort_order: 9 },
];

/** 배너 "이 지역 추천"이 쓰는 기본 넛지 세트 (실 DB 는 seed_explore_presets.py 가 시드). */
export const recommendDefaultCodes = [
  { code: "cost", name: "가성비", extra: "", sort_order: 1 },
  { code: "commute", name: "출퇴근", extra: "", sort_order: 2 },
  { code: "education", name: "학군", extra: "", sort_order: 3 },
];

/** /explore 갤러리 프리셋. broken_preset 은 파서가 건너뛰어야 할 깨진 행(고의). */
export const explorePresetCodes = [
  {
    code: "gangnam_edu",
    name: "강남구 · 학군과 안전",
    extra: JSON.stringify({
      emoji: "🏫",
      description: "학군과 치안을 모두 잡는 강남 라이프",
      nudges: ["education", "safety"],
      sigungu_code: "11680",
      region_label: "강남구",
    }),
    sort_order: 1,
  },
  {
    code: "mapo_value",
    name: "마포구 · 출퇴근과 가성비",
    extra: JSON.stringify({
      emoji: "🚇",
      description: "도심 접근성과 합리적인 가격",
      nudges: ["commute", "cost"],
      sigungu_code: "11440",
      region_label: "마포구",
    }),
    sort_order: 2,
  },
  { code: "broken_preset", name: "깨진 프리셋", extra: "not-json", sort_order: 99 },
];

export const codesByGroup = {
  nudge: nudgeCodes,
  recommend_default: recommendDefaultCodes,
  explore_preset: explorePresetCodes,
};

/** `/api/dashboard/recent` — RecentTradesBanner 렌더 + E3 "이 지역 추천" 검증용. */
export const dashboardRecent = [
  {
    apt_nm: FIXTURE_APT_NAME,
    sgg_cd: "11110",
    sigungu: "서울 종로구",
    area: 84.9,
    floor: 10,
    date: "2026.07.01",
    price: 120000,
    pnu: FIXTURE_PNU,
    lat: 37.5665,
    lng: 126.978,
    bld_nm: FIXTURE_APT_NAME,
  },
];
```

- [ ] **Step 3: mock-api.mjs 라우팅 갱신**

import 변경 (`codes` → `codesByGroup, dashboardRecent`):

```js
import {
  apartments,
  apartmentDetail,
  tradesResponse,
  dashboardTrades,
  nudgeWeights,
  codesByGroup,
  dashboardRecent,
  chatFeedbackStats,
} from "./fixtures.mjs";
```

`resolveBody` 의 exact 라우트에서 `"/api/dashboard/recent": []` 를 `dashboardRecent` 로 교체하고, `/api/log/event` 를 추가:

```js
    "/api/dashboard/recent": dashboardRecent,
    "/api/log/event": { ok: true },
```

codes 패턴 라우트(56행 `if (/^\/api\/codes(\/[^/]+)?$/.test(pathname)) return codes;`)를 그룹별 응답으로 교체:

```js
  // 공통코드 — 그룹별 fixture, 미정의 그룹은 빈 배열
  const codesMatch = pathname.match(/^\/api\/codes(?:\/([^/]+))?$/);
  if (codesMatch) {
    const group = codesMatch[1];
    if (!group) {
      return Object.entries(codesByGroup).map(([group_id, items]) => ({
        group_id,
        cnt: items.length,
      }));
    }
    return codesByGroup[group] ?? [];
  }
```

- [ ] **Step 4: 기존 스모크 회귀 확인**

```bash
cd web/frontend-next && npx playwright test e2e/smoke.spec.ts
```
Expected: 6 passed (칩·배너가 새로 렌더되어도 기존 어서션은 영향 없음)

- [ ] **Step 5: Commit**

```bash
git add web/frontend-next/e2e/fixtures.mjs web/frontend-next/e2e/mock-api.mjs
git commit -m "test(e2e): mock codes 그룹별 응답 + dashboard recent fixture"
```

---

### Task 2: logEvent 헬퍼 + E1 — 비활성 칩 alert 제거, 검색 유도 인라인 코치

**Files:**
- Create: `web/frontend-next/src/lib/logEvent.ts`
- Create: `web/frontend-next/src/app/_home/SearchCoach.tsx`
- Modify: `web/frontend-next/src/app/_home/NudgeBar.tsx`
- Test: `web/frontend-next/e2e/entry-flows.spec.ts` (신규)

**Interfaces:**
- Consumes: fixtures 칩 라벨 "가성비" (Task 1)
- Produces: `logEvent(eventType: string, payload?: Record<string, unknown>): void` — Task 3/5/6 이 사용. `SearchCoach({ visible: boolean; onDismiss: () => void })` 컴포넌트.

- [ ] **Step 1: 실패하는 e2e 테스트 작성**

`web/frontend-next/e2e/entry-flows.spec.ts` 생성:

```ts
import { test, expect } from "@playwright/test";

/**
 * 진입 마찰 제거(E) + 큐레이션 갤러리(D) 플로우 검증.
 * 데이터는 e2e/mock-api.mjs 캔드 응답 — 실 백엔드·DB 불필요.
 * 스펙: docs/prd/2026-07-03-entry-barrier-reduction-proposals.md §5-6
 */

const COACH_TEXT = "지역을 먼저 검색하면 라이프스타일 추천이 켜져요";

test.describe("E1: 비활성 넛지 칩 → 인라인 코치", () => {
  test("alert 없이 코치 노출 + nudge_chip_blocked 로깅", async ({ page }) => {
    let dialogAppeared = false;
    page.on("dialog", async (d) => {
      dialogAppeared = true;
      await d.dismiss();
    });

    await page.goto("/");
    const logReq = page.waitForRequest(
      (r) => r.url().includes("/api/log/event") && r.method() === "POST",
    );
    await page.getByRole("button", { name: "가성비" }).filter({ visible: true }).first().click();

    await expect(page.getByText(COACH_TEXT)).toBeVisible();
    expect(dialogAppeared).toBe(false);
    const req = await logReq;
    expect(req.postDataJSON()).toMatchObject({
      event_type: "nudge_chip_blocked",
      payload: { nudge_id: "cost" },
    });
  });

  test("코치 ✕ 로 닫기", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "가성비" }).filter({ visible: true }).first().click();
    await expect(page.getByText(COACH_TEXT)).toBeVisible();
    await page.getByRole("button", { name: "안내 닫기" }).click();
    await expect(page.getByText(COACH_TEXT)).toBeHidden();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts
```
Expected: FAIL — alert 다이얼로그 발생(`dialogAppeared` true) 및 코치 텍스트 미존재

- [ ] **Step 3: logEvent 헬퍼 구현**

`web/frontend-next/src/lib/logEvent.ts` 생성:

```ts
// src/lib/logEvent.ts
import { api } from "@/lib/api";

/**
 * 클라이언트 행동 이벤트 로깅 (fire-and-forget).
 *
 * 백엔드 POST /api/log/event 로 전송 (web/backend/routers/log.py).
 * X-Device-Id 는 api interceptor 가 자동 주입하며, opt-out 사용자는
 * 서버가 no-op 처리한다. 로깅 실패가 UX 를 막으면 안 되므로 오류는
 * 조용히 무시한다.
 */
export function logEvent(
  eventType: string,
  payload?: Record<string, unknown>,
): void {
  void api
    .post("/api/log/event", { event_type: eventType, payload: payload ?? null })
    .catch(() => {
      // 로깅 실패는 무시 — 측정은 best-effort, 사용자 경험에 영향 없음
    });
}
```

- [ ] **Step 4: SearchCoach 컴포넌트 구현**

`web/frontend-next/src/app/_home/SearchCoach.tsx` 생성:

```tsx
"use client";

interface SearchCoachProps {
  visible: boolean;
  onDismiss: () => void;
}

/**
 * 검색 유도 인라인 코치 (E1).
 *
 * 비활성 nudge 칩을 눌렀을 때 기존 alert() 대신 검색창 아래에 노출되어
 * "지역을 먼저 고르면 추천이 켜진다"는 다음 행동을 안내한다.
 * 표시/숨김 판단은 부모(NudgeBar)가 소유 — 지역/키워드가 생기면 내려간다.
 */
export default function SearchCoach({ visible, onDismiss }: SearchCoachProps) {
  if (!visible) return null;

  return (
    <div
      role="status"
      className="absolute top-full left-0 mt-2 z-50 flex items-center gap-2
                 bg-blue-600 text-white text-xs rounded-lg shadow-lg px-3 py-2
                 whitespace-nowrap animate-fade-in"
    >
      <span aria-hidden>💡</span>
      <span>지역을 먼저 검색하면 라이프스타일 추천이 켜져요</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="안내 닫기"
        className="ml-1 text-white/80 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
```

- [ ] **Step 5: NudgeBar 수정 — alert 제거, 코치 상태 소유**

`web/frontend-next/src/app/_home/NudgeBar.tsx` 수정 5곳:

(a) import 추가 (3-8행 부근):

```tsx
import { logEvent } from '@/lib/logEvent';
import SearchCoach from './SearchCoach';
```

(b) `NudgeBar` 본문 — `hasAnyKeyword` 선언(34행) 아래에 코치 상태 추가:

```tsx
  // E1: 비활성 칩 클릭 → 검색 유도 코치. 지역/키워드가 생기면 자동 종료.
  const [showSearchCoach, setShowSearchCoach] = useState(false);
  useEffect(() => {
    if (hasAnyKeyword) setShowSearchCoach(false);
  }, [hasAnyKeyword]);

  const handleDisabledChipClick = (nudgeId: string) => {
    logEvent('nudge_chip_blocked', { nudge_id: nudgeId });
    setShowSearchCoach(true);
  };
```

(c) `MapControls` 호출부(60-70행)에 3개 prop 추가:

```tsx
          <MapControls
            selectedNudges={selectedNudges}
            onToggleNudge={toggleNudge}
            onOpenSettings={onOpenSettings}
            onOpenFilter={onOpenFilter}
            filterCount={filterCount}
            hasAnyKeyword={hasAnyKeyword}
            onAddKeyword={addKeyword}
            onSelectRegion={selectRegion}
            onSelectApartment={handleSelectApartment}
            onDisabledChipClick={handleDisabledChipClick}
            coachVisible={showSearchCoach}
            onCoachDismiss={() => setShowSearchCoach(false)}
          />
```

`MobileNudgeChips` 호출부(80-84행)에 1개 prop 추가:

```tsx
          <MobileNudgeChips
            selectedNudges={selectedNudges}
            onToggleNudge={toggleNudge}
            hasAnyKeyword={hasAnyKeyword}
            onDisabledChipClick={handleDisabledChipClick}
          />
```

(d) `MapControls` — 시그니처에 3개 prop 추가, 검색 input 하이라이트, 코치 렌더:

시그니처 (137-147행):

```tsx
function MapControls({
  selectedNudges, onToggleNudge, onOpenSettings, onOpenFilter, filterCount,
  hasAnyKeyword, onAddKeyword, onSelectRegion, onSelectApartment,
  onDisabledChipClick, coachVisible, onCoachDismiss,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void;
  onOpenSettings: () => void; onOpenFilter: () => void; filterCount: number;
  hasAnyKeyword: boolean;
  onAddKeyword: (kw: string, label?: string) => void;
  onSelectRegion: (region: SelectedRegion) => void;
  onSelectApartment?: (pnu: string, lat: number, lng: number, name: string) => void;
  onDisabledChipClick: (nudgeId: string) => void;
  coachVisible: boolean;
  onCoachDismiss: () => void;
}) {
```

검색 input(305-315행)의 className 을 코치 상태에 따라 강조 — 기존 입력 태그를 다음으로 교체:

```tsx
        <input
          type="text"
          value={inputValue}
          onChange={(e) => { setInputValue(e.target.value); resetDropdown(); }}
          onKeyDown={handleKeyDown}
          placeholder="지역명·단지명 (Enter)"
          className={`w-full sm:w-48 px-3 py-1.5 pr-7 text-sm bg-blue-50/70 border-2 rounded-full
                     hover:border-blue-400 hover:bg-blue-50
                     focus:outline-none focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200
                     placeholder-blue-400/70 transition-colors
                     ${coachVisible ? 'border-blue-500 ring-2 ring-blue-300' : 'border-blue-300'}`}
        />
```

같은 relative 컨테이너 안, `<span ...>🔍</span>` 바로 아래에 코치 렌더:

```tsx
        <SearchCoach visible={coachVisible} onDismiss={onCoachDismiss} />
```

넛지 칩 목록(371-382행)의 `NudgeChip` 에 prop 전달:

```tsx
          <NudgeChip
            key={nudge.id}
            nudge={nudge}
            isSelected={selectedNudges.includes(nudge.id)}
            disabled={!hasAnyKeyword}
            onToggle={onToggleNudge}
            onDisabledClick={onDisabledChipClick}
            size="desktop"
          />
```

(e) `MobileNudgeChips` — prop 추가 + 전달:

```tsx
function MobileNudgeChips({
  selectedNudges, onToggleNudge, hasAnyKeyword, onDisabledChipClick,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void; hasAnyKeyword: boolean;
  onDisabledChipClick: (nudgeId: string) => void;
}) {
  const { codes: nudgeCodes } = useCodes('nudge');
  const nudges = nudgeCodes.map(c => ({ id: c.code, label: c.name }));

  return (
    <div className="flex sm:hidden items-center gap-1.5 px-3 pb-2 overflow-x-auto scrollbar-hide">
      {nudges.map(nudge => (
        <NudgeChip
          key={nudge.id}
          nudge={nudge}
          isSelected={selectedNudges.includes(nudge.id)}
          disabled={!hasAnyKeyword}
          onToggle={onToggleNudge}
          onDisabledClick={onDisabledChipClick}
          size="mobile"
        />
      ))}
    </div>
  );
}
```

`NudgeChip` — alert 제거, 콜백으로 교체 (434-458행):

```tsx
function NudgeChip({
  nudge, isSelected, disabled, onToggle, onDisabledClick, size,
}: {
  nudge: { id: string; label: string }; isSelected: boolean; disabled: boolean;
  onToggle: (id: string) => void; onDisabledClick: (id: string) => void;
  size: 'desktop' | 'mobile';
}) {
  const sizeClass = size === 'desktop' ? 'px-3 py-1.5 text-sm' : 'px-2.5 py-1 text-xs';
  return (
    <button
      onClick={() => {
        // 비활성 상태 클릭 = 진입 실패 신호 — alert 대신 검색 코치로 유도 (E1)
        if (disabled) { onDisabledClick(nudge.id); return; }
        onToggle(nudge.id);
      }}
      className={`${sizeClass} rounded-full font-medium whitespace-nowrap transition-all duration-200 border
        ${disabled
          ? 'bg-gray-50 text-gray-300 border-gray-200 cursor-not-allowed'
          : isSelected
            ? 'bg-blue-600 text-white border-blue-600 shadow-sm cursor-pointer'
            : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600 cursor-pointer'
        }`}
    >
      {nudge.label}
    </button>
  );
}
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts e2e/smoke.spec.ts
```
Expected: 전체 PASS (E1 신규 2건 + 스모크 6건)

- [ ] **Step 7: Commit**

```bash
git add web/frontend-next/src/lib/logEvent.ts web/frontend-next/src/app/_home/SearchCoach.tsx web/frontend-next/src/app/_home/NudgeBar.tsx web/frontend-next/e2e/entry-flows.spec.ts
git commit -m "feat(web): 비활성 넛지 칩 alert 를 검색 유도 인라인 코치로 교체 (E1)"
```

---

### Task 3: E3 — RecentTradesBanner "이 지역 추천" 액션

데드엔드였던 실거래 배너를 추천 런처로 전환. 백엔드는 이미 `sgg_cd` 를 반환하므로 프론트만 수정.

**Files:**
- Modify: `web/frontend-next/src/app/_home/RecentTradesBanner.tsx`
- Modify: `web/frontend-next/src/app/_home/HomeShell.tsx`
- Test: `web/frontend-next/e2e/entry-flows.spec.ts` (추가)

**Interfaces:**
- Consumes: `logEvent` (Task 2), fixtures `dashboardRecent`(sgg_cd: "11110", sigungu: "서울 종로구") (Task 1)
- Produces: `RecentTradesBanner` 신규 prop `onRecommendRegion?: (sigunguCode: string, sigunguLabel: string) => void`

- [ ] **Step 1: 실패하는 e2e 테스트 추가**

`entry-flows.spec.ts` 에 추가:

```ts
test.describe("E3: 신규거래 배너 → 이 지역 추천", () => {
  test("배너 아이템의 지역 추천 → 지역 태그 + 스코어 호출", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "최근 거래 내역 열기" }).click();

    const scoreReq = page.waitForRequest(
      (r) => r.url().includes("/api/nudge/score") && r.method() === "POST",
    );
    await page.getByRole("button", { name: "서울 종로구 지역 추천 보기" }).click();

    await expect(page.getByText("📍 서울 종로구")).toBeVisible();
    const req = await scoreReq;
    expect(req.postDataJSON()).toMatchObject({
      nudges: ["cost", "commute", "education"],
      sigungu_code: "11110",
    });
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts
```
Expected: E3 테스트 FAIL — "서울 종로구 지역 추천 보기" 버튼 미존재

- [ ] **Step 3: RecentTradesBanner 수정**

(a) `RecentTrade` 인터페이스(6-14행)에 필드 추가:

```ts
interface RecentTrade {
  apt_nm: string;
  sgg_cd?: string;
  sigungu: string;
  area: number | null;
  floor: number | null;
  date: string;
  price?: number;
  pnu?: string;
}
```

(b) `Props`(16-20행)에 콜백 추가:

```ts
interface Props {
  onSelect?: (pnu: string, aptName: string) => void;
  onGoToDashboard?: () => void;
  onRecommendRegion?: (sigunguCode: string, sigunguLabel: string) => void;
  hasResults?: boolean;
}
```

컴포넌트 시그니처(35행):

```tsx
export default function RecentTradesBanner({ onSelect, onGoToDashboard, onRecommendRegion, hasResults }: Props) {
```

(c) 확장 리스트 아이템(120-147행) — `<li>` 를 flex 로 바꾸고 우측에 지역 추천 버튼 추가. HTML 상 button 중첩을 피하기 위해 형제 배치:

```tsx
          <ul className="divide-y divide-gray-100 overflow-y-auto max-h-[21rem]">
            {trades.map((t, i) => (
              <li key={`${t.pnu ?? t.apt_nm}-${i}`} className="flex items-stretch">
                <button
                  type="button"
                  disabled={!t.pnu}
                  onClick={() => {
                    if (t.pnu) {
                      onSelect?.(t.pnu, t.apt_nm);
                      setExpanded(false);
                    }
                  }}
                  className="flex-1 min-w-0 text-left px-4 py-2.5 hover:bg-blue-50 disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-gray-900 truncate">{t.apt_nm}</span>
                    <span className="text-sm font-bold text-blue-700 flex-shrink-0">{formatPrice(t.price)}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-0.5">
                    <span>{t.date}</span>
                    <span>·</span>
                    <span className="truncate">{t.sigungu}</span>
                    {t.area != null && <><span>·</span><span>{Math.round(t.area)}㎡</span></>}
                    {t.floor != null && <><span>·</span><span>{t.floor}층</span></>}
                  </div>
                </button>
                {/* E3: 거래 지역 기반 추천 런처 — sgg_cd 없는 행(구데이터)은 미노출 */}
                {t.sgg_cd && onRecommendRegion ? (
                  <button
                    type="button"
                    onClick={() => {
                      onRecommendRegion(t.sgg_cd!, t.sigungu);
                      setExpanded(false);
                    }}
                    aria-label={`${t.sigungu} 지역 추천 보기`}
                    className="flex-shrink-0 px-2.5 text-[11px] font-medium text-emerald-700
                               border-l border-gray-100 hover:bg-emerald-50 whitespace-nowrap"
                  >
                    이 지역<br />추천
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
```

- [ ] **Step 4: HomeShell 에 핸들러 연결**

(a) import 추가:

```tsx
import { useCodes } from "@/hooks/useCodes";
import { logEvent } from "@/lib/logEvent";
```

(b) store 셀렉터 블록(59-70행)에 2개 추가:

```tsx
  const selectRegion = useAppStore((s) => s.selectRegion);
  const setSelectedNudges = useAppStore((s) => s.setSelectedNudges);
```

(c) side-effect hooks 아래(75행 부근)에 코드 로드 추가:

```tsx
  // E3 "이 지역 추천"용 코드 — nudge(화이트리스트) + recommend_default(기본 세트)
  const { codes: nudgeCodes } = useCodes("nudge");
  const { codes: recommendDefaultCodes } = useCodes("recommend_default");
```

(d) `handleBannerSelect` 아래(108행 부근)에 핸들러 추가:

```tsx
  // RecentTradesBanner "이 지역 추천" — 거래 지역 + 기본 넛지 세트로 즉시 추천 (E3).
  // recommend_default(common_code) 미시드 환경에서는 지역만 세팅된다(칩 활성화까지).
  const handleRecommendRegion = (sigunguCode: string, sigunguLabel: string) => {
    logEvent("recent_banner_recommend_click", { sgg_cd: sigunguCode });
    void selectRegion({ type: "sigungu", code: sigunguCode, label: sigunguLabel });
    if (recommendDefaultCodes.length > 0) {
      const validNudgeCodes =
        nudgeCodes.length > 0 ? nudgeCodes.map((c) => c.code) : undefined;
      setSelectedNudges(
        recommendDefaultCodes.map((c) => c.code),
        validNudgeCodes,
      );
    }
  };
```

(e) `RecentTradesBanner` 렌더(152-156행)에 prop 연결:

```tsx
          <RecentTradesBanner
            onSelect={handleBannerSelect}
            onGoToDashboard={() => switchView("dashboard")}
            onRecommendRegion={handleRecommendRegion}
            hasResults={hasResults}
          />
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts e2e/smoke.spec.ts
```
Expected: 전체 PASS

- [ ] **Step 6: Commit**

```bash
git add web/frontend-next/src/app/_home/RecentTradesBanner.tsx web/frontend-next/src/app/_home/HomeShell.tsx web/frontend-next/e2e/entry-flows.spec.ts
git commit -m "feat(web): 신규거래 배너에 '이 지역 추천' 액션 추가 (E3)"
```

---

### Task 4: 프리셋 데이터 계층 — 시드 스크립트 + extra(JSON) 파서

**Files:**
- Create: `scripts/seed_explore_presets.py`
- Create: `web/frontend-next/src/lib/explorePreset.ts`
- Modify: `web/frontend-next/src/hooks/useCodes.ts` (CodeItem export)

**Interfaces:**
- Consumes: common_code 스키마 `(group_id, code, name, extra, sort_order)` — `web/backend/database.py:533`
- Produces:
  - DB: `common_code` 그룹 `explore_preset`(6행), `recommend_default`(3행: cost/commute/education)
  - `export interface CodeItem { code: string; name: string; extra: string; sort_order: number }` (useCodes.ts)
  - `parseExplorePresets(codes: CodeItem[]): ExplorePreset[]`, `interface ExplorePreset { code; title; emoji; description; nudges: string[]; sigunguCode; regionLabel }` — Task 5 가 소비

- [ ] **Step 1: useCodes 의 CodeItem export**

`web/frontend-next/src/hooks/useCodes.ts` 4행 `interface CodeItem` → `export interface CodeItem` 으로 변경. (다른 변경 없음)

- [ ] **Step 2: 파서 구현**

`web/frontend-next/src/lib/explorePreset.ts` 생성:

```ts
// src/lib/explorePreset.ts
import type { CodeItem } from "@/hooks/useCodes";

export interface ExplorePreset {
  code: string;
  title: string;
  emoji: string;
  description: string;
  nudges: string[];
  sigunguCode: string;
  regionLabel: string;
}

interface ExplorePresetExtra {
  emoji?: string;
  description?: string;
  nudges?: string[];
  sigungu_code?: string;
  region_label?: string;
}

/**
 * common_code(group='explore_preset') 행 → ExplorePreset 목록 (D안).
 *
 * extra 는 JSON 문자열 — 파싱에 실패하거나 필수 필드(nudges/sigungu_code/
 * region_label)가 빠진 행은 경고 후 건너뛴다. 운영 중 잘못 입력된 행 하나가
 * 갤러리 전체를 깨뜨리지 않게 하기 위함이다 (시드는 scripts/seed_explore_presets.py).
 */
export function parseExplorePresets(codes: CodeItem[]): ExplorePreset[] {
  const presets: ExplorePreset[] = [];
  for (const item of codes) {
    try {
      const extra = JSON.parse(item.extra) as ExplorePresetExtra;
      if (!Array.isArray(extra.nudges) || extra.nudges.length === 0) throw new Error("nudges 누락");
      if (!extra.sigungu_code || !extra.region_label) throw new Error("지역 필드 누락");
      presets.push({
        code: item.code,
        title: item.name,
        emoji: extra.emoji ?? "🏙",
        description: extra.description ?? "",
        nudges: extra.nudges,
        sigunguCode: extra.sigungu_code,
        regionLabel: extra.region_label,
      });
    } catch (err) {
      console.warn(`explore_preset 행 건너뜀 (${item.code}):`, err);
    }
  }
  return presets;
}
```

- [ ] **Step 3: 시드 스크립트 구현**

`scripts/seed_explore_presets.py` 생성 (연결/CLI 패턴: `scripts/reflect_imdong_diavill_to_railway.py`, `batch/purge_old_trades.py` 준용):

```python
"""탐색 갤러리(explore_preset)·기본 추천 넛지(recommend_default) common_code 시드.

D안(큐레이션 딥링크 갤러리 /explore)과 E3안(신규거래 배너 → 이 지역 추천)이
소비하는 코드 데이터를 common_code 에 upsert 한다. 하드코딩 금지 원칙에 따라
프리셋 정의는 프론트 코드가 아닌 DB 에 두며, 이 스크립트가 유일한 시드 경로다.

- explore_preset: code=프리셋 id, name=타일 제목,
  extra=JSON {emoji, description, nudges[], sigungu_code, region_label}
- recommend_default: code=nudge 코드 (배너 '이 지역 추천'의 기본 세트)

각 프리셋의 sigungu_code 가 apartments 에 실존하는지 검증하고, 없으면 해당
프리셋을 건너뛰며 경고를 남긴다 (깨진 딥링크 방지).

사용 (기본 dry-run):
  .venv/bin/python scripts/seed_explore_presets.py                     # local dry-run
  .venv/bin/python scripts/seed_explore_presets.py --apply             # local 반영
  .venv/bin/python scripts/seed_explore_presets.py --target railway --apply
    ⚠️ production 쓰기 — CLAUDE.md 정책상 railway 는 사용자가 직접 실행한다.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

GROUP_EXPLORE = "explore_preset"
GROUP_RECOMMEND_DEFAULT = "recommend_default"

# 배너 "이 지역 추천"의 기본 넛지 세트 — 가성비/출퇴근/학군 (범용 균형 조합)
RECOMMEND_DEFAULT_NUDGES = [
    ("cost", "가성비", 1),
    ("commute", "출퇴근", 2),
    ("education", "학군", 3),
]

# /explore 큐레이션 타일 — (code, 제목, extra, sort_order)
EXPLORE_PRESETS = [
    (
        "gangnam_edu",
        "강남구 · 학군과 안전",
        {
            "emoji": "🏫",
            "description": "학군과 치안을 모두 잡는 강남 라이프",
            "nudges": ["education", "safety"],
            "sigungu_code": "11680",
            "region_label": "강남구",
        },
        1,
    ),
    (
        "bundang_commute",
        "성남 분당 · 출퇴근과 신혼",
        {
            "emoji": "🚇",
            "description": "판교 출퇴근과 신혼 라이프의 균형",
            "nudges": ["commute", "newlywed"],
            "sigungu_code": "41135",
            "region_label": "성남시 분당구",
        },
        2,
    ),
    (
        "mapo_value",
        "마포구 · 출퇴근과 가성비",
        {
            "emoji": "☕",
            "description": "도심 접근성과 합리적인 가격",
            "nudges": ["commute", "cost"],
            "sigungu_code": "11440",
            "region_label": "마포구",
        },
        3,
    ),
    (
        "nowon_edu_value",
        "노원구 · 학군과 가성비",
        {
            "emoji": "🎒",
            "description": "교육 인프라와 부담 없는 가격대",
            "nudges": ["education", "cost"],
            "sigungu_code": "11350",
            "region_label": "노원구",
        },
        4,
    ),
    (
        "yeongtong_family",
        "수원 영통 · 학군과 신혼",
        {
            "emoji": "👨‍👩‍👧",
            "description": "젊은 가족이 정착하기 좋은 신도시",
            "nudges": ["education", "newlywed"],
            "sigungu_code": "41117",
            "region_label": "수원시 영통구",
        },
        5,
    ),
    (
        "haeundae_nature",
        "부산 해운대 · 자연과 투자",
        {
            "emoji": "🌊",
            "description": "바다 조망과 투자 가치를 동시에",
            "nudges": ["nature", "investment"],
            "sigungu_code": "26350",
            "region_label": "부산 해운대구",
        },
        6,
    ),
]

UPSERT_SQL = """
    INSERT INTO common_code (group_id, code, name, extra, sort_order)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (group_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        extra = EXCLUDED.extra,
        sort_order = EXCLUDED.sort_order
"""


def get_conn(target: str):
    if target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
        if not url:
            raise SystemExit("RAILWAY_DATABASE_URL 미설정 (.env 확인)")
    else:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL 미설정 (.env 확인)")
    return psycopg2.connect(url)


def sigungu_exists(cur, sigungu_code: str) -> bool:
    cur.execute(
        "SELECT 1 FROM apartments WHERE sigungu_code = %s LIMIT 1", [sigungu_code]
    )
    return cur.fetchone() is not None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    args = parser.parse_args()

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    planned: list[tuple[str, str, str, str, int]] = []

    for code, name, sort_order in RECOMMEND_DEFAULT_NUDGES:
        planned.append((GROUP_RECOMMEND_DEFAULT, code, name, "", sort_order))

    for code, name, extra, sort_order in EXPLORE_PRESETS:
        if not sigungu_exists(cur, extra["sigungu_code"]):
            print(f"⚠️  skip {code}: sigungu_code={extra['sigungu_code']} 가 apartments 에 없음")
            continue
        planned.append(
            (GROUP_EXPLORE, code, name, json.dumps(extra, ensure_ascii=False), sort_order)
        )

    for row in planned:
        print(f"{'APPLY' if args.apply else 'DRY-RUN'} upsert: {row[0]}/{row[1]} — {row[2]}")

    if args.apply:
        for row in planned:
            cur.execute(UPSERT_SQL, list(row))
        conn.commit()
        print(f"✅ {args.target} 반영 완료: {len(planned)}행")
    else:
        conn.rollback()
        print(f"dry-run 종료 ({len(planned)}행 예정) — 반영하려면 --apply")

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: dry-run 으로 검증 실행 (실패 확인 대용 — 데이터 태스크)**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
.venv/bin/python scripts/seed_explore_presets.py
```
Expected: `DRY-RUN upsert: ...` 9행(recommend_default 3 + explore_preset 6) 출력. sigungu_code 가 DB 에 없는 프리셋이 있으면 `⚠️ skip` — skip 발생 시 해당 코드가 실제 5자리 시군구코드인지 확인해 수정한다.

- [ ] **Step 5: 로컬 반영 + 확인**

```bash
.venv/bin/python scripts/seed_explore_presets.py --apply
.venv/bin/python -c "
from web.backend.database import DictConnection
" 2>/dev/null || true
```

확인은 psql 대신 백엔드 API 로 (백엔드 기동 없이 하려면 아래 python one-liner):

```bash
.venv/bin/python - <<'EOF'
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT group_id, code, name FROM common_code WHERE group_id IN ('explore_preset','recommend_default') ORDER BY group_id, sort_order")
for r in cur.fetchall():
    print(r)
conn.close()
EOF
```
Expected: recommend_default 3행 + explore_preset 6행 (skip 없을 시)

- [ ] **Step 6: 린트 + ruff**

```bash
ruff format scripts/seed_explore_presets.py && ruff check scripts/seed_explore_presets.py
cd web/frontend-next && npm run lint
```
Expected: 오류 없음

- [ ] **Step 7: Commit**

```bash
git add scripts/seed_explore_presets.py web/frontend-next/src/lib/explorePreset.ts web/frontend-next/src/hooks/useCodes.ts
git commit -m "feat(explore): 프리셋 시드 스크립트 + common_code extra 파서 (D)"
```

> ⚠️ Railway 반영(`--target railway --apply`)은 배포 시점에 **사용자가 직접** 실행 — Task 7 체크리스트에 포함.

---

### Task 5: /explore 큐레이션 갤러리 페이지 + 홈 진입점

**Files:**
- Create: `web/frontend-next/src/app/explore/page.tsx`
- Create: `web/frontend-next/src/app/explore/PresetTiles.tsx`
- Modify: `web/frontend-next/src/app/_home/NudgeBar.tsx` (둘러보기 링크)
- Test: `web/frontend-next/e2e/entry-flows.spec.ts` (추가)

**Interfaces:**
- Consumes: `parseExplorePresets`, `ExplorePreset`, `CodeItem` (Task 4), `logEvent` (Task 2), `useBridgeParams` 딥링크 규약 `/?nudges=<csv>&sigungu_code=<5자리>&region_label=<라벨>` (기존, `useBridgeParams.ts:30-76`)
- Produces: `/explore` 라우트, `PresetTiles({ presets: ExplorePreset[] })`

- [ ] **Step 1: 실패하는 e2e 테스트 추가**

`entry-flows.spec.ts` 에 추가:

```ts
test.describe("D: /explore 큐레이션 갤러리", () => {
  test("프리셋 타일 렌더 — 깨진 행은 제외", async ({ page }) => {
    const res = await page.goto("/explore");
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "라이프스타일 추천 둘러보기" })).toBeVisible();
    await expect(page.getByText("강남구 · 학군과 안전")).toBeVisible();
    await expect(page.getByText("마포구 · 출퇴근과 가성비")).toBeVisible();
    await expect(page.getByText("깨진 프리셋")).toBeHidden();
  });

  test("타일 클릭 → 홈 딥링크 소비 → 지역 태그 + 스코어 호출", async ({ page }) => {
    await page.goto("/explore");
    const scoreReq = page.waitForRequest(
      (r) => r.url().includes("/api/nudge/score") && r.method() === "POST",
    );
    await page.getByRole("link", { name: /강남구 · 학군과 안전/ }).click();

    await expect(page.getByText("📍 강남구")).toBeVisible();
    const req = await scoreReq;
    expect(req.postDataJSON()).toMatchObject({
      nudges: ["education", "safety"],
      sigungu_code: "11680",
    });
    // 소비 후 쿼리 제거 (useBridgeParams 규약)
    await expect(page).toHaveURL(/\/$/);
  });

  test("홈 상단바에서 둘러보기 진입", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "추천 둘러보기" }).click();
    await expect(page.getByRole("heading", { name: "라이프스타일 추천 둘러보기" })).toBeVisible();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts
```
Expected: D 테스트 3건 FAIL (라우트 404 / 링크 미존재)

- [ ] **Step 3: 갤러리 페이지(서버) 구현**

`web/frontend-next/src/app/explore/page.tsx` 생성:

```tsx
// src/app/explore/page.tsx
import type { Metadata } from "next";
import { API_URL } from "@/lib/site";
import type { CodeItem } from "@/hooks/useCodes";
import { parseExplorePresets, type ExplorePreset } from "@/lib/explorePreset";
import PresetTiles from "./PresetTiles";

export const metadata: Metadata = {
  title: "라이프스타일 추천 둘러보기 | 집토리",
  description:
    "학군·출퇴근·가성비 등 지역 × 라이프스타일 조합을 고르면 바로 아파트 추천을 받아볼 수 있습니다.",
};

// 프리셋은 common_code(explore_preset) 서버 fetch — 1시간 재검증 캐시.
// 각 타일은 홈 딥링크(useBridgeParams 소비)이므로 이 페이지 자체가 SEO/공유 랜딩이 된다.
export const revalidate = 3600;

async function fetchPresets(): Promise<ExplorePreset[]> {
  try {
    const res = await fetch(`${API_URL}/api/codes/explore_preset`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    return parseExplorePresets((await res.json()) as CodeItem[]);
  } catch {
    // 백엔드 불가 시 빈 갤러리 안내 렌더 (빌드/프리렌더 실패 방지)
    return [];
  }
}

export default async function ExplorePage() {
  const presets = await fetchPresets();

  return (
    <main className="min-h-[100dvh] bg-gray-50 px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
          라이프스타일 추천 둘러보기
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          마음에 드는 조합을 고르면 바로 추천 결과를 보여드려요.
        </p>
        <PresetTiles presets={presets} />
      </div>
    </main>
  );
}
```

- [ ] **Step 4: 타일 그리드(클라이언트) 구현**

`web/frontend-next/src/app/explore/PresetTiles.tsx` 생성:

```tsx
// src/app/explore/PresetTiles.tsx
"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import type { ExplorePreset } from "@/lib/explorePreset";
import { logEvent } from "@/lib/logEvent";

interface PresetTilesProps {
  presets: ExplorePreset[];
}

/** 프리셋 → 홈 딥링크 (useBridgeParams 가 1회 소비해 추천 자동 실행). */
function presetHref(p: ExplorePreset): string {
  const params = new URLSearchParams({
    nudges: p.nudges.join(","),
    sigungu_code: p.sigunguCode,
    region_label: p.regionLabel,
  });
  return `/?${params.toString()}`;
}

export default function PresetTiles({ presets }: PresetTilesProps) {
  const viewLoggedRef = useRef(false);

  useEffect(() => {
    if (viewLoggedRef.current) return;
    viewLoggedRef.current = true;
    logEvent("explore_view", { preset_count: presets.length });
  }, [presets.length]);

  if (presets.length === 0) {
    return (
      <div className="mt-8 rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
        아직 준비된 추천 조합이 없습니다.
        <div className="mt-3">
          <Link href="/" className="text-blue-600 hover:underline">
            지도로 직접 찾아보기 →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
      {presets.map((p) => (
        <Link
          key={p.code}
          href={presetHref(p)}
          onClick={() => logEvent("explore_tile_click", { preset: p.code })}
          className="group rounded-2xl border border-gray-200 bg-white p-4 shadow-sm
                     transition-all hover:border-blue-300 hover:shadow-md"
        >
          <div className="flex items-start gap-3">
            <span className="text-2xl" aria-hidden>
              {p.emoji}
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-gray-900 group-hover:text-blue-700">
                {p.title}
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">{p.description}</p>
            </div>
          </div>
          <div className="mt-3 text-right text-xs font-medium text-blue-600">
            추천 보기 →
          </div>
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: NudgeBar 에 둘러보기 진입점 추가**

`NudgeBar.tsx` 의 `GuideLink` 함수 바로 위에 컴포넌트 추가:

```tsx
function ExploreLink() {
  // 상단바 우측: /explore 큐레이션 갤러리 진입점 (D안 홈 진입점).
  return (
    <Link
      href="/explore"
      title="추천 둘러보기"
      aria-label="추천 둘러보기"
      className="inline-flex items-center gap-1 px-2 sm:px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium
                 text-gray-600 border border-gray-300 hover:border-blue-400 hover:text-blue-600
                 transition-all duration-200 whitespace-nowrap cursor-pointer flex-shrink-0"
    >
      <span aria-hidden>✨</span>
      <span className="hidden sm:inline">둘러보기</span>
    </Link>
  );
}
```

`NudgeBar` 본문의 `<GuideLink />`(73행) 앞에 배치하되, `GuideLink` 의 `ml-auto` 가 우측 정렬을 담당하므로 **ExploreLink 로 ml-auto 를 옮긴다**: `GuideLink` 의 className 에서 `ml-auto` 를 제거하고 `ExploreLink` 의 className 맨 앞에 `ml-auto` 추가. 렌더 순서:

```tsx
        <ExploreLink />
        <GuideLink />
        <SiteInfo />
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts e2e/smoke.spec.ts
```
Expected: 전체 PASS

- [ ] **Step 7: Commit**

```bash
git add web/frontend-next/src/app/explore/ web/frontend-next/src/app/_home/NudgeBar.tsx web/frontend-next/e2e/entry-flows.spec.ts
git commit -m "feat(web): /explore 큐레이션 딥링크 갤러리 + 홈 진입점 (D)"
```

---

### Task 6: E2 — 첫 실행 빈 상태 힌트 (FirstRunHint)

**Files:**
- Create: `web/frontend-next/src/app/_home/FirstRunHint.tsx`
- Modify: `web/frontend-next/src/app/_home/HomeShell.tsx`
- Test: `web/frontend-next/e2e/entry-flows.spec.ts` (추가)

**Interfaces:**
- Consumes: `logEvent` (Task 2), `/explore` 라우트 (Task 5)
- Produces: `FirstRunHint({ active: boolean })` — active = "지도 모드 + 검색/추천 이전" 상태. localStorage 키 `apt_first_run_hint_done`.

- [ ] **Step 1: 실패하는 e2e 테스트 추가**

`entry-flows.spec.ts` 에 추가:

```ts
test.describe("E2: 첫 실행 힌트", () => {
  const HINT_TEXT = "지역 검색";

  test("첫 방문 노출 → ✕ 닫기 → 새로고침 후 미노출 (1회성)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("status").filter({ hasText: HINT_TEXT })).toBeVisible();

    await page.getByRole("button", { name: "힌트 닫기" }).click();
    await expect(page.getByRole("status").filter({ hasText: HINT_TEXT })).toBeHidden();

    await page.reload();
    // localStorage 마킹으로 재노출 없음
    await expect(page.getByRole("button", { name: "집토리 열기" })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: HINT_TEXT })).toBeHidden();
  });

  test("힌트의 둘러보기 링크 → /explore", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "추천 조합 둘러보기 →" }).click();
    await expect(page.getByRole("heading", { name: "라이프스타일 추천 둘러보기" })).toBeVisible();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts
```
Expected: E2 테스트 2건 FAIL (힌트 미존재)

- [ ] **Step 3: FirstRunHint 구현**

`web/frontend-next/src/app/_home/FirstRunHint.tsx` 생성:

```tsx
// src/app/_home/FirstRunHint.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { logEvent } from "@/lib/logEvent";

const HINT_DONE_KEY = "apt_first_run_hint_done";

interface FirstRunHintProps {
  /** 지도 모드 && 검색/지역/넛지 아무것도 없는 첫 상태일 때만 true */
  active: boolean;
}

/**
 * 첫 실행 빈 상태 힌트 (E2).
 *
 * 검색도 추천도 없는 첫 화면에서 다음 행동(① 지역 검색 → ② 라이프스타일 선택)을
 * 안내하고 /explore 갤러리로의 지름길을 제공한다.
 *
 * 1회성 정책: ✕ 클릭 또는 사용자가 진행(active=false 전환)하면 localStorage 에
 * 완료 마킹 — 재방문 사용자에게 노이즈가 되지 않도록 다시 뜨지 않는다.
 * (localStorage 접근 실패 시 이 세션에서만 숨김 유지)
 */
export default function FirstRunHint({ active }: FirstRunHintProps) {
  // SSR/hydration 안전: 기본 숨김으로 시작 → mount 후 localStorage 판정
  const [done, setDone] = useState(true);
  const shownLoggedRef = useRef(false);

  useEffect(() => {
    try {
      setDone(localStorage.getItem(HINT_DONE_KEY) === "1");
    } catch {
      setDone(false);
    }
  }, []);

  const markDone = () => {
    setDone(true);
    try {
      localStorage.setItem(HINT_DONE_KEY, "1");
    } catch {
      // private mode 등 저장 실패 — 세션 내 숨김만 유지
    }
  };

  // 사용자가 진행(검색·추천 시작)하면 힌트의 역할이 끝난 것 — 영구 마킹
  useEffect(() => {
    if (!active && !done) markDone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const visible = active && !done;

  useEffect(() => {
    if (visible && !shownLoggedRef.current) {
      shownLoggedRef.current = true;
      logEvent("first_run_hint_shown");
    }
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      role="status"
      className="fixed bottom-20 sm:bottom-8 left-1/2 -translate-x-1/2 z-10
                 flex items-center gap-3 rounded-full bg-gray-900/90 text-white
                 px-4 py-2.5 text-xs sm:text-sm shadow-lg backdrop-blur-sm
                 whitespace-nowrap animate-fade-in"
    >
      <span>
        <b>① 지역 검색</b> → <b>② 라이프스타일 선택</b>으로 추천을 받아보세요
      </span>
      <Link
        href="/explore"
        className="font-semibold text-amber-300 hover:text-amber-200"
      >
        추천 조합 둘러보기 →
      </Link>
      <button
        type="button"
        onClick={markDone}
        aria-label="힌트 닫기"
        className="text-white/70 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
```

- [ ] **Step 4: HomeShell 에 렌더 연결**

(a) import 추가:

```tsx
import FirstRunHint from "./FirstRunHint";
```

(b) store 셀렉터에 2개 추가 (Task 3 에서 추가한 것 외):

```tsx
  const searchKeywords = useAppStore((s) => s.searchKeywords);
  const selectedRegion = useAppStore((s) => s.selectedRegion);
```

(c) `hasResults` 계산(81행 부근) 아래에 파생 상태 추가:

```tsx
  // E2: 검색·지역·넛지 아무것도 없는 첫 상태 (첫 실행 힌트 노출 조건)
  const preSearchIdle =
    viewMode === "map" &&
    searchKeywords.length === 0 &&
    selectedRegion === null &&
    selectedNudges.length === 0;
```

(d) 지도 분기(`viewMode === "map"` 내부) `<RecentTradesBanner ... />` 아래에 렌더:

```tsx
          <FirstRunHint active={preSearchIdle} />
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd web/frontend-next && npx playwright test e2e/entry-flows.spec.ts e2e/smoke.spec.ts
```
Expected: 전체 PASS. 주의: E1/E3/D 테스트는 fresh context 라 힌트가 함께 떠 있음 — 기존 어서션과 충돌하지 않는지 확인(충돌 시 해당 테스트 시작부에서 힌트 ✕ 클릭 후 진행하도록 보강).

- [ ] **Step 6: Commit**

```bash
git add web/frontend-next/src/app/_home/FirstRunHint.tsx web/frontend-next/src/app/_home/HomeShell.tsx web/frontend-next/e2e/entry-flows.spec.ts
git commit -m "feat(web): 첫 실행 빈 상태 힌트 + /explore 지름길 (E2)"
```

---

### Task 7: 통합 검증 + 마무리

**Files:**
- Modify: `docs/prd/2026-07-03-entry-barrier-reduction-proposals.md` (상태 갱신)

- [ ] **Step 1: 전체 프론트 검증**

```bash
cd web/frontend-next && npm run lint && npm run build && npx playwright test
```
Expected: lint 0 error / build 성공 / e2e 전체 PASS

- [ ] **Step 2: 실환경 수동 확인 (로컬 백엔드 + 프론트)**

```bash
# 터미널 1
cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000
# 터미널 2
cd web/frontend-next && npm run dev
```

확인 항목:
1. `http://localhost:3000/` — 첫 화면에 힌트 노출, 비활성 칩 클릭 시 코치 노출(alert 없음)
2. `http://localhost:3000/explore` — 시드된 프리셋 6개 타일 렌더
3. 타일 클릭 → 홈 착지 → 지역 태그(📍) + 추천 카드 자동 노출
4. 신규거래 배너 확장 → "이 지역 추천" → 추천 카드 노출
5. `user_event` 적재 확인:

```bash
.venv/bin/python - <<'EOF'
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""SELECT event_type, COUNT(*) FROM user_event
  WHERE event_type IN ('nudge_chip_blocked','recent_banner_recommend_click','explore_view','explore_tile_click','first_run_hint_shown')
  GROUP BY event_type""")
for r in cur.fetchall():
    print(r)
conn.close()
EOF
```
Expected: 수동 확인으로 발생시킨 이벤트 타입별 카운트 출력

- [ ] **Step 3: PRD 상태 갱신**

`docs/prd/2026-07-03-entry-barrier-reduction-proposals.md` 의 `- 상태: 제안 승인 (구현 착수 전)` 을 `- 상태: E + D 구현 완료 (feature/entry-friction-quickwins), C/A/B 는 데이터 확보 후 결정` 으로 수정.

- [ ] **Step 4: Commit**

```bash
git add docs/prd/2026-07-03-entry-barrier-reduction-proposals.md docs/superpowers/plans/2026-07-03-entry-friction-quickwins.md
git commit -m "docs(prd): 진입장벽 제안 문서 상태 갱신 (E+D 구현 완료)"
```

- [ ] **Step 5: 사용자 액션 안내 (실행 아님 — 보고만)**

구현 완료 보고 시 아래를 사용자에게 안내한다:
1. **Railway 프리셋 시드**: `.venv/bin/python scripts/seed_explore_presets.py --target railway --apply` — production 쓰기이므로 사용자가 직접 실행
2. PR 생성 여부 결정 (main 직접 push 금지)
3. 배포 후 측정: `user_event` 의 `explore_tile_click`/`nudge_score` 퍼널로 타일별 CTR 확인 → C안(대화형) 착수 근거 데이터

---

## Self-Review 결과 (작성 시 수행)

- **Spec coverage**: PRD §6 E안 3건(① alert→코치=Task 2, ② 빈 상태 힌트=Task 6, ③ 배너 추천 런처=Task 3), §5 D안(갤러리=Task 4·5, 딥링크 재사용, common_code 관리, 측정 이벤트) 모두 태스크 존재. D의 "실거래 트렌드 반자동 큐레이션"은 PRD 에서도 '검토' — YAGNI 로 제외(수동 시드 6종으로 시작).
- **Placeholder**: 없음 — 모든 코드 스텝에 실제 코드 포함.
- **Type consistency**: `logEvent(eventType, payload?)` / `CodeItem`(export) / `ExplorePreset.sigunguCode(camelCase, TS 내부)` vs extra JSON `sigungu_code(snake_case, 외부 데이터)` — 명명 규칙과 일치. `onRecommendRegion(sigunguCode, sigunguLabel)` 시그니처 Task 3 정의·소비 일치.
- **알려진 리스크**: (1) e2e 에서 FirstRunHint 가 다른 테스트 화면에 겹칠 수 있음 — Task 6 Step 5 에 보강 지침 명시. (2) 시드 sigungu_code 실존 여부는 스크립트가 검증(skip+경고). (3) `/explore` 서버 fetch 는 백엔드 불가 시 빈 갤러리로 degrade(빌드 실패 방지) — fallback 발동 조건 코드 주석에 명시.
