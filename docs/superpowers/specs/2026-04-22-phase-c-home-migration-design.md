# Phase C — 홈·Kakao Maps·Zustand 이관 설계

- **상태**: 승인 대기
- **날짜**: 2026-04-22
- **관련**: PR #82 (Phase A/B/D 머지), `docs/adr/` 내 장기 Next.js 이전 계획

## 목적

Next.js 16 이전의 마지막 큰 덩어리. 홈 페이지(`/`) — Kakao Maps·필터·NUDGE 스코어링·챗봇·비교·대시보드 — 를 `web/frontend-next/` 로 이전해 **Vercel 배포 준비 완료** 상태로 만든다.

## 범위

### 포함
- `app/page.tsx` client 진입점 + `_home/` 하위 홈 UI 전체
- `_home/Map/` Kakao Maps 전체 재설계 (window 전역 콜백 제거, React portal InfoWindow, 타입 ambient d.ts)
- `lib/store/` Zustand 단일 스토어 + 4개 slice (search/nudge/chat/map)
- 기존 컴포넌트 11개 + 훅 4개 Next.js 로 이관
- 홈 모달용 Client DetailModal (`_home/DetailModalClient.tsx`) — Phase B Server 섹션의 Client 복제

### 제외 (별도 Phase)
- Vercel 프로젝트 연결 (Phase E)
- DNS 전환 (Phase F)
- `web/frontend/` 삭제·ADR (Phase G)
- 백엔드 FastAPI 변경
- UI/UX 재디자인
- 테스트 프레임워크 도입

## 확정된 기술 결정

| 결정 | 값 | 근거 |
|---|---|---|
| 상태 관리 | **Zustand 단일 스토어, slice 4개** | Map 재설계 context 에서 selector 별 re-render, Provider 중첩 회피 |
| Kakao Maps | **자체 wrapper 재설계** | 외부 의존성 없이 타입 안전 확보, 클러스터러·커스텀 오버레이 등 특수 요구 보존 |
| window 전역 콜백 | **완전 제거** (props + React portal) | 타입 안전·SSR 호환·테스트 용이 |
| 컴포넌트 이관 | **Wave 1 리프 → Wave 2 store 결합 → Wave 3 Map/Shell** | 의존성 낮은 순부터 |

## 아키텍처

```
web/frontend-next/src/
├── app/
│   ├── layout.tsx                   Server (기존)
│   ├── page.tsx                     Client ("use client" → <HomeShell />)
│   ├── error.tsx                    Client 에러 바운더리 (신규)
│   ├── apartment/[pnu]/              Server (기존 Phase B)
│   ├── about/page.tsx                Server (기존 Phase D)
│   ├── robots.ts, sitemap.ts         (기존 Phase D)
│   └── _home/                        Client 컴포넌트 격리 (_ = 라우트 아님)
│       ├── HomeShell.tsx             viewMode 스위치·배치
│       ├── Map/
│       │   ├── MapView.tsx           Kakao SDK 통합 진입점
│       │   ├── useKakaoReady.ts      kakao.maps.load(cb) 기반 준비 감지
│       │   ├── useMapInstance.ts     Map/Clusterer/InfoWindow refs + idle
│       │   ├── markers/
│       │   │   ├── createBasicMarker.ts
│       │   │   ├── createRankedMarker.ts
│       │   │   └── createChatMarker.ts
│       │   ├── InfoWindowBody.tsx    React 컴포넌트 (HTML string 대체)
│       │   └── portalToInfoWindow.ts createRoot → kakao.maps.InfoWindow
│       ├── FilterPanel.tsx           (이관)
│       ├── NudgeBar.tsx              (이관)
│       ├── ResultCards.tsx           (이관, onSelect 에 setSelectedPnu 동시 호출)
│       ├── RecentTradesBanner.tsx    (이관)
│       ├── ChatButton.tsx            (이관)
│       ├── ChatModal.tsx             (이관)
│       ├── ChatInput.tsx             (이관)
│       ├── ChatMessage.tsx           (이관)
│       ├── CompareModal.tsx          (이관)
│       ├── WeightDrawer.tsx          (이관)
│       ├── Dashboard.tsx             (이관)
│       ├── FeedbackStats.tsx         (이관)
│       ├── TradeHistoryPanel.tsx     (이관)
│       ├── DetailModalClient.tsx     Phase B Server 섹션의 Client 복제
│       └── detail-sections/          Client 버전 sections (server 재사용 불가)
├── hooks/
│   ├── useApartments.ts              (이관, 내부 Zustand 위임)
│   ├── useNudge.ts                   (이관, 내부 Zustand 위임)
│   ├── useChat.ts                    (이관, SSE local state 유지)
│   ├── useCodes.ts                   (이관 그대로)
│   └── useUrlSyncedPnu.ts            (신규, /apartment/:pnu 딥링크 sync)
├── lib/
│   ├── site.ts, api.ts, device.ts    (기존)
│   └── store/
│       ├── index.ts                  create<AppStore>(slice 조립)
│       ├── searchSlice.ts
│       ├── nudgeSlice.ts
│       ├── chatSlice.ts
│       └── mapSlice.ts
└── types/
    └── kakao-maps.d.ts               ambient (신규)
```

