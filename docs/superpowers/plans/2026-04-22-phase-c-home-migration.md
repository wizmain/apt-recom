# Phase C — 홈·Kakao Maps·Zustand 이관 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Next.js 16 이전의 마지막 큰 덩어리 — 홈 페이지(`/`) 와 Kakao Maps·필터·NUDGE·챗봇·비교·대시보드 전부를 `web/frontend-next/` 로 이전해 Vercel 배포 준비 완료.

**Architecture:** Zustand 단일 스토어(slice 4개) + 자체 Map wrapper 재설계(window 전역 콜백 → React portal + props) + Wave 단위 이관(리프 → Map → store 결합 → Shell).

**Tech Stack:** Next.js 16.2.3, React 19.2.4, TypeScript 5.9 strict, Tailwind CSS 4, Zustand 5.x (신규), axios(기존), react-markdown(기존), Kakao Maps JS SDK.

**참고:** spec `docs/superpowers/specs/2026-04-22-phase-c-home-migration-design.md`. 테스트 프레임워크 미도입 상태이므로 TDD 대신 **빌드·타입체크·린트 + dev 서버 수동 검증** 을 각 task 의 verify step 으로 사용한다. 각 task 의 마지막 step 은 commit.

**실행 디렉터리:** 모든 task 는 `.worktrees/nextjs-phase-c/web/frontend-next/` 내부(상대경로 생략). `npm`/`git` 명령은 해당 디렉터리 기준.

---

## File Structure (신규·수정·삭제)

### 신규 (약 45 파일)
```
web/frontend-next/src/
├── lib/store/
│   ├── index.ts
│   ├── searchSlice.ts
│   ├── nudgeSlice.ts
│   ├── chatSlice.ts
│   └── mapSlice.ts
├── hooks/useUrlSyncedPnu.ts
├── types/kakao-maps.d.ts
├── components/presentation/
│   ├── Section.tsx
│   ├── DataList.tsx
│   ├── Empty.tsx
│   └── format.ts
├── app/error.tsx
└── app/_home/
    ├── HomeShell.tsx
    ├── Map/
    │   ├── MapView.tsx
    │   ├── useKakaoReady.ts
    │   ├── useMapInstance.ts
    │   ├── markers/createBasicMarker.ts
    │   ├── markers/createRankedMarker.ts
    │   ├── markers/createChatMarker.ts
    │   ├── InfoWindowBody.tsx
    │   └── portalToInfoWindow.ts
    ├── FilterPanel.tsx
    ├── NudgeBar.tsx
    ├── ResultCards.tsx
    ├── RecentTradesBanner.tsx
    ├── ChatButton.tsx
    ├── ChatModal.tsx
    ├── ChatInput.tsx
    ├── ChatMessage.tsx
    ├── CompareModal.tsx
    ├── WeightDrawer.tsx
    ├── Dashboard.tsx
    ├── FeedbackStats.tsx
    ├── TradeHistoryPanel.tsx
    ├── DetailModalClient.tsx
    └── detail-sections/
        ├── BasicInfo.tsx
        ├── LifeScores.tsx
        ├── PriceInfo.tsx
        ├── School.tsx
        ├── Facilities.tsx
        ├── Safety.tsx
        ├── Population.tsx
        └── RecentTrades.tsx
└── hooks/{useApartments.ts, useNudge.ts, useChat.ts, useCodes.ts}
```

### 수정
- `web/frontend-next/package.json` — `zustand` 의존성 추가
- `web/frontend-next/src/app/page.tsx` — default scaffold → `<HomeShell />`
- `web/frontend-next/src/app/apartment/[pnu]/sections/_shared.tsx` — presentation 공통 유틸을 `components/presentation/` 으로 이관 후 `_shared.tsx` 는 re-export 로 축소

### 삭제 (이 Phase 에서는 안 함, Phase G 에서 `web/frontend/` 정리 시)

---

## Prep

### Task 0: Worktree + 의존성

**Files:** git worktree, package.json

- [ ] **Step 1: 프로젝트 루트에서 worktree 생성**

Run:
```bash
cd /Users/wizmain/Documents/workspace/apt-recom
git worktree add .worktrees/nextjs-phase-c -b feature/nextjs-phase-c main
```
Expected: `Preparing worktree (new branch 'feature/nextjs-phase-c')` + `HEAD is now at ... Next.js 16 이전 Phase A/B/D ...`

- [ ] **Step 2: worktree 에서 의존성 설치**

Run:
```bash
cd .worktrees/nextjs-phase-c/web/frontend-next
npm install
```
Expected: `found 0 vulnerabilities`, `node_modules` 생성.

- [ ] **Step 3: zustand 추가**

Run:
```bash
npm install zustand
```
Expected: `added 1 package`.

- [ ] **Step 4: 빌드 스모크**

Run: `npm run build`
Expected: `Route (app)` 테이블에 `/`, `/_not-found`, `/about`, `/apartment/[pnu]`, `/robots.txt`, `/sitemap.xml` 6개 route + `Compiled successfully`.

- [ ] **Step 5: 커밋**

Run:
```bash
git add package.json package-lock.json
git commit -m "chore(next): zustand 의존성 추가 (Phase C 준비)"
```

---

## Wave A — Skeleton & Types

### Task 1: `types/kakao-maps.d.ts` ambient 정의

**Files:**
- Create: `src/types/kakao-maps.d.ts`

- [ ] **Step 1: 타입 파일 작성**

```ts
// src/types/kakao-maps.d.ts
export {};

declare global {
  interface Window {
    kakao?: typeof kakao;
  }
}

declare namespace kakao.maps {
  class LatLng {
    constructor(lat: number, lng: number);
    getLat(): number;
    getLng(): number;
  }

  class LatLngBounds {
    getSouthWest(): LatLng;
    getNorthEast(): LatLng;
  }

  interface MapOptions {
    center: LatLng;
    level?: number;
  }
  class Map {
    constructor(container: HTMLElement, options: MapOptions);
    getBounds(): LatLngBounds;
    setCenter(latlng: LatLng): void;
    getCenter(): LatLng;
    setLevel(level: number): void;
    getLevel(): number;
    panTo(latlng: LatLng): void;
  }

  interface MarkerOptions {
    position: LatLng;
    image?: MarkerImage;
    title?: string;
    clickable?: boolean;
  }
  class Marker {
    constructor(options: MarkerOptions);
    setMap(map: Map | null): void;
    getPosition(): LatLng;
  }

  interface MarkerImageOptions {
    offset?: Point;
  }
  class Point {
    constructor(x: number, y: number);
  }
  class Size {
    constructor(width: number, height: number);
  }
  class MarkerImage {
    constructor(src: string, size: Size, options?: MarkerImageOptions);
  }

  interface CustomOverlayOptions {
    position: LatLng;
    content: HTMLElement | string;
    yAnchor?: number;
    xAnchor?: number;
    zIndex?: number;
    clickable?: boolean;
  }
  class CustomOverlay {
    constructor(options: CustomOverlayOptions);
    setMap(map: Map | null): void;
  }

  interface InfoWindowOptions {
    position?: LatLng;
    content: HTMLElement | string;
    zIndex?: number;
    removable?: boolean;
  }
  class InfoWindow {
    constructor(options: InfoWindowOptions);
    open(map: Map, marker?: Marker): void;
    close(): void;
    setContent(content: HTMLElement | string): void;
    setPosition(pos: LatLng): void;
  }

  interface MarkerClustererOptions {
    map: Map;
    averageCenter?: boolean;
    minLevel?: number;
    gridSize?: number;
  }
  class MarkerClusterer {
    constructor(options: MarkerClustererOptions);
    addMarkers(markers: Marker[]): void;
    clear(): void;
    removeMarkers(markers: Marker[]): void;
  }

  namespace event {
    function addListener<T = unknown>(
      target: unknown,
      type: string,
      handler: (event?: T) => void,
    ): void;
    function removeListener<T = unknown>(
      target: unknown,
      type: string,
      handler: (event?: T) => void,
    ): void;
  }

  function load(callback: () => void): void;
}
```

- [ ] **Step 2: 타입 체크**

Run: `npx tsc --noEmit`
Expected: 에러 없음 (기존 코드와 충돌 없음).

- [ ] **Step 3: 커밋**

```bash
git add src/types/kakao-maps.d.ts
git commit -m "feat(next): Kakao Maps ambient 타입 정의"
```

---

### Task 2: Zustand store skeleton

**Files:**
- Create: `src/lib/store/index.ts`
- Create: `src/lib/store/searchSlice.ts`
- Create: `src/lib/store/nudgeSlice.ts`
- Create: `src/lib/store/chatSlice.ts`
- Create: `src/lib/store/mapSlice.ts`

- [ ] **Step 1: searchSlice skeleton**