**핵심 원칙**
- `_home/` 의 `_` prefix 는 Next.js 라우트 세그먼트 아님 (private directory).
- Phase B Server sections 는 Client 에서 import 불가 → `_home/detail-sections/` 로 **명시적 복제**. presentation 공통(`Section`, `DataList`, `formatPriceManwon`) 은 공유 유틸로 뽑아 양쪽 재사용.
- 모든 client 호출은 `lib/api`(axios + X-Device-Id interceptor), Server Component 는 native `fetch` + `next.revalidate`.

## Zustand Store 설계

### 단일 store 조립

```ts
// lib/store/index.ts
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
    { name: "apt-recom", enabled: process.env.NODE_ENV !== "production" },
  ),
);
```

### Slice별 상태·액션

| Slice | 소유 상태 | 주요 action |
|---|---|---|
| **searchSlice** | `searchKeywords`, `keywordLabels`, `selectedRegion`, `filters`, `apartments`, `mapBounds`, `regionFitNonce` | `addKeyword`, `removeKeyword`, `clearKeywords`, `selectRegion`, `clearRegion`, `applyFilters`, `clearFilters`, `onBoundsChange`, `fetchApartments` |
| **nudgeSlice** | `selectedNudges`, `customWeights`, `defaultWeights`, `nudgeResults`, `nudgeLoading`, `rankContext` | `toggleNudge`, `setCustomWeights`, `fetchDefaultWeights`, `scoreApartments`, `setRankContext` |
| **chatSlice** | `showChat`, `chatInitialMessage`, `chatAnalyzeContext`, `chatHighlightApts`, `chatFocusApts`, `compareList` | `openChat`, `closeChat`, `setInitialMessage`, `setAnalyzeContext`, `addHighlight`, `clearHighlights`, `toggleCompare`, `clearCompare` |
| **mapSlice** | `selectedPnu`, `focusPnu`, `viewMode` | `selectApartment`, `clearSelection`, `focusApartment`, `clearFocus`, `switchView` |

### 기존 훅 API 유지

컴포넌트 관점에선 `useApartments()`·`useNudge()` 호출 패턴 동일. 훅 내부만 Zustand store 에 위임해 backward compatibility.

### 성능

- Zustand selector 결과 `Object.is` 비교로 re-render 최소화
- 단일 필드 구독 기본, 복합 객체만 `useShallow`
- devtools middleware production 자동 제외

## Map 컴포넌트 재설계

### 재설계 지점 vs 보존 지점

**재설계**
- window 전역 콜백 4개 (`__detailClick`/`__chatAnalyze`/`__compareToggle`/`__closeInfoWindow`) → props 치환
- InfoWindow HTML string + `onclick` → React portal + JSX
- `setInterval` 폴링 → `kakao.maps.load(cb)` 콜백
- `window.kakao` any → ambient `kakao.maps.*` namespace

**보존**
- 클러스터러 (`MarkerClusterer`)
- SVG 마커 3종(회색 점·순위 컬러·챗봇 빨강)
- idle 이벤트 → bounds 보고
- 디자인 (색상·크기·애니메이션)

### InfoWindow React Portal 패턴

```ts
// portalToInfoWindow.ts
export function openInfoWindow(
  map: kakao.maps.Map,
  position: kakao.maps.LatLng,
  content: React.ReactElement,
) {
  const container = document.createElement("div");
  const root = createRoot(container);
  root.render(content);
  const iw = new kakao.maps.InfoWindow({ position, content: container, zIndex: 10 });
  iw.open(map);
  return () => {
    iw.close();
    queueMicrotask(() => root.unmount());  // race-free cleanup
  };
}
```

### MapView props

```ts
type MapViewProps = {
  apartments: Apartment[];
  scoredApartments: ScoredApartment[] | null;  // NUDGE 결과
  chatHighlights: ChatHighlight[];
  focusPnu: FocusPnu | null;
  onBoundsChange: (bounds: MapBounds) => void;
  onDetailOpen: (pnu: string) => void;
  onChatAnalyze: (name: string, pnu: string) => void;
  onCompareToggle: (pnu: string, name: string) => void;
};
```

store 구독은 `HomeShell` 에서 하고 props 로 주입 — Map 컴포넌트는 store 무지(無知), 재사용·테스트 용이.

### 타입 정의

```ts
// types/kakao-maps.d.ts — 우리가 실제 쓰는 API 만
declare global { interface Window { kakao?: typeof kakao; } }
declare namespace kakao.maps {
  class Map { ... }
  class LatLng { ... }
  class Marker { ... }
  class CustomOverlay { ... }
  class InfoWindow { ... }
  class MarkerClusterer { ... }
  namespace event { function addListener(...): void; }
  function load(cb: () => void): void;
}
```

## 컴포넌트 이관 Wave

### Wave 1 — 리프 (의존성 낮음)
ChatInput, ChatMessage, FeedbackStats, RecentTradesBanner, TradeHistoryPanel, WeightDrawer
→ import 경로만 치환

### Wave 2 — Zustand 결합
FilterPanel, NudgeBar, ResultCards, CompareModal, ChatModal, ChatButton, Dashboard
→ store selector 구독 전환, props drilling 제거

### Wave 3 — 홈 진입점·Map
`_home/Map/*` 신규, `_home/HomeShell.tsx`, `app/page.tsx`, `_home/DetailModalClient.tsx`

### Hooks
- `useApartments`, `useNudge`: 내부 fetch 를 slice action 으로, 훅 시그니처 유지
- `useChat`: 거의 그대로 (SSE 스트림 local state), store 와는 `chatInitialMessage` 만 동기
- `useCodes`: 그대로 이관
- `useUrlSyncedPnu`: 신규 (`lib/route.ts` 로직 Next 환경 포팅)

### DetailModal Server/Client 중복 전략

Phase B 에서 `app/apartment/[pnu]/sections/*.tsx` 는 Server Component. 홈 Client 모달에서 재사용 불가 → `_home/detail-sections/*.tsx` **명시적 복제**.

공통화 기회: presentation-only 컴포넌트 (`Section`, `DataList`, `Empty`, `formatPriceManwon` 등) 는 **Server·Client 중립** 으로 뽑아 `components/presentation/` 같은 공유 폴더로. 데이터 fetch 만 중복.

## 데이터 흐름

```
User Action → useAppStore().action()
   ↓
Slice action → lib/api.get() (axios, X-Device-Id 자동)
   ↓                              ↓
set(state)                    api.apt-recom.kr
   ↓                              ↓
useAppStore selector          JSON response
   ↓
Component re-render (selector-scoped)
```

**Server Component 별도 경로**: `fetch(API_URL, { next: { revalidate: 3600 } })` — Zustand 무관.

### URL 동기화

```ts
// hooks/useUrlSyncedPnu.ts
export function useUrlSyncedPnu() {
  const selectedPnu = useAppStore(s => s.selectedPnu);
  const selectApartment = useAppStore(s => s.selectApartment);

  useEffect(() => {
    const sync = () => {
      const pnu = parseAptPnuFromPath(location.pathname);
      if (pnu !== selectedPnu) selectApartment(pnu);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  useEffect(() => {
    const nextPath = selectedPnu ? `/apartment/${selectedPnu}` : "/";
    if (location.pathname !== nextPath) history.pushState(null, "", nextPath);
    if (!selectedPnu) document.title = DEFAULT_DOCUMENT_TITLE;
  }, [selectedPnu]);
}
```

SSR hydration 불일치 방지: 초기 렌더는 `selectedPnu=null`, 첫 effect 에서 URL 반영.

### SSE 챗봇

`useChat` 의 `fetch` + `ReadableStream` 패턴 유지. `X-Device-Id` 는 훅 내부에서 `getDeviceId()` 호출. tool_start/done/delta/map_action/done 이벤트 파싱 로직 그대로. 완료 시 `chatSlice.addMessage`.

## 에러 처리

| 계층 | 에러 | 대응 |
|---|---|---|
| Server Component fetch | 상세 API 실패 | `notFound()` → `not-found.tsx` |
| Client action (axios) | 네트워크·5xx | slice `loading=false` + inline 빈 상태 |
| DetailModalClient | 상세 fetch 실패 | `loadError` + "아파트 정보 없음" + 닫기 |
| SSE 스트림 중단 | reader 에러 | 부분 메시지 완료, 에러 메시지 1개 추가 |
| Kakao SDK 로드 실패 | appkey/호스트 | `useKakaoReady` false 유지 → placeholder 노출 |
| 런타임 오류 | 예측 불가 | `app/error.tsx` fallback + 재시도 버튼 |