```ts
// src/lib/store/searchSlice.ts
import type { StateCreator } from "zustand";
import type {
  Apartment,
  MapBounds,
  SelectedRegion,
} from "@/types/apartment";

export type FilterState = {
  min_area?: number;
  max_area?: number;
  min_price?: number;
  max_price?: number;
  min_floor?: number;
  built_after?: number;
};

export type SearchSlice = {
  searchKeywords: string[];
  keywordLabels: Record<string, string>;
  selectedRegion: SelectedRegion | null;
  filters: FilterState;
  apartments: Apartment[];
  mapBounds: MapBounds | null;
  regionFitNonce: number;

  addKeyword: (keyword: string, label?: string) => void;
  removeKeyword: (keyword: string) => void;
  clearKeywords: () => void;
  selectRegion: (region: SelectedRegion) => void;
  clearRegion: () => void;
  applyFilters: (filters: FilterState) => void;
  clearFilters: () => void;
  onBoundsChange: (bounds: MapBounds) => void;
  fetchApartments: () => Promise<void>;  // Wave D 에서 채움
};

export const createSearchSlice: StateCreator<SearchSlice> = (set) => ({
  searchKeywords: [],
  keywordLabels: {},
  selectedRegion: null,
  filters: {},
  apartments: [],
  mapBounds: null,
  regionFitNonce: 0,

  addKeyword: (keyword, label) =>
    set((s) => ({
      searchKeywords: s.searchKeywords.includes(keyword)
        ? s.searchKeywords
        : [...s.searchKeywords, keyword],
      keywordLabels: label
        ? { ...s.keywordLabels, [keyword]: label }
        : s.keywordLabels,
    })),
  removeKeyword: (keyword) =>
    set((s) => ({
      searchKeywords: s.searchKeywords.filter((k) => k !== keyword),
    })),
  clearKeywords: () => set({ searchKeywords: [], keywordLabels: {} }),
  selectRegion: (region) =>
    set((s) => ({ selectedRegion: region, regionFitNonce: s.regionFitNonce + 1 })),
  clearRegion: () => set({ selectedRegion: null }),
  applyFilters: (filters) => set({ filters }),
  clearFilters: () => set({ filters: {} }),
  onBoundsChange: (bounds) => set({ mapBounds: bounds }),
  fetchApartments: async () => {
    // Wave D Task 14 에서 구현
  },
});
```

- [ ] **Step 2: nudgeSlice skeleton**

```ts
// src/lib/store/nudgeSlice.ts
import type { StateCreator } from "zustand";
import type { NudgeWeights, ScoredApartment, TopContributor } from "@/types/apartment";

export type RankContext = {
  rank: number;
  selectedNudges: string[];
  topContributors: TopContributor[];
};

export type NudgeSlice = {
  selectedNudges: string[];
  customWeights: Record<string, Record<string, number>> | null;
  defaultWeights: NudgeWeights | null;
  nudgeResults: ScoredApartment[];
  nudgeLoading: boolean;
  rankContext: RankContext | null;

  toggleNudge: (nudgeId: string) => void;
  setCustomWeights: (w: Record<string, Record<string, number>> | null) => void;
  fetchDefaultWeights: () => Promise<void>;
  scoreApartments: () => Promise<void>;
  setRankContext: (ctx: RankContext | null) => void;
};

export const createNudgeSlice: StateCreator<NudgeSlice> = (set) => ({
  selectedNudges: [],
  customWeights: null,
  defaultWeights: null,
  nudgeResults: [],
  nudgeLoading: false,
  rankContext: null,

  toggleNudge: (nudgeId) =>
    set((s) => ({
      selectedNudges: s.selectedNudges.includes(nudgeId)
        ? s.selectedNudges.filter((n) => n !== nudgeId)
        : [...s.selectedNudges, nudgeId],
    })),
  setCustomWeights: (w) => set({ customWeights: w }),
  fetchDefaultWeights: async () => {
    // Wave D Task 15
  },
  scoreApartments: async () => {
    // Wave D Task 15
  },
  setRankContext: (ctx) => set({ rankContext: ctx }),
});
```

- [ ] **Step 3: chatSlice skeleton**

```ts
// src/lib/store/chatSlice.ts
import type { StateCreator } from "zustand";

export type ChatHighlightApt = {
  pnu: string;
  bld_nm: string;
  lat: number;
  lng: number;
  score?: number;
};

export type ChatFocusApt = { lat: number; lng: number };

export type ChatSlice = {
  showChat: boolean;
  chatInitialMessage: string | null;
  chatAnalyzeContext: { pnu: string; name: string } | null;
  chatHighlightApts: ChatHighlightApt[];
  chatFocusApts: ChatFocusApt[];
  compareList: { pnu: string; name: string }[];

  openChat: () => void;
  closeChat: () => void;
  setInitialMessage: (msg: string | null) => void;
  setAnalyzeContext: (ctx: { pnu: string; name: string } | null) => void;
  setHighlights: (apts: ChatHighlightApt[]) => void;
  clearHighlights: () => void;
  setFocusApts: (apts: ChatFocusApt[]) => void;
  toggleCompare: (pnu: string, name: string) => void;
  clearCompare: () => void;
};

export const createChatSlice: StateCreator<ChatSlice> = (set) => ({
  showChat: false,
  chatInitialMessage: null,
  chatAnalyzeContext: null,
  chatHighlightApts: [],
  chatFocusApts: [],
  compareList: [],

  openChat: () => set({ showChat: true }),
  closeChat: () =>
    set({ showChat: false, chatInitialMessage: null, chatAnalyzeContext: null }),
  setInitialMessage: (msg) => set({ chatInitialMessage: msg }),
  setAnalyzeContext: (ctx) => set({ chatAnalyzeContext: ctx }),
  setHighlights: (apts) => set({ chatHighlightApts: apts }),
  clearHighlights: () => set({ chatHighlightApts: [] }),
  setFocusApts: (apts) => set({ chatFocusApts: apts }),
  toggleCompare: (pnu, name) =>
    set((s) => ({
      compareList: s.compareList.some((c) => c.pnu === pnu)
        ? s.compareList.filter((c) => c.pnu !== pnu)
        : s.compareList.length < 5
          ? [...s.compareList, { pnu, name }]
          : s.compareList,
    })),
  clearCompare: () => set({ compareList: [] }),
});
```

- [ ] **Step 4: mapSlice skeleton**

```ts
// src/lib/store/mapSlice.ts
import type { StateCreator } from "zustand";

export type FocusPnu = {
  pnu: string;
  lat: number;
  lng: number;
  name: string;
};

export type MapSlice = {
  selectedPnu: string | null;
  focusPnu: FocusPnu | null;
  viewMode: "map" | "dashboard";

  selectApartment: (pnu: string | null) => void;
  clearSelection: () => void;
  focusApartment: (focus: FocusPnu | null) => void;
  clearFocus: () => void;
  switchView: (mode: "map" | "dashboard") => void;
};

export const createMapSlice: StateCreator<MapSlice> = (set) => ({
  selectedPnu: null,
  focusPnu: null,
  viewMode: "map",

  selectApartment: (pnu) => set({ selectedPnu: pnu }),
  clearSelection: () => set({ selectedPnu: null }),
  focusApartment: (focus) => set({ focusPnu: focus }),
  clearFocus: () => set({ focusPnu: null }),
  switchView: (mode) => set({ viewMode: mode }),
});
```

- [ ] **Step 5: store index — slice 조립**

```ts
// src/lib/store/index.ts
import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { createSearchSlice, type SearchSlice } from "./searchSlice";
import { createNudgeSlice, type NudgeSlice } from "./nudgeSlice";
import { createChatSlice, type ChatSlice } from "./chatSlice";
import { createMapSlice, type MapSlice } from "./mapSlice";

export type AppStore = SearchSlice & NudgeSlice & ChatSlice & MapSlice;

export const useAppStore = create<AppStore>()(
  devtools(
    (...a) => ({
      ...createSearchSlice(...a),
      ...createNudgeSlice(...a),
      ...createChatSlice(...a),
      ...createMapSlice(...a),
    }),
    {
      name: "apt-recom",
      enabled: process.env.NODE_ENV !== "production",
    },
  ),
);
```

- [ ] **Step 6: 타입 체크 + 빌드**

Run:
```bash
npx tsc --noEmit
npm run build
```
Expected: 에러 없음. build 결과 기존과 동일 (store 는 아직 사용 안 됨).

- [ ] **Step 7: 커밋**

```bash
git add src/lib/store/
git commit -m "feat(next): Zustand store skeleton — search/nudge/chat/map 4 slice"
```

---

### Task 3: presentation 공유 유틸 분리

**Files:**
- Create: `src/components/presentation/Section.tsx`, `DataList.tsx`, `Empty.tsx`, `format.ts`
- Modify: `src/app/apartment/[pnu]/sections/_shared.tsx` → re-export 로 축소

- [ ] **Step 1: `components/presentation/format.ts`**

```ts
// src/components/presentation/format.ts
export function formatYyyymmdd(s: string | null | undefined): string | null {
  if (!s) return null;
  if (s.length === 8) return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`;
  return s;
}

export function formatPriceManwon(amount: number | null | undefined): string | null {
  if (amount == null) return null;
  if (amount >= 10000) {
    const ok = Math.floor(amount / 10000);
    const rest = amount % 10000;
    return rest > 0 ? `${ok}억 ${rest.toLocaleString()}만원` : `${ok}억원`;
  }
  return `${amount.toLocaleString()}만원`;
}

export function formatMeters(m: number | null | undefined): string | null {
  if (m == null) return null;
  if (m < 1000) return `${Math.round(m)}m`;
  return `${(m / 1000).toFixed(1)}km`;
}
```

- [ ] **Step 2: `Section.tsx`**

```tsx
// src/components/presentation/Section.tsx
export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-base font-semibold text-gray-800">{title}</h2>
      {children}
    </section>
  );
}
```

- [ ] **Step 3: `DataList.tsx` + `Empty.tsx`**

```tsx
// src/components/presentation/DataList.tsx
export type DataItem = { label: string; value: string } | null | undefined;

export function DataList({ items }: { items: DataItem[] }) {
  const valid = items.filter((i): i is { label: string; value: string } => !!i);
  if (valid.length === 0) return null;
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border border-gray-200 bg-white p-4">
      {valid.map((it) => (
        <div key={it.label} className="text-sm">
          <dt className="text-gray-500">{it.label}</dt>
          <dd className="font-medium text-gray-900">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
```

```tsx
// src/components/presentation/Empty.tsx
export function Empty({ text = "정보 없음" }: { text?: string }) {
  return <p className="text-sm text-gray-400">{text}</p>;
}
```

- [ ] **Step 4: 기존 `sections/_shared.tsx` 을 re-export 로**

```tsx
// src/app/apartment/[pnu]/sections/_shared.tsx
export {
  Section,
} from "@/components/presentation/Section";
export { DataList, type DataItem } from "@/components/presentation/DataList";
export { Empty } from "@/components/presentation/Empty";
export {
  formatYyyymmdd,
  formatPriceManwon,
  formatMeters,
} from "@/components/presentation/format";
```

- [ ] **Step 5: 타입·빌드 검증**

```bash
npx tsc --noEmit
npm run build
```
Expected: 에러 없음. 상세 페이지 섹션들 기존과 동일 렌더 (import 해결 경로만 re-export 경유).

- [ ] **Step 6: 커밋**

```bash
git add src/components/presentation/ src/app/apartment/[pnu]/sections/_shared.tsx
git commit -m "refactor(next): presentation 공유 유틸을 components/presentation/ 로 분리"
```

---

## Wave B — Leaf Components 이관

### Task 4: `useCodes` 훅 이관

**Files:**
- Create: `src/hooks/useCodes.ts`

- [ ] **Step 1: 기존 파일 내용 확인**

Run:
```bash
cat ../../../../web/frontend/src/hooks/useCodes.ts
```
Expected: 71 LOC 훅 소스.

- [ ] **Step 2: Next.js 경로로 복사 + import 치환**

기존 `web/frontend/src/hooks/useCodes.ts` 를 `src/hooks/useCodes.ts` 로 복사하되 다음 치환:
- `import { API_BASE } from '../config'` → `import { API_URL as API_BASE } from '@/lib/site'`
- 그 외 import 없으면 그대로

- [ ] **Step 3: 검증**

```bash
npx tsc --noEmit
```
Expected: 에러 없음.

- [ ] **Step 4: 커밋**

```bash
git add src/hooks/useCodes.ts
git commit -m "feat(next): useCodes 훅 이관"
```

---

### Task 5: `ChatInput`, `ChatMessage`, `WeightDrawer` 이관

**Files:**
- Create: `src/app/_home/ChatInput.tsx`, `ChatMessage.tsx`, `WeightDrawer.tsx`

- [ ] **Step 1: 각 파일 복사 + `"use client"` 추가 + import 치환**

기존 `web/frontend/src/components/{ChatInput,ChatMessage,WeightDrawer}.tsx` 를 `src/app/_home/` 에 복사. 최상단에 `"use client";` 추가. import 치환 규칙:
| 기존 | 신규 |
|---|---|
| `from '../lib/api'` | `from '@/lib/api'` |
| `from '../lib/device'` | `from '@/lib/device'` |
| `from '../config'` | `from '@/lib/site'` (and `API_BASE` → `API_URL`) |
| `from '../types/apartment'` | `from '@/types/apartment'` |
| `from './WeightDrawer'` 등 상대참조 | 동일 디렉터리라면 `./WeightDrawer` 유지 |

- [ ] **Step 2: react-markdown 의존성 확인**

ChatMessage 가 `react-markdown` import 시:
```bash
npm install react-markdown
```

- [ ] **Step 3: 타입 체크**

Run: `npx tsc --noEmit`
Expected: 에러 없음. 사용 안 된 import 경고는 무시 가능.

- [ ] **Step 4: 커밋**

```bash
git add src/app/_home/ChatInput.tsx src/app/_home/ChatMessage.tsx src/app/_home/WeightDrawer.tsx package.json package-lock.json
git commit -m "feat(next): ChatInput/ChatMessage/WeightDrawer 이관 (Wave 1 리프)"
```

---

### Task 6: `FeedbackStats`, `TradeHistoryPanel`, `RecentTradesBanner` 이관

**Files:**
- Create: `src/app/_home/FeedbackStats.tsx`, `TradeHistoryPanel.tsx`, `RecentTradesBanner.tsx`

- [ ] **Step 1: Task 5 와 동일 치환 규칙으로 복사**

각 파일을 `src/app/_home/` 로 복사하고 `"use client";` + import 치환.

- [ ] **Step 2: 검증**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/FeedbackStats.tsx src/app/_home/TradeHistoryPanel.tsx src/app/_home/RecentTradesBanner.tsx
git commit -m "feat(next): FeedbackStats/TradeHistoryPanel/RecentTradesBanner 이관"
```

---

## Wave C — Map 재설계

### Task 7: `useKakaoReady` 훅

**Files:**
- Create: `src/app/_home/Map/useKakaoReady.ts`

- [ ] **Step 1: 훅 작성**

```ts
// src/app/_home/Map/useKakaoReady.ts
"use client";

import { useEffect, useState } from "react";

/**
 * Kakao Maps SDK 준비 감지.
 * layout.tsx 의 <Script afterInteractive /> 가 window.kakao 를 붙인 뒤,
 * kakao.maps.load(cb) 공식 API 로 LatLng/MarkerClusterer 등 사용 가능 상태에 진입.
 */
export function useKakaoReady(): boolean {
  const [ready, setReady] = useState<boolean>(false);

  useEffect(() => {
    if (ready) return;
    // 이미 sdk 가 로드 + load callback 이 실행된 상태인지
    if (typeof window !== "undefined" && window.kakao?.maps?.LatLng) {
      setReady(true);
      return;
    }
    // 아직 SDK 자체가 window 에 붙지 않은 상태 — 일정 간격으로 확인
    let cancelled = false;
    const check = () => {
      if (cancelled) return;
      const k = window.kakao;
      if (k?.maps?.load) {
        k.maps.load(() => {
          if (!cancelled) setReady(true);
        });
      } else {
        setTimeout(check, 100);
      }
    };
    check();
    return () => {
      cancelled = true;
    };
  }, [ready]);

  return ready;
}
```

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/Map/useKakaoReady.ts
git commit -m "feat(next): useKakaoReady 훅 — kakao.maps.load 공식 API 기반"
```

---

### Task 8: 마커 유틸 3종

**Files:**
- Create: `src/app/_home/Map/markers/createBasicMarker.ts`, `createRankedMarker.ts`, `createChatMarker.ts`

- [ ] **Step 1: `createBasicMarker`**

```ts
// src/app/_home/Map/markers/createBasicMarker.ts
"use client";

/**
 * 일반 아파트 마커 (작은 회색 점).
 * CustomOverlay 로 DOM 요소 자체를 지도에 올린다 (Marker 아닌 이유: 초소형 + 인터랙션 제어).
 */
export function createBasicMarker(
  position: kakao.maps.LatLng,
  onClick: () => void,
): kakao.maps.CustomOverlay {
  const el = document.createElement("div");
  el.style.cssText =
    "width:10px;height:10px;border-radius:50%;background:#6B7280;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.2);cursor:pointer;";
  el.addEventListener("click", onClick);
  return new window.kakao!.maps.CustomOverlay({
    position,
    content: el,
    yAnchor: 0.5,
    clickable: true,
  });
}
```

- [ ] **Step 2: `createRankedMarker`**

```ts
// src/app/_home/Map/markers/createRankedMarker.ts
"use client";

/**
 * 순위 컬러 마커 (1~3위 특별 색상, 나머지 파란색). 풍선 모양 SVG.
 */
const RANK_COLORS = {
  1: "#EF4444",
  2: "#F97316",
  3: "#EC4899",
  default: "#3B82F6",
} as const;

export function createRankedMarker(
  position: kakao.maps.LatLng,
  rank: number,
  onClick: () => void,
): kakao.maps.CustomOverlay {
  const color =
    (RANK_COLORS as Record<number, string>)[rank] ?? RANK_COLORS.default;
  const svg = `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z" fill="${color}"/><circle cx="15" cy="14" r="8" fill="white"/><text x="15" y="18" text-anchor="middle" font-size="12" font-weight="bold" fill="${color}">${rank}</text></svg>`,
  )}`;
  const img = document.createElement("img");
  img.src = svg;
  img.style.cssText = "width:30px;height:40px;cursor:pointer;display:block;";
  img.addEventListener("click", onClick);
  return new window.kakao!.maps.CustomOverlay({
    position,
    content: img,
    yAnchor: 1,
    clickable: true,
  });
}
```

- [ ] **Step 3: `createChatMarker`**

```ts
// src/app/_home/Map/markers/createChatMarker.ts
"use client";

/**
 * 챗봇 하이라이트 마커 (빨강). 지도 강조용.
 */
export function createChatMarker(
  position: kakao.maps.LatLng,
  onClick: () => void,
): kakao.maps.CustomOverlay {
  const svg = `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="38" viewBox="0 0 28 38"><path d="M14 0C6.3 0 0 6.3 0 14c0 9.8 14 24 14 24s14-14.2 14-24C28 6.3 21.7 0 14 0z" fill="#dc2626"/><circle cx="14" cy="13" r="6" fill="white"/></svg>`,
  )}`;
  const img = document.createElement("img");
  img.src = svg;
  img.style.cssText = "width:28px;height:38px;cursor:pointer;display:block;";
  img.addEventListener("click", onClick);
  return new window.kakao!.maps.CustomOverlay({
    position,
    content: img,
    yAnchor: 1,
    clickable: true,
  });
}
```

- [ ] **Step 4: 타입 체크**

```bash
npx tsc --noEmit
```
Expected: kakao.maps.* 타입 누락 없음.

- [ ] **Step 5: 커밋**

```bash
git add src/app/_home/Map/markers/
git commit -m "feat(next): Map 마커 유틸 3종 — basic/ranked/chat"
```

---

### Task 9: `InfoWindowBody` + `portalToInfoWindow`

**Files:**
- Create: `src/app/_home/Map/InfoWindowBody.tsx`, `portalToInfoWindow.ts`

- [ ] **Step 1: `InfoWindowBody.tsx`**

```tsx
// src/app/_home/Map/InfoWindowBody.tsx
"use client";

export type InfoWindowApt = {
  pnu: string;
  bld_nm: string;
};

export function InfoWindowBody({
  apt,
  onDetailOpen,
  onChatAnalyze,
  onCompareToggle,
  onClose,
}: {
  apt: InfoWindowApt;
  onDetailOpen: (pnu: string) => void;
  onChatAnalyze: (name: string, pnu: string) => void;
  onCompareToggle: (pnu: string, name: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="min-w-[180px] p-3 bg-white rounded-lg shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 truncate">
          {apt.bld_nm}
        </h3>
        <button
          onClick={onClose}
          aria-label="닫기"
          className="text-gray-400 hover:text-gray-600 flex-shrink-0"
        >
          ✕
        </button>
      </div>
      <div className="mt-2 flex flex-col gap-1 text-xs">
        <button
          onClick={() => onDetailOpen(apt.pnu)}
          className="px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
        >
          상세 보기
        </button>
        <button
          onClick={() => onChatAnalyze(apt.bld_nm, apt.pnu)}
          className="px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          AI 분석
        </button>
        <button
          onClick={() => onCompareToggle(apt.pnu, apt.bld_nm)}
          className="px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          비교에 추가
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: `portalToInfoWindow.ts`**

```ts
// src/app/_home/Map/portalToInfoWindow.ts
"use client";

import { createRoot, type Root } from "react-dom/client";
import type { ReactElement } from "react";

/**
 * Kakao InfoWindow 에 React 컴포넌트 마운트.
 * HTML string + onclick 패턴을 React 이벤트로 대체해 window 전역 콜백 제거.
 *
 * @returns cleanup 함수 (InfoWindow close + React root unmount)
 */
export function openInfoWindow(
  map: kakao.maps.Map,
  position: kakao.maps.LatLng,
  content: ReactElement,
): () => void {
  const container = document.createElement("div");
  const root: Root = createRoot(container);
  root.render(content);
  const iw = new window.kakao!.maps.InfoWindow({
    position,
    content: container,
    zIndex: 10,
  });
  iw.open(map);
  return () => {
    iw.close();
    queueMicrotask(() => root.unmount());
  };
}
```

- [ ] **Step 3: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 4: 커밋**

```bash
git add src/app/_home/Map/InfoWindowBody.tsx src/app/_home/Map/portalToInfoWindow.ts
git commit -m "feat(next): InfoWindow React portal — HTML string + window 콜백 제거"
```

---

### Task 10: `useMapInstance` 훅 (Map·Clusterer·InfoWindow refs + idle)

**Files:**
- Create: `src/app/_home/Map/useMapInstance.ts`

- [ ] **Step 1: 훅 작성**

```ts
// src/app/_home/Map/useMapInstance.ts
"use client";

import { useEffect, useRef } from "react";
import type { MapBounds } from "@/types/apartment";

const INIT_CENTER = { lat: 37.5665, lng: 126.978 };
const INIT_LEVEL = 6;

/**
 * Kakao Map 인스턴스·클러스터러·InfoWindow 를 container 에 초기화.
 * `onBoundsChange` 는 debounced 로 호출되지 않음 — 호출부(hook `useApartments`) 에서 debounce.
 */
export function useMapInstance(
  container: React.RefObject<HTMLDivElement | null>,
  ready: boolean,
  onBoundsChange: (bounds: MapBounds) => void,
) {
  const mapRef = useRef<kakao.maps.Map | null>(null);
  const clustererRef = useRef<kakao.maps.MarkerClusterer | null>(null);

  useEffect(() => {
    if (!ready || !container.current || mapRef.current) return;
    const k = window.kakao!.maps;
    const map = new k.Map(container.current, {
      center: new k.LatLng(INIT_CENTER.lat, INIT_CENTER.lng),
      level: INIT_LEVEL,
    });
    mapRef.current = map;

    const clusterer = new k.MarkerClusterer({
      map,
      averageCenter: true,
      minLevel: 7,
      gridSize: 60,
    });
    clustererRef.current = clusterer;

    const emitBounds = () => {
      const b = map.getBounds();
      onBoundsChange({
        sw: { lat: b.getSouthWest().getLat(), lng: b.getSouthWest().getLng() },
        ne: { lat: b.getNorthEast().getLat(), lng: b.getNorthEast().getLng() },
      });
    };

    // 초기 1회
    emitBounds();
    k.event.addListener(map, "idle", emitBounds);
    // cleanup 은 map 을 destroy 하지 않음 — 페이지 unmount 시 GC 기대
  }, [ready, container, onBoundsChange]);

  return { mapRef, clustererRef };
}
```

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/Map/useMapInstance.ts
git commit -m "feat(next): useMapInstance — Map/Clusterer 초기화 + idle event"
```

---

### Task 11: `MapView` 조립

**Files:**
- Create: `src/app/_home/Map/MapView.tsx`

- [ ] **Step 1: 컴포넌트 작성**

```tsx
// src/app/_home/Map/MapView.tsx
"use client";

import { useEffect, useRef } from "react";
import type { Apartment, MapBounds, ScoredApartment } from "@/types/apartment";
import type { ChatHighlightApt } from "@/lib/store/chatSlice";
import type { FocusPnu } from "@/lib/store/mapSlice";
import { useKakaoReady } from "./useKakaoReady";
import { useMapInstance } from "./useMapInstance";
import { createBasicMarker } from "./markers/createBasicMarker";
import { createRankedMarker } from "./markers/createRankedMarker";
import { createChatMarker } from "./markers/createChatMarker";
import { InfoWindowBody } from "./InfoWindowBody";
import { openInfoWindow } from "./portalToInfoWindow";

export type MapViewProps = {
  apartments: Apartment[];
  scoredApartments: ScoredApartment[];
  chatHighlights: ChatHighlightApt[];
  focusPnu: FocusPnu | null;
  onBoundsChange: (bounds: MapBounds) => void;
  onDetailOpen: (pnu: string) => void;
  onChatAnalyze: (name: string, pnu: string) => void;
  onCompareToggle: (pnu: string, name: string) => void;
};

export function MapView(props: MapViewProps) {
  const {
    apartments,
    scoredApartments,
    chatHighlights,
    focusPnu,
    onBoundsChange,
    onDetailOpen,
    onChatAnalyze,
    onCompareToggle,
  } = props;

  const containerRef = useRef<HTMLDivElement>(null);
  const ready = useKakaoReady();
  const { mapRef } = useMapInstance(containerRef, ready, onBoundsChange);

  // 스코어드(순위) 마커 / 챗봇 하이라이트 / 일반 마커 3레이어 관리
  const rankedOverlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);
  const chatOverlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);
  const basicOverlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);
  const closeInfoRef = useRef<(() => void) | null>(null);

  const showInfo = (apt: { pnu: string; bld_nm: string; lat: number; lng: number }) => {
    if (!mapRef.current) return;
    closeInfoRef.current?.();
    const k = window.kakao!.maps;
    const position = new k.LatLng(apt.lat, apt.lng);
    closeInfoRef.current = openInfoWindow(
      mapRef.current,
      position,
      <InfoWindowBody
        apt={{ pnu: apt.pnu, bld_nm: apt.bld_nm }}
        onDetailOpen={(pnu) => {
          closeInfoRef.current?.();
          closeInfoRef.current = null;
          onDetailOpen(pnu);
        }}
        onChatAnalyze={(name, pnu) => {
          closeInfoRef.current?.();
          closeInfoRef.current = null;
          onChatAnalyze(name, pnu);
        }}
        onCompareToggle={(pnu, name) => onCompareToggle(pnu, name)}
        onClose={() => {
          closeInfoRef.current?.();
          closeInfoRef.current = null;
        }}
      />,
    );
  };

  // 순위 마커 갱신 (scoredApartments 우선)
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    rankedOverlaysRef.current.forEach((o) => o.setMap(null));
    rankedOverlaysRef.current = [];
    scoredApartments.forEach((apt, idx) => {
      if (!apt.lat || !apt.lng) return;
      const rank = idx + 1;
      const ov = createRankedMarker(
        new k.LatLng(apt.lat, apt.lng),
        rank,
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      ov.setMap(mapRef.current);
      rankedOverlaysRef.current.push(ov);
    });
    return () => {
      rankedOverlaysRef.current.forEach((o) => o.setMap(null));
    };
  }, [scoredApartments, ready, mapRef]);

  // 챗봇 하이라이트 마커
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    chatOverlaysRef.current.forEach((o) => o.setMap(null));
    chatOverlaysRef.current = [];
    chatHighlights.forEach((apt) => {
      const ov = createChatMarker(
        new k.LatLng(apt.lat, apt.lng),
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      ov.setMap(mapRef.current);
      chatOverlaysRef.current.push(ov);
    });
    return () => {
      chatOverlaysRef.current.forEach((o) => o.setMap(null));
    };
  }, [chatHighlights, ready, mapRef]);

  // 일반 아파트 마커 (스코어·챗봇이 없으면 기본 표시)
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    basicOverlaysRef.current.forEach((o) => o.setMap(null));
    basicOverlaysRef.current = [];
    if (scoredApartments.length > 0) return; // 순위 모드에서는 숨김
    apartments.forEach((apt) => {
      const ov = createBasicMarker(
        new k.LatLng(apt.lat, apt.lng),
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      ov.setMap(mapRef.current);
      basicOverlaysRef.current.push(ov);
    });
    return () => {
      basicOverlaysRef.current.forEach((o) => o.setMap(null));
    };
  }, [apartments, scoredApartments.length, ready, mapRef]);

  // focus 이동
  useEffect(() => {
    if (!mapRef.current || !ready || !focusPnu) return;
    const k = window.kakao!.maps;
    mapRef.current.panTo(new k.LatLng(focusPnu.lat, focusPnu.lng));
    showInfo({
      pnu: focusPnu.pnu,
      bld_nm: focusPnu.name,
      lat: focusPnu.lat,
      lng: focusPnu.lng,
    });
  }, [focusPnu, ready, mapRef]);

  return (
    <div ref={containerRef} className="w-full h-full">
      {!ready ? (
        <div className="flex items-center justify-center h-full text-gray-500 text-sm">
          지도를 불러오는 중...
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```
Expected: 에러 없음.

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/Map/MapView.tsx
git commit -m "feat(next): MapView 조립 — props 기반 + React portal InfoWindow"
```

---

## Wave D — Store Actions & Hooks

### Task 12: `searchSlice.fetchApartments` 구현

**Files:**
- Modify: `src/lib/store/searchSlice.ts` (fetchApartments 내부 채움)

- [ ] **Step 1: fetchApartments 구현**

기존 `searchSlice.ts` 의 `fetchApartments` 를 다음으로 교체:

```ts
import { api } from "@/lib/api";

// ... existing state/actions ...

fetchApartments: async () => {
  const { mapBounds, selectedRegion, filters } = useAppStore.getState() as SearchSlice;
  if (!mapBounds && !selectedRegion) return;

  const params: Record<string, string | number | undefined> = {
    ...filters,
  };
  if (selectedRegion) {
    params[selectedRegion.type === "sigungu" ? "sgg_code" : "bjd_code"] =
      selectedRegion.code;
  } else if (mapBounds) {
    params.sw_lat = mapBounds.sw.lat;
    params.sw_lng = mapBounds.sw.lng;
    params.ne_lat = mapBounds.ne.lat;
    params.ne_lng = mapBounds.ne.lng;
  }

  try {
    const res = await api.get<Apartment[]>("/api/apartments", { params });
    set({ apartments: res.data });
  } catch (err) {
    console.error("fetchApartments failed", err);
  }
},
```

> **Note:** `useAppStore` 순환참조 회피를 위해 `get()` 대신 `useAppStore.getState()` 사용. Zustand `StateCreator` 의 `get` 파라미터를 `createSearchSlice(set, get)` 로 받아 사용해도 됨.

- [ ] **Step 2: `useAppStore` import 추가**

`searchSlice.ts` 상단에:
```ts
import { useAppStore } from "./index";
```

- [ ] **Step 3: 빌드·타입 체크**

```bash
npx tsc --noEmit
npm run build
```
Expected: 순환 import 경고 없음 (동적 import 효과).

- [ ] **Step 4: 커밋**

```bash
git add src/lib/store/searchSlice.ts
git commit -m "feat(next): searchSlice.fetchApartments 구현"
```

---

### Task 13: `nudgeSlice.scoreApartments` + `fetchDefaultWeights`

**Files:**
- Modify: `src/lib/store/nudgeSlice.ts`

- [ ] **Step 1: 구현 추가**

```ts
import { api } from "@/lib/api";
import { useAppStore } from "./index";
import type { NudgeWeights, ScoredApartment } from "@/types/apartment";

// fetchDefaultWeights
fetchDefaultWeights: async () => {
  try {
    const res = await api.get<NudgeWeights>("/api/nudge/weights");
    set({ defaultWeights: res.data });
  } catch (err) {
    console.error("fetchDefaultWeights failed", err);
  }
},

// scoreApartments
scoreApartments: async () => {
  const state = useAppStore.getState();
  const { selectedNudges, customWeights, searchKeywords, filters, selectedRegion } = state;

  if (selectedNudges.length === 0) {
    set({ nudgeResults: [], nudgeLoading: false });
    return;
  }
  set({ nudgeLoading: true });
  try {
    const body: Record<string, unknown> = {
      nudges: selectedNudges,
      weights: customWeights,
      top_n: 10,
    };
    if (searchKeywords.length > 0) body.keywords = searchKeywords;
    if (Object.keys(filters).length > 0) body.filters = filters;
    if (selectedRegion) body.region = selectedRegion;

    const res = await api.post<ScoredApartment[]>("/api/nudge/score", body);
    set({ nudgeResults: res.data, nudgeLoading: false });
  } catch (err) {
    console.error("scoreApartments failed", err);
    set({ nudgeLoading: false });
  }
},
```

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 커밋**

```bash
git add src/lib/store/nudgeSlice.ts
git commit -m "feat(next): nudgeSlice.scoreApartments + fetchDefaultWeights"
```

---

### Task 14: `useApartments`, `useNudge`, `useChat` 훅 이관

**Files:**
- Create: `src/hooks/useApartments.ts`, `useNudge.ts`, `useChat.ts`

- [ ] **Step 1: `useApartments` — Zustand 위임 + debounce**

```ts
// src/hooks/useApartments.ts
"use client";

import { useEffect, useRef } from "react";
import { useAppStore } from "@/lib/store";

/**
 * 지도 bounds·region·filters·keywords 변화에 따라 /api/apartments 재조회.
 * 300ms debounce — 지도 drag 스팸 방지.
 */
export function useApartments() {
  const mapBounds = useAppStore((s) => s.mapBounds);
  const selectedRegion = useAppStore((s) => s.selectedRegion);
  const filters = useAppStore((s) => s.filters);
  const searchKeywords = useAppStore((s) => s.searchKeywords);
  const fetchApartments = useAppStore((s) => s.fetchApartments);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      void fetchApartments();
    }, 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [mapBounds, selectedRegion, filters, searchKeywords, fetchApartments]);
}

export function countActiveFilters(f: Record<string, unknown>): number {
  return Object.values(f).filter((v) => v !== undefined && v !== null && v !== "").length;
}
```

- [ ] **Step 2: `useNudge` — 기본 weights fetch + 스코어링 트리거**

```ts
// src/hooks/useNudge.ts
"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";

/** 홈 mount 시 defaultWeights 를 받아오고, NUDGE 선택 변화에 반응해 스코어 재계산. */
export function useNudge() {
  const defaultWeights = useAppStore((s) => s.defaultWeights);
  const fetchDefaultWeights = useAppStore((s) => s.fetchDefaultWeights);
  const selectedNudges = useAppStore((s) => s.selectedNudges);
  const customWeights = useAppStore((s) => s.customWeights);
  const apartments = useAppStore((s) => s.apartments);
  const scoreApartments = useAppStore((s) => s.scoreApartments);

  useEffect(() => {
    if (!defaultWeights) void fetchDefaultWeights();
  }, [defaultWeights, fetchDefaultWeights]);

  useEffect(() => {
    void scoreApartments();
  }, [selectedNudges, customWeights, apartments, scoreApartments]);
}
```

- [ ] **Step 3: `useChat` 이관**

기존 `web/frontend/src/hooks/useChat.ts` (256 LOC) 를 `src/hooks/useChat.ts` 로 복사. import 치환:
- `import { API_BASE } from '../config'` → `import { API_URL as API_BASE } from '@/lib/site'`
- `import { getDeviceId } from '../lib/device'` → `import { getDeviceId } from '@/lib/device'`

파일 최상단에 `"use client";` 추가.

- [ ] **Step 4: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 5: 커밋**

```bash
git add src/hooks/useApartments.ts src/hooks/useNudge.ts src/hooks/useChat.ts
git commit -m "feat(next): useApartments/useNudge/useChat 이관 — Zustand 위임"
```

---

## Wave E — Store 결합 컴포넌트 이관

각 컴포넌트는 다음 공통 패턴을 따른다:
1. 기존 파일 복사 + `"use client";` 추가 + import 치환(Task 5 규칙)
2. 기존 props 중 store 에서 받을 수 있는 것은 `useAppStore(selector)` 로 교체
3. 나머지 props 는 유지

### Task 15: `FilterPanel` 이관

**Files:**
- Create: `src/app/_home/FilterPanel.tsx`

- [ ] **Step 1: 기존 파일 복사 + 치환**

기존 `web/frontend/src/components/FilterPanel.tsx` (203 LOC) 복사. import 치환 규칙 적용.

- [ ] **Step 2: props 최소화 — 필터 상태를 store 에서 구독**

기존 props 에서 `filters`, `onApply`, `onClear` 가 있다면:
- `filters` → `useAppStore((s) => s.filters)` 로 대체
- `onApply(f)` 호출 → `useAppStore((s) => s.applyFilters)` + `applyFilters(f)` 호출
- `onClear` → `useAppStore((s) => s.clearFilters)`

`isOpen` / `onClose` 같은 UI-only props 는 **유지** (홈이 제어).

- [ ] **Step 3: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 4: 커밋**

```bash
git add src/app/_home/FilterPanel.tsx
git commit -m "feat(next): FilterPanel 이관 + Zustand filters 구독"
```

---

### Task 16: `NudgeBar` 이관

**Files:**
- Create: `src/app/_home/NudgeBar.tsx`

- [ ] **Step 1~4: Task 15 패턴 동일**

- store 구독 대체:
  - `selectedNudges` → `useAppStore((s) => s.selectedNudges)`
  - `onToggle` → `useAppStore((s) => s.toggleNudge)`
  - `searchKeywords` / `keywordLabels` → 각각 구독
  - `addKeyword`/`removeKeyword`/`clearKeywords` → 각각 구독
- `www.apt-recom.kr` 링크는 `apt-recom.kr` 로 교체 (canonical 단일화)

커밋 메시지:
```bash
git commit -m "feat(next): NudgeBar 이관 + Zustand nudge/search 구독 + canonical 링크 통일"
```

---

### Task 17: `ResultCards` 이관

**Files:**
- Create: `src/app/_home/ResultCards.tsx`

- [ ] **Step 1: 복사 + 치환**

- [ ] **Step 2: onSelect 이중 액션 보존**

`onSelect(pnu)` 내부가 기존처럼 `focusApartment` + `selectApartment` 를 동시에 호출. 부모(HomeShell) 에서 wiring:

```tsx
<ResultCards
  results={results}
  loading={loading}
  onSelect={(pnu) => {
    const apt = results.find((r) => r.pnu === pnu);
    if (apt?.lat && apt?.lng) {
      focusApartment({ pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm });
    }
    selectApartment(pnu);
  }}
/>
```

ResultCards 자체는 `onSelect` props 만 받음 (store 무지).

- [ ] **Step 3: 커밋**

```bash
git commit -m "feat(next): ResultCards 이관 — onSelect 포커스+선택 동시 유지"
```

---

### Task 18: `CompareModal` 이관

**Files:**
- Create: `src/app/_home/CompareModal.tsx`

- [ ] **Step 1: 복사 + 치환 + store 구독**

- `compareList` → `useAppStore((s) => s.compareList)`
- `onToggle` → `useAppStore((s) => s.toggleCompare)`
- `onClear` → `useAppStore((s) => s.clearCompare)`

- [ ] **Step 2: 커밋**

```bash
git commit -m "feat(next): CompareModal 이관 + compareList store 구독"
```

---

### Task 19: `ChatButton` + `ChatModal` 이관

**Files:**
- Create: `src/app/_home/ChatButton.tsx`, `ChatModal.tsx`

- [ ] **Step 1: ChatButton — store showChat 제어**

```tsx
// ChatButton — 발췌
const showChat = useAppStore((s) => s.showChat);
const openChat = useAppStore((s) => s.openChat);
const closeChat = useAppStore((s) => s.closeChat);
// onClick: showChat ? closeChat() : openChat()
```

- [ ] **Step 2: ChatModal — initialMessage / analyzeContext 구독**

```tsx
const initialMessage = useAppStore((s) => s.chatInitialMessage);
const analyzeContext = useAppStore((s) => s.chatAnalyzeContext);
const closeChat = useAppStore((s) => s.closeChat);
// map_action 수신 시 store 의 setHighlights, setFocusApts, selectApartment 호출
```

- [ ] **Step 3: 커밋**

```bash
git commit -m "feat(next): ChatButton/ChatModal 이관 + chat slice 구독"
```

---

### Task 20: `Dashboard` 이관

**Files:**
- Create: `src/app/_home/Dashboard.tsx`

- [ ] **Step 1: 복사 + 치환**

- `onGoToMap(_name, _sggCd, pnu)` 내부에서 `clearKeywords`·`clearRegion`·`setSelectedPnu(null)` 등 호출 → 각각 store action 직접 호출로.
- pnu → 좌표 조회 후 `focusApartment` + `switchView("map")`.

- [ ] **Step 2: 커밋**

```bash
git commit -m "feat(next): Dashboard 이관 + viewMode 전환 store 액션화"
```

---

## Wave F — DetailModal 이중화

### Task 21: `_home/detail-sections/` — Client 버전 섹션 복제

**Files:**
- Create: `src/app/_home/detail-sections/BasicInfo.tsx`, `LifeScores.tsx`, `PriceInfo.tsx`, `School.tsx`, `Facilities.tsx`, `Safety.tsx`, `Population.tsx`, `RecentTrades.tsx`

- [ ] **Step 1: 각 파일을 Phase B 서버 섹션에서 복사**

`src/app/apartment/[pnu]/sections/*.tsx` 를 `src/app/_home/detail-sections/` 에 복사. 각 파일 최상단에 `"use client";` 추가.

import 치환: `from "./_shared"` → `from "@/components/presentation/Section"`, `from "@/components/presentation/DataList"`, `from "@/components/presentation/format"` 등 개별.

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```
Expected: `"use client"` 안에서 async 함수 export default 가 없어야 함 (Phase B server 가 async 였다면 이 Client 버전은 props 로 데이터 받아 동기 렌더).

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/detail-sections/
git commit -m "feat(next): detail-sections Client 복제 — 홈 모달 재사용"
```

---

### Task 22: `DetailModalClient` 조립

**Files:**
- Create: `src/app/_home/DetailModalClient.tsx`

- [ ] **Step 1: 작성**

```tsx
// src/app/_home/DetailModalClient.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { ApartmentDetail, TradesResponse } from "@/types/apartment";
import { BasicInfo } from "./detail-sections/BasicInfo";
import { LifeScores } from "./detail-sections/LifeScores";
import { PriceInfo } from "./detail-sections/PriceInfo";
import { School } from "./detail-sections/School";
import { Facilities } from "./detail-sections/Facilities";
import { Safety } from "./detail-sections/Safety";
import { Population } from "./detail-sections/Population";
import { RecentTrades } from "./detail-sections/RecentTrades";

export function DetailModalClient({ pnu }: { pnu: string }) {
  const clearSelection = useAppStore((s) => s.clearSelection);
  const [detail, setDetail] = useState<ApartmentDetail | null>(null);
  const [trades, setTrades] = useState<TradesResponse>({ trades: [], rents: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    Promise.all([
      api.get<ApartmentDetail>(`/api/apartment/${pnu}`),
      api.get<TradesResponse>(`/api/apartment/${pnu}/trades`),
    ])
      .then(([d, t]) => {
        if (cancelled) return;
        setDetail(d.data);
        setTrades(t.data ?? { trades: [], rents: [] });
        if (d.data?.basic?.bld_nm) {
          document.title = `집토리 - ${d.data.basic.bld_nm}`;
        }
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("DetailModalClient fetch failed", err);
        setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pnu]);

  const close = useCallback(() => {
    clearSelection();
  }, [clearSelection]);

  const handleBackdrop = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) close();
    },
    [close],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in"
      onClick={handleBackdrop}
    >
      <div className="relative w-full max-w-4xl h-[95dvh] sm:h-[85vh] mx-2 sm:mx-4 bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-start justify-between px-4 pt-4 pb-2 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900 truncate">
            {loadError
              ? "아파트 정보 없음"
              : (detail?.basic?.bld_nm ?? "로딩 중...")}
          </h2>
          <button
            onClick={close}
            className="ml-4 p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        {loadError ? (
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="text-4xl">🏚️</div>
              <p className="text-sm text-gray-500">
                요청하신 단지의 상세 정보를 불러오지 못했습니다.
              </p>
              <button
                onClick={close}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
              >
                닫기
              </button>
            </div>
          </div>
        ) : loading || !detail ? (
          <div className="flex-1 flex items-center justify-center h-64 text-gray-500 text-sm">
            데이터를 불러오는 중...
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-6">
            <BasicInfo basic={detail.basic} kapt={detail.kapt_info} />
            <PriceInfo basic={detail.basic} />
            <LifeScores scores={detail.scores} />
            <School school={detail.school} />
            <Facilities summary={detail.facility_summary} />
            <Safety safety={detail.safety} />
            <Population population={detail.population} />
            <RecentTrades trades={trades} />
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/DetailModalClient.tsx
git commit -m "feat(next): DetailModalClient — 홈 모달용 Client 상세"
```

---

## Wave G — 홈 조립 + URL + 에러

### Task 23: `useUrlSyncedPnu` 훅

**Files:**
- Create: `src/hooks/useUrlSyncedPnu.ts`

- [ ] **Step 1: 작성**

```ts
// src/hooks/useUrlSyncedPnu.ts
"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";

const DEFAULT_DOCUMENT_TITLE = "집토리 - 라이프스타일 아파트 찾기";
const APT_PATH = /^\/apartment\/([0-9]{19})\/?$/;

function parsePnu(pathname: string): string | null {
  const m = APT_PATH.exec(pathname);
  return m ? m[1] : null;
}

/**
 * selectedPnu ↔ /apartment/:pnu URL 양방향 동기화.
 *
 * - 초기 mount + popstate: URL → store
 * - selectedPnu 변화: store → URL (pushState)
 * - selectedPnu=null 로 돌아갈 때 document.title 기본값 복구
 */
export function useUrlSyncedPnu() {
  const selectedPnu = useAppStore((s) => s.selectedPnu);
  const selectApartment = useAppStore((s) => s.selectApartment);

  // URL → store
  useEffect(() => {
    const sync = () => {
      const pnu = parsePnu(window.location.pathname);
      selectApartment(pnu);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
    // selectApartment 는 stable (Zustand action reference) → deps 고정
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // store → URL + title
  useEffect(() => {
    const nextPath = selectedPnu ? `/apartment/${selectedPnu}` : "/";
    if (window.location.pathname !== nextPath) {
      window.history.pushState(null, "", nextPath);
    }
    if (!selectedPnu) {
      document.title = DEFAULT_DOCUMENT_TITLE;
    }
  }, [selectedPnu]);
}
```

- [ ] **Step 2: 타입 체크**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 커밋**

```bash
git add src/hooks/useUrlSyncedPnu.ts
git commit -m "feat(next): useUrlSyncedPnu — /apartment/:pnu ↔ selectedPnu 양방향"
```

---

### Task 24: `HomeShell` 조립

**Files:**
- Create: `src/app/_home/HomeShell.tsx`

- [ ] **Step 1: 작성**

```tsx
// src/app/_home/HomeShell.tsx
"use client";

import { useAppStore } from "@/lib/store";
import { useApartments } from "@/hooks/useApartments";
import { useNudge } from "@/hooks/useNudge";
import { useUrlSyncedPnu } from "@/hooks/useUrlSyncedPnu";
import { MapView } from "./Map/MapView";
import { FilterPanel } from "./FilterPanel";
import { NudgeBar } from "./NudgeBar";
import { ResultCards } from "./ResultCards";
import { RecentTradesBanner } from "./RecentTradesBanner";
import { ChatButton } from "./ChatButton";
import { ChatModal } from "./ChatModal";
import { CompareModal } from "./CompareModal";
import { WeightDrawer } from "./WeightDrawer";
import { Dashboard } from "./Dashboard";
import { DetailModalClient } from "./DetailModalClient";

export function HomeShell() {
  // 기본 구독
  const apartments = useAppStore((s) => s.apartments);
  const nudgeResults = useAppStore((s) => s.nudgeResults);
  const chatHighlights = useAppStore((s) => s.chatHighlightApts);
  const focusPnu = useAppStore((s) => s.focusPnu);
  const selectedPnu = useAppStore((s) => s.selectedPnu);
  const viewMode = useAppStore((s) => s.viewMode);
  const showChat = useAppStore((s) => s.showChat);
  const compareList = useAppStore((s) => s.compareList);

  // 액션
  const onBoundsChange = useAppStore((s) => s.onBoundsChange);
  const selectApartment = useAppStore((s) => s.selectApartment);
  const focusApartment = useAppStore((s) => s.focusApartment);
  const toggleCompare = useAppStore((s) => s.toggleCompare);
  const setAnalyzeContext = useAppStore((s) => s.setAnalyzeContext);
  const openChat = useAppStore((s) => s.openChat);

  // side effects (훅)
  useApartments();
  useNudge();
  useUrlSyncedPnu();

  return (
    <div className="relative w-full h-[100dvh] flex flex-col">
      {viewMode === "map" ? (
        <>
          <NudgeBar />
          <div className="relative flex-1">
            <MapView
              apartments={apartments}
              scoredApartments={nudgeResults}
              chatHighlights={chatHighlights}
              focusPnu={focusPnu}
              onBoundsChange={onBoundsChange}
              onDetailOpen={(pnu) => selectApartment(pnu)}
              onChatAnalyze={(name, pnu) => {
                setAnalyzeContext({ name, pnu });
                openChat();
              }}
              onCompareToggle={toggleCompare}
            />
            <ResultCards
              results={nudgeResults}
              loading={false}
              onSelect={(pnu) => {
                const apt = nudgeResults.find((r) => r.pnu === pnu);
                if (apt?.lat && apt?.lng) {
                  focusApartment({
                    pnu,
                    lat: apt.lat,
                    lng: apt.lng,
                    name: apt.bld_nm,
                  });
                }
                selectApartment(pnu);
              }}
            />
            <RecentTradesBanner />
          </div>
        </>
      ) : (
        <Dashboard />
      )}

      {selectedPnu ? <DetailModalClient pnu={selectedPnu} /> : null}
      {showChat ? <ChatModal /> : null}
      {compareList.length > 0 ? <CompareModal /> : null}

      <ChatButton />
      <FilterPanel />
      <WeightDrawer />
    </div>
  );
}
```

> **Note:** 각 Wave E 컴포넌트 (`FilterPanel`, `WeightDrawer`, `CompareModal`, `ChatModal`, `RecentTradesBanner`, `NudgeBar`, `Dashboard`) 의 props 는 Task 15–20 구현 시 확정된 것을 사용. 이 조립 단계에서 props 불일치가 발견되면 해당 컴포넌트로 돌아가 수정.

- [ ] **Step 2: 타입 체크 + 빌드**

```bash
npx tsc --noEmit
npm run build
```
Expected: 에러 없음.

- [ ] **Step 3: 커밋**

```bash
git add src/app/_home/HomeShell.tsx
git commit -m "feat(next): HomeShell 조립"
```

---

### Task 25: `app/page.tsx` 최종 전환

**Files:**
- Modify: `src/app/page.tsx`

- [ ] **Step 1: default scaffold 제거 + HomeShell 연결**

```tsx
// src/app/page.tsx
"use client";

import { HomeShell } from "./_home/HomeShell";

export default function HomePage() {
  return <HomeShell />;
}
```

- [ ] **Step 2: 빌드 + 로컬 dev 확인**

```bash
npm run build
NEXT_PUBLIC_API_URL=https://api.apt-recom.kr \
NEXT_PUBLIC_SITE_URL=http://localhost:3001 \
NEXT_PUBLIC_KAKAO_MAPS_APPKEY=832af9764dadaf139a8e82517d49e9f3 \
npm run dev -- --port 3001
```

Expected: `/` 접속 시 Kakao 지도 로드, 아파트 마커 표시, NudgeBar 클릭 → 스코어 결과. (별도 터미널에서 `curl -s http://localhost:3001/ | grep -c '<h1\|NudgeBar'` 으로 최소 smoke)

- [ ] **Step 3: dev 서버 종료 + 커밋**

```bash
# Ctrl+C 로 dev 종료
git add src/app/page.tsx
git commit -m "feat(next): app/page.tsx 를 HomeShell 로 교체 (scaffold 제거)"
```

---

### Task 26: `app/error.tsx` — 에러 바운더리

**Files:**
- Create: `src/app/error.tsx`

- [ ] **Step 1: 작성**

```tsx
// src/app/error.tsx
"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-4 text-center">
      <div className="text-5xl">⚠️</div>
      <h1 className="mt-4 text-xl font-bold text-gray-900">
        문제가 발생했습니다
      </h1>
      <p className="mt-2 text-sm text-gray-500">
        일시적인 오류일 수 있습니다. 잠시 후 다시 시도해주세요.
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        다시 시도
      </button>
    </main>
  );
}
```

- [ ] **Step 2: 빌드 확인**

```bash
npm run build
```

- [ ] **Step 3: 커밋**

```bash
git add src/app/error.tsx
git commit -m "feat(next): 전역 에러 바운더리 (app/error.tsx)"
```

---

## Wave H — 최종 검증

### Task 27: 전체 정적 검증 + grep 확인

**Files:** 검증만, 수정 없음

- [ ] **Step 1: TypeScript strict 체크**

Run: `npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 2: ESLint**

Run: `npm run lint`
Expected: 경고만 (기존 Map.tsx 같은 경고는 이관 대상 파일에서 제거되어야 함).

- [ ] **Step 3: 프로덕션 빌드**

Run: `npm run build`
Expected: 6개 route 전부 성공, static 생성 경고 외 에러 0.

- [ ] **Step 4: `window.__*` 전역 콜백 잔존 확인**

Run: `grep -rn "window\.__" src/ | grep -v node_modules`
Expected: **출력 없음** (0건). 있으면 해당 파일 리팩토링 누락.

- [ ] **Step 5: 백엔드 회귀**

Run:
```bash
cd /Users/wizmain/Documents/workspace/apt-recom
set -a && source .env && set +a
.venv/bin/python web/backend/tests/test_core.py
```
Expected: 62/62 통과 (백엔드 무변경 전제).

---

### Task 28: 18개 수동 시나리오 검증 (dev 서버 + Playwright MCP)

**Files:** 검증만

- [ ] **Step 1: dev 서버 기동**

```bash
cd .worktrees/nextjs-phase-c/web/frontend-next
NEXT_PUBLIC_API_URL=https://api.apt-recom.kr \
NEXT_PUBLIC_SITE_URL=http://localhost:3001 \
NEXT_PUBLIC_KAKAO_MAPS_APPKEY=832af9764dadaf139a8e82517d49e9f3 \
npm run dev -- --port 3001
```

- [ ] **Step 2: 각 시나리오 수동 실행 (체크박스로 기록)**

spec §검증.18시나리오 → 체크리스트:
- [ ] #1 홈 로드 → 지도 + 기본 마커
- [ ] #2 drag/zoom → bounds 변경 후 재조회
- [ ] #3 NUDGE 출퇴근 클릭 → 상위 10 컬러 마커 + 카드
- [ ] #4 WeightDrawer → 점수 재계산
- [ ] #5 검색 "자양동" → 후보/지역 이동
- [ ] #6 필터 패널 → 결과 업데이트
- [ ] #7 카드 클릭 → 지도 포커스 + 모달 오픈 + URL 변경
- [ ] #8 모달 닫기 → URL `/` + title 원복
- [ ] #9 브라우저 뒤로가기 → 모달 토글
- [ ] #10 딥링크 직접 `/apartment/<valid>` → 모달(홈) 또는 상세 페이지
- [ ] #11 잘못된 PNU → 에러 UI
- [ ] #12 챗봇 SSE → tool 표시 + map_action 하이라이트
- [ ] #13 챗봇→비교 추가
- [ ] #14 비교 모달
- [ ] #15 대시보드 전환
- [ ] #16 대시보드→지도 복귀
- [ ] #17 Recent banner 클릭 → 모달
- [ ] #18 agent 스모크: `curl -A ClaudeBot http://localhost:3001/apartment/1168010500001170000 | grep -c '쌍용'` → 1 이상

- [ ] **Step 3: dev 서버 종료 + 결과 기록**

수동 시나리오 결과를 PR body 에 적기 위해 이 체크리스트를 사용.

---

### Task 29: 최종 검증 스모크 + push + PR

**Files:** 없음

- [ ] **Step 1: 원격 push**

```bash
cd .worktrees/nextjs-phase-c
git push -u origin feature/nextjs-phase-c
```
Expected: `new branch` 메시지.

- [ ] **Step 2: PR 생성**

```bash
gh pr create --title "feat(next): Phase C — 홈·Map·Zustand 이관" --body "$(cat <<'EOF'
## Summary
Next.js 16 이전 마지막 큰 덩어리. 홈/Map/Zustand 전부 `web/frontend-next/` 에 완성.

## 변경
- **Zustand 단일 스토어** + 4 slice (search/nudge/chat/map)
- **Map 전체 재설계** — window 전역 콜백 4개 제거, React portal InfoWindow, `kakao.maps.load()` 공식 API, ambient 타입
- 11개 컴포넌트 + 4개 훅 이관
- `useUrlSyncedPnu` — `/apartment/:pnu` ↔ store 양방향
- `_home/DetailModalClient` + `detail-sections/` Client 복제 (Phase B Server 섹션과 presentation 공유)
- `app/error.tsx` 에러 바운더리

## 검증
- `npx tsc --noEmit` 에러 0
- `npm run lint` 에러 0
- `npm run build` 통과
- `grep -r "window\.__" src/` → 0건
- 백엔드 test_core.py 62/62
- 18 시나리오 수동 검증 (세부는 Task 28 체크리스트 참조)

## 배포 영향도
- Vercel 미연동 상태 → 프로덕션 영향 없음 (Phase E 에서 연결)

## 남은 작업 (별도 PR)
- **Phase E**: Vercel 프로젝트 연결, 프리뷰 URL 검증, CI workflow 업데이트
- **Phase F**: DNS 전환
- **Phase G**: `web/frontend/` 정리 + ADR-011
EOF
)"
```

---

## Self-Review 체크

1. **Spec coverage 확인**:
- 스펙 §아키텍처 → Task 24(HomeShell), Task 25(app/page.tsx) ✓
- 스펙 §Zustand store 설계 → Task 2, 12, 13 ✓
- 스펙 §Map 재설계 → Task 1, 7-11 ✓
- 스펙 §컴포넌트 이관 Wave → Task 4-6(Wave 1), 15-20(Wave 2), 7-11·24-25(Wave 3) ✓
- 스펙 §DetailModal 이중화 → Task 21, 22 ✓
- 스펙 §데이터 흐름 → Task 12, 13, 14 + Task 23(URL sync) ✓
- 스펙 §에러 처리 → Task 26 ✓
- 스펙 §검증 → Task 27, 28 ✓

2. **Placeholder scan**: "TODO/TBD" 없음. 각 task 에 코드·명령·기대 결과 명시.

3. **Type consistency**:
- `MapBounds` (types/apartment) → `onBoundsChange` / `useMapInstance` / `searchSlice.mapBounds` 모두 동일 타입 ✓
- `ScoredApartment` → `nudgeSlice.nudgeResults` / `MapView.scoredApartments` / `ResultCards.results` 동일 ✓
- `FocusPnu` → `mapSlice.focusApartment` / `MapView.focusPnu` 동일 ✓

## 실행 옵션

Plan complete and saved to `docs/superpowers/plans/2026-04-22-phase-c-home-migration.md`.

**1. Subagent-Driven (recommended)** — 매 task 마다 fresh subagent 디스패치 + 2-stage review. 태스크 간 review gate 로 drift 방지.

**2. Inline Execution** — 현재 세션에서 순차 실행. 체크포인트마다 review.

Phase C 는 28 개 task 로 방대하며 각 task 가 독립적 체크포인트를 가지므로 **Subagent-Driven 권장**.