Sentry 는 선택 (`@sentry/nextjs` + wizard). 이 Phase 필수 아님.

## 검증

### 수동 회귀 18개 시나리오 (🔴 필수 11 / 🟡 중 5 / 🟢 낮음 2)

홈 로드, 지도 drag/zoom, NUDGE 토글, 가중치 드로어, 검색, 필터, 카드 클릭, 모달 닫기, 뒤로가기, 딥링크 직접/잘못된 PNU, 챗봇 스트림, 챗봇→비교, 비교 모달, 대시보드 전환/돌아오기, Recent banner, 크롤러 스모크(`curl -A ClaudeBot`).

### 자동화

- `next build` + TypeScript
- `next lint` (ESLint CLI)
- `web/backend/tests/test_core.py` 62/62 회귀 확인 (백엔드 무변경)
- agent 스모크: `curl -A ClaudeBot <preview>/apartment/<pnu> | grep <apt-name>`

### Phase C 완료 정의

- [ ] 로컬 `next dev` → 시나리오 #1~#17 **기존 Vite 앱과 동등** 동작
- [ ] `next build` 통과, TypeScript 에러 0
- [ ] 에이전트 스모크(#18) — 상세 페이지 본문 정보 유지
- [ ] `grep -r "window.__" _home/Map/` → 0건
- [ ] `web/frontend/` 무변경 (Phase G 에서 정리)

## 롤백

- 이 Phase 는 `web/frontend-next/` 내부 작업
- Vercel 미연동 상태 → 프로덕션 영향 없음
- 실패 시 PR 미머지, 서비스 중단 없음

## 핵심 파일·라인 참조

### 재사용
- `web/backend/routers/apartments.py`, `detail.py`, `nudge.py`, `chat.py`, `commute.py`, `similar.py`, `dashboard.py`, `codes.py`, `feedback.py`, `log.py` — 전부 그대로
- `web/frontend-next/src/app/layout.tsx:1` — Kakao Script 이미 통합
- `web/frontend-next/src/lib/site.ts:1` — SITE_URL/API_URL/BRAND 상수
- `web/frontend-next/src/app/apartment/[pnu]/sections/_shared.tsx:1` — presentation 공통 (Section/DataList) — Server/Client 중립으로 재분류해 재사용 검토
- 기존 `web/frontend/src/hooks/useChat.ts:1` — SSE 파싱 로직 이관 기준

### 신규 생성
- `web/frontend-next/src/lib/store/index.ts` + `searchSlice.ts` + `nudgeSlice.ts` + `chatSlice.ts` + `mapSlice.ts`
- `web/frontend-next/src/hooks/useUrlSyncedPnu.ts`
- `web/frontend-next/src/app/_home/HomeShell.tsx`
- `web/frontend-next/src/app/_home/Map/*` (8 파일)
- `web/frontend-next/src/app/_home/DetailModalClient.tsx`
- `web/frontend-next/src/app/_home/detail-sections/*.tsx`
- `web/frontend-next/src/app/error.tsx`
- `web/frontend-next/src/types/kakao-maps.d.ts`
- Wave 1/2 이관 컴포넌트 11개 + 훅 4개

### 수정
- `web/frontend-next/src/app/page.tsx` — default scaffold → `<HomeShell />`
- `web/frontend-next/package.json` — `zustand` 의존성 추가
- `web/frontend-next/next.config.ts` — 필요 시 추가 (현재로는 변경 없음)

## 작업 순서 (권장)

1. **Zustand 기반 구축** — 의존성 추가, 빈 store + 4 slice skeleton, 타입만
2. **types/kakao-maps.d.ts** — ambient 정의
3. **Wave 1 리프 컴포넌트** 이관 — import 경로만
4. **Map 재설계** — useKakaoReady, useMapInstance, MapView props, InfoWindow portal, 마커
5. **Wave 2 컴포넌트** + 훅 이관 — store 연결
6. **DetailModalClient + detail-sections 복제** — presentation 공유 유틸 분리
7. **HomeShell + app/page.tsx** — 최종 조립
8. **useUrlSyncedPnu** + error.tsx
9. **로컬 검증** — 18 시나리오 수동 + next build + 백엔드 회귀

예상 공수: 풀타임 약 1~1.5주.

## 다음 단계

이 spec 승인 후 `writing-plans` 스킬로 구현 plan 작성 → 단계별 실행.
