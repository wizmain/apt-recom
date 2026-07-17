# PRD — 인스타그램 카드뉴스 콘텐츠 랜딩 (`/content/[slug]`)

- 작성일: 2026-07-13
- 브랜치: `feature/instagram-content-landing`
- 관련 커밋: `e993477 feat(content): 인스타그램 카드 자동 생성 — 거래TOP·동네비교·숨은가성비 (#161)`
- 관련 기획 메모: `.hermes/plans/2026-07-13_164135-instagram-content-landing.md` (본 PRD가 레포 근거 기준으로 재작성한 상위 문서)

---

## 1. 개요 / 목표 / 비목표

### 배경

인스타그램 카드 3종(거래TOP·동네비교·숨은가성비)은 이미 자동 생성된다(`scripts/generate_insta_cards.py`). 그러나 카드 하단에 찍히는 유입 경로는 브랜드 도메인 문자열 하나뿐이다.

```
scripts/generate_insta_cards.py:59-60
FOOTER_BRAND = "apt-recom.kr"
FOOTER_DISCLAIMER = "공공데이터 기반 · 투자 자문이 아닙니다"
```

즉 카드를 본 사용자는 홈(`/`)의 빈 지도에 떨어지고, (1) 방금 본 게시물과 같은 화면인지 확인 불가, (2) 지역·라이프스타일 재설정, (3) 카드에서 본 단지 재검색 — 3중 재탐색 비용을 다시 지불한다. 카드 이미지 안의 수치는 어디에서도 재현되지 않는다.

### 목표 (MVP)

인스타그램 카드에서 유입된 사용자가 **카드와 동일한 수치·기준일·선정 근거**를 모바일 첫 화면에서 확인하고, **한 번의 CTA로 동일 조건이 적용된 기존 지도 추천**에 도달하게 한다.

### 성공지표

| 지표 | 정의 | 측정 |
|---|---|---|
| `content_view` → `content_map_cta_click` 전환율 | 랜딩 도달 대비 지도 CTA 클릭 | `user_event` (device_id 기준) |
| CTA 클릭 → `content_map_arrival` 도달률 | 딥링크가 실제로 store에 적용된 비율 | `user_event` |
| 도달 → 추천 실행 성공률 | `content_map_arrival` 이후 `/api/nudge/score` 성공 | 서버 로그 + 이벤트 |
| 단지 상세 클릭률 | `content_apartment_click` / `content_view` | `user_event` |

MVP 기준 목표치는 파일럿 1건 발행 후 baseline을 잡고 설정한다(사전 목표 수치 없음 — 추측 금지).

### 비목표 (Out of scope)

- 운영자용 CMS·어드민·예약 발행
- 콘텐츠 페이지 내부의 인터랙티브 카카오맵 렌더
- 콘텐츠 전용 DB 테이블(`content_post` 등) 도입
- 발행 후 수치를 최신 값으로 자동 갱신하는 기능
- 로그인·북마크·댓글·공유 버튼·A/B 테스트 플랫폼
- LLM 본문 자동 생성

---

## 2. 현재 구현 근거 요약 (file:line)

### 2-1. 카드 생성기 — `scripts/generate_insta_cards.py`

로컬 전용 배치 스크립트. `batch.db`의 로컬 DB + 운영 공개 API(`https://api.apt-recom.kr`)를 혼용한다.

```
scripts/generate_insta_cards.py:28-30   sys.path 조작 후 batch.db import (로컬 전용)
scripts/generate_insta_cards.py:62      PROD_API_BASE = "https://api.apt-recom.kr"
scripts/generate_insta_cards.py:85      OUTPUT_ROOT = <repo>/reports/insta
scripts/generate_insta_cards.py:715     output_dir = OUTPUT_ROOT / date.today().isoformat()
```

시리즈별 데이터 소스와 산출물:

| 시리즈 | 데이터 소스 | 생성 함수 | 출력 파일 | 근거 |
|---|---|---|---|---|
| `trade-top` | 로컬 DB `trade_history` + `trade_apt_mapping` + `apartments` + `common_code(sigungu)` | `generate_trade_top_cards()` | `trade-top-price.png`, `trade-top-hot.png` | :218-275, :362-374 |
| `compare` | 운영 API `GET /api/dashboard/regions`, `POST /api/nudge/score` (지역별 top_n=10 평균) | `generate_compare_card()` | `compare.png` | :380-398, :534-556 |
| `value` | 운영 API `POST /api/nudge/score` (top_n=30, `keyword`, `min_hhld`) + 로컬 DB `apt_price_score.price_per_m2` | `generate_value_card()` | `value.png` | :562-591, :629-667 |

핵심 계약(랜딩이 반드시 승계해야 할 의미론):

- **trade-top은 거래일이 아니라 신고일(`t.created_at`) 기준 최근 N일**이다.
  ```
  :234  WHERE t.created_at >= NOW() - (%s || ' days')::interval
  :208-215  trade_top_period_texts() — 라벨 "신고일 기준 · 최근 {days}일"
  ```
  동일 단지 중복 제거는 `COALESCE(m.pnu, sgg_cd || ':' || apt_nm)` 기준 `DISTINCT ON` (:221-242).
- **compare의 점수는 시군구 전체 평균이 아니라 "선택 넛지 상위 10개 단지의 평균 점수"**다 (:543-547).
- **value는 "가성비 넛지 상위 30 후보 중 min_hhld 통과 + price_per_m2 보유 단지를 ㎡당 가격 오름차순"** 이다 (:632-666). `min_hhld`는 서버 필터이며 응답의 `total_hhld_cnt`로 재검증하고, 미달 시 예외로 발행을 중단한다 (:638-647) — fallback 없이 실패시키는 현재 설계는 그대로 유지한다.

**현재 산출물은 PNG 이미지뿐이다. JSON 스냅샷을 만들지 않는다.** `save_card()`가 PNG만 저장하며(:673-677), 출력 디렉토리는 `.gitignore:85 reports/insta/`로 커밋 대상이 아니다.

실행 방식은 수동 CLI (`--series`, `--days`, `--regions`, `--nudge`, `--region`, `--min-hhld`; :680-710). 스케줄러/GitHub Actions 워크플로에 등록되어 있지 않다(`.github/workflows/` 내 insta 관련 워크플로 없음).

### 2-2. 프론트엔드 — `web/frontend-next` (기본 프론트, `web/frontend`는 레거시)

- Next.js **16.2.6**, React 19.2.6, Tailwind 4, zustand 5 (`web/frontend-next/package.json:19-27`).
- App Router. 기존 라우트: `/`, `/about`, `/guide`, `/explore`, `/region`, `/region/[code]`, `/apartment/[pnu]`.
- SSG/ISR 패턴 선례:
  - `web/frontend-next/src/app/apartment/[pnu]/page.tsx:24-25` — `export const revalidate = 3600; export const dynamicParams = true;`, `generateStaticParams()`는 빈 배열(:54-57), `params: Promise<PageParams>`를 await (:86, :183).
  - `web/frontend-next/src/app/region/[code]/page.tsx:23` — 동일 패턴 + `generateMetadata` + JSON-LD `<script>` 주입(:143-146).
- 메타데이터: 루트 layout에 `metadataBase`, `title.template = "%s | 집토리"` (`src/app/layout.tsx:12-19`). 페이지는 `alternates.canonical`만 선언(`apartment/[pnu]/page.tsx:97`).
- sitemap: `src/app/sitemap.ts` — 백엔드 sitemap fetch + 정적 페이지 수동 추가 (`:73-78`).
- robots: `src/app/robots.ts:33-47` — `/admin/`, `/api/`만 Disallow.
- 정적 자산 헤더: `web/frontend-next/public/_headers` (Cloudflare Workers Static Assets). `next.config.ts:39-49`의 `headers()`는 **Next 라우트에만** 적용되고 `public/` 파일에는 적용되지 않는다.
- 이미지: `next/image`를 쓰는 코드가 현재 **한 곳도 없다** (`src/**` grep 결과 0건). `next.config.ts:31-37`의 `images.remotePatterns`는 Kakao CDN만 등록되어 있고 아직 미사용.
- **Kakao Maps SDK는 루트 layout에서 전역 로드된다** (`src/app/layout.tsx:73-78`, `strategy="afterInteractive"`). 즉 `/content/*`에도 SDK 스크립트가 삽입된다 → 아래 리스크 항목 참조.
- E2E: Playwright + mock API (`playwright.config.ts:34-52`), 기존 딥링크 검증은 `e2e/entry-flows.spec.ts:122-137`.

> 제약: 이 워크트리에는 `web/frontend-next/node_modules`가 설치되어 있지 않아 `node_modules/next/dist/docs/`(AGENTS.md가 요구하는 Next 16 문서)를 **읽지 못했다.** 구현 담당(frontend-developer)은 반드시 `npm install` 후 해당 문서(App Router / metadata / static generation)를 먼저 읽고 시작해야 한다. 본 PRD의 Next API 서술은 레포 내 기존 코드 패턴(`apartment/[pnu]`, `region/[code]`)만을 근거로 한다.

### 2-3. 지도 딥링크

- 홈 딥링크는 쿼리파라미터를 `useBridgeParams`가 **1회 소비**해 store를 부트스트랩한다.
  ```
  src/hooks/useBridgeParams.ts:44-74
    - nudges (필수 트리거), sigungu_code, region_label 만 소비
    - common_code(group='nudge') 화이트리스트로 필터
    - 소비 후 window.history.replaceState 로 쿼리 제거 (:59)
    - selectedPnu !== null 이면 동작 안 함 (:42)
  ```
- 소비 순서는 현재 `selectRegion(fetch 포함)` → `setSelectedNudges` (`:68-74`). `filters`는 **아직 소비하지 않는다.**
- store의 필터 계약은 `FilterState` 9개 키로 이미 고정되어 있다.
  ```
  src/lib/store/searchSlice.ts:6-16
    min_area, max_area, min_price, max_price, min_floor, min_hhld, max_hhld, built_after, built_before
  ```
  이 필터는 `scoreApartments()`에서 `/api/nudge/score` 본문에 flat 전개된다(`src/lib/store/nudgeSlice.ts:113-116`), 그리고 `useNudge`가 `filters` 변경을 감지해 재스코어한다(`src/hooks/useNudge.ts:29-31`).
- 기존 딥링크 생성부 선례: `src/app/explore/PresetTiles.tsx:22-29` (typedRoutes 때문에 반환 타입을 `` `/?${string}` `` 템플릿 리터럴로 명시해야 함 — 주석 :16-21), `src/app/apartment/[pnu]/sections/RecommendCta.tsx:120-124`.
- **백엔드 `/api/map` 단일핀 모드는 이 기능과 무관하다.** 해당 엔드포인트는 RN WebView(toss-miniapp)용 HTML을 반환하며 `lat/lng/label/level/interactive` 쿼리로 핀 1개를 그린다 (`web/backend/main.py:353`, 단일핀 블록 `main.py:172-200`). 웹 랜딩에서 재사용할 이유가 없다 → 범위 제외.

### 2-4. 분석 이벤트

두 개의 수집 경로가 공존한다.

| 경로 | 화이트리스트 | 사용처 | 근거 |
|---|---|---|---|
| `POST /api/log/event` | 없음 (임의 event_type 허용) | `logEvent()` 유틸 → explore, 넛지칩, 첫실행힌트 | `src/lib/logEvent.ts:12-21`, `web/backend/routers/log.py:24-38` |
| `POST /api/events` | 있음 (`ALLOWED_EVENT_TYPES`, 미등록 시 422) | 단지 상세 CTA 2종만 | `web/backend/routers/events.py:21-49`, `RecommendCta.tsx:94-118` |

둘 다 최종적으로 `user_event(device_id, event_type, event_name, payload JSONB, created_at)` 테이블에 적재된다 (`web/backend/services/activity_log.py:47-72`, 스키마 `web/backend/database.py:612-619`, 인덱스 `database.py:729-732`).

선례(`explore_view`, `explore_tile_click`)는 `logEvent()`를 쓴다 (`PresetTiles.tsx:37,59`).

---

## 3. MVP 범위

### In scope

1. 카드 생성기(`scripts/generate_insta_cards.py`)가 이미지와 **동일한 실행에서** 발행 스냅샷 JSON을 산출.
2. 스냅샷 레지스트리 파일 + 타입/검증/조회 레이어 (프론트 빌드타임 정적 import).
3. `/content/[slug]` 모바일 랜딩 (Server Component, 정적 생성) + `/content` 목록.
4. 지도 CTA — 기존 홈 딥링크 확장(필터 allowlist 소비).
5. 퍼널 이벤트 4종 (`logEvent` 경로 사용).
6. canonical / OG / Article JSON-LD / sitemap 등록.
7. 파일럿 1건 발행 (`value` 시리즈).

### Out of scope

- CMS, DB 테이블, 새 백엔드 엔드포인트(§6-3의 선택지 A 채택 시), 페이지 내 지도 렌더, 관련 콘텐츠 추천, 캐러셀 전체 이미지 공개 호스팅.

---

## 4. 사용자 흐름 (시리즈별)

공통 진입:

```
인스타 카드(캡션/링크스티커) → https://apt-recom.kr/content/{slug}?utm_source=instagram&utm_campaign={series}
  → 히어로(시리즈 라벨·제목·한줄결론·기준일)
  → 핵심 결과(카드와 동일한 5행/2블록)
  → 왜 이렇게 선정됐나(top_contributors 기반)
  → 읽을 때 주의할 점(기준일·신고지연·투자자문 아님)
  → 지도 CTA (본문 1회 + 하단 sticky 1회)
```

### value (숨은 가성비) — 파일럿 대상

```
CTA "가성비 조건 그대로 {지역} 지도에서 보기"
  → /?nudges=cost&sigungu_code=...&region_label=...&min_hhld=100&content_slug=...&content_cta=...
  → useBridgeParams 소비 → applyFilters → selectRegion → setSelectedNudges → useNudge 자동 재스코어
  → 각 후보 행 → /apartment/{pnu} 상세
```
단일 지역·단일 넛지·단일 CTA라 딥링크 검증이 가장 단순하다.

### compare (동네 비교)

한 지도에서 시군구 2개를 동시에 선택할 수 없다(`selectedRegion`은 단일 객체 — `searchSlice.ts:23`). 따라서 CTA를 **지역별로 2개** 제공한다.
```
CTA-A "{지역A} 추천 보기" / CTA-B "{지역B} 추천 보기"
  → /?nudges={nudge}&sigungu_code={A|B}&region_label=...
```
상세 링크는 현재 데이터로는 각 지역 1위 단지명만 있고 pnu가 없다(§5 gap).

### trade-top (거래 TOP)

랭킹 자체가 추천 조건이 아니므로 `investment` 넛지를 임의로 부여하지 않는다(하드코딩된 가짜 의도 금지). 메인 CTA는 **거래가 발생한 지역 지도로 이동**으로 한정하고, 단지별 상세 링크를 우선한다.
```
행 클릭 → /apartment/{pnu} (pnu 확보 시)
CTA → /?nudges=... 형태를 강제하지 않음 → §11 오픈이슈 Q3
```

---

## 5. 데이터 스냅샷 계약

### 원칙

카드 이미지와 랜딩 본문은 **같은 실행의 같은 데이터**에서 나와야 한다. 랜딩이 요청 시점에 API를 다시 호출하면 게시물과 수치가 어긋난다 → **랜딩은 API를 호출하지 않는다.**

### 레지스트리 스키마 (제안)

파일: `web/frontend-next/src/content/instagram/posts.json` (배열)

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `slug` | string | Y | 소문자 ASCII+하이픈. 발행 후 불변 |
| `status` | `"draft" \| "published"` | Y | published만 라우팅/sitemap 포함 |
| `series` | `"trade_top" \| "compare" \| "value"` | Y | discriminant |
| `title` | string | Y | |
| `eyebrow` | string | Y | 카드의 시리즈 라벨과 동일 (`build_card_canvas` 1번째 인자) |
| `summary` | string | Y | 한 줄 결론 |
| `published_at` | string (YYYY-MM-DD) | Y | |
| `data_as_of` | string (YYYY-MM-DD) | Y | 생성 실행일 |
| `period_label` | string | Y | 예: "신고일 기준 최근 7일" |
| `cover_image` | string | Y | `/content/instagram/{slug}/cover.png` |
| `cover_alt` | string | Y | |
| `methodology` | string[] (≥1) | Y | §4의 시리즈별 의미론 문구 |
| `caveats` | string[] (≥1) | Y | 투자자문 아님 + 신고지연 + 재계산 차이 |
| `items` | Item[] | Y | 시리즈별 길이 규칙은 아래 |
| `map_ctas` | MapCta[] (≥1) | Y | |

`Item`:

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `rank` | int | Y | 1부터 연속 |
| `name` | string | Y | 단지명 또는 지역명 |
| `region` | string \| null | Y(nullable) | 시군구 라벨 |
| `pnu` | string(19자리) \| null | N | 있을 때만 `/apartment/{pnu}` 링크 |
| `metrics` | `{label,value,unit}[]` | Y | 카드에 그려진 수치와 1:1 |
| `reasons` | string[] | N | `top_contributors` 기반 |

`MapCta`:

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `id` | string | Y | 게시물 내 유일 |
| `label` | string | Y | |
| `nudges` | string[] | Y(≥1) | `useBridgeParams`가 nudges 없으면 아무것도 하지 않음 (`:45-46`) |
| `sigungu_code` | string \| null | N | |
| `region_label` | string \| null | N | |
| `filters` | FilterState 부분집합 | N | **허용 키는 `searchSlice.ts:6-16`의 9개뿐** |

명명은 snake_case, 접두어 규칙 준수(프로젝트 표준). 프론트 타입은 `series` 기반 discriminated union으로 정의하고 `any` 금지.

### 현재 구현과의 gap (반드시 메울 것)

| # | gap | 근거 | 영향 |
|---|---|---|---|
| G1 | 생성기가 JSON을 전혀 만들지 않음 (PNG만) | `generate_insta_cards.py:673-677` | 스냅샷 계약 전체가 신규 |
| G2 | **trade-top 행에 pnu가 없다.** 쿼리가 `apt_display_name, sgg_cd, deal_amount, exclu_use_ar`만 select | `:221-252` | 단지 상세 링크 불가 → 쿼리에 `m.pnu` 추가 필요(생성기 변경) |
| G3 | **value 행에 지역 라벨이 없다.** `/api/nudge/score` 응답은 `pnu, bld_nm, lat, lng, total_hhld_cnt, score, score_breakdown, top_contributors, score_percentile`만 반환 — `sigungu_code`/주소는 내부 `apt_map`에만 있고 응답에서 빠짐 | `web/backend/routers/nudge.py:208-232` (SQL은 `:72`에서 `new_plat_plc`, `sigungu_code`를 조회함) | item.region 채울 수 없음 → §11 Q1 |
| G4 | compare 결과에 각 지역 1위 단지의 **pnu가 유실**됨. `generate_compare_card`가 `top1_apt_name`만 보존 | `:548-554` (원본 `top10[0]`에는 pnu 존재) | 생성기에서 pnu 함께 보존하면 해결 |
| G5 | 카드 출력 경로가 gitignore 대상 | `.gitignore:85` | 공개 cover는 `public/content/instagram/{slug}/`로 별도 저장 필요 |
| G6 | 생성기가 slug/summary/발행 여부를 모른다 | CLI `:680-710` | `--slug/--summary/--publish/--force` 옵션 추가 |

---

## 6. 카드 생성기 ↔ Next.js 연계

### 6-1. 전달 방식: 레포 커밋된 JSON을 빌드타임 정적 import

- 생성기가 `posts.json`을 갱신하고 `cover.png`를 `public/`에 복사 → 커밋 → 배포.
- 프론트는 `src/content/instagram/posts.json`을 정적 import 후 **런타임 type guard로 검증**한다. 검증 실패는 빌드 오류로 드러내야 한다(조용한 fallback 금지). 단, `explorePreset.ts:45-48`처럼 "깨진 행은 건너뛴다" 패턴은 **여기선 채택하지 않는다** — 콘텐츠는 게시물 단위 신뢰성이 핵심이라 잘못된 레코드를 조용히 숨기면 게시물이 404가 되는 사고가 발생한다.
- 근거: 백엔드에 콘텐츠 테이블/엔드포인트가 없고(§2-1, §2-4), 게시물은 주 1~3건 수준의 저빈도 자산이다. DB/API 도입은 YAGNI.

### 6-2. 렌더링 전략: 완전 정적 (SSG)

- `/content/[slug]`는 외부 fetch가 **0건**이므로 ISR/revalidate가 필요 없다. `generateStaticParams()`가 published slug 전체를 반환 → 빌드타임 프리렌더. `dynamicParams = false`로 두어 unknown slug는 404.
- 이는 `apartment/[pnu]`(외부 API 의존 → `revalidate = 3600`, `dynamicParams = true`; `page.tsx:24-25`)와 의도적으로 다른 선택이며, 차이 이유를 코드 주석에 남긴다.
- 인스타 인앱 브라우저 대상이므로 첫 화면은 정적 HTML + 이미지 1장으로 제한한다.

### 6-3. 정적 자산 규칙

- cover 이미지는 `web/frontend-next/public/content/instagram/{slug}/cover.png`.
- Cloudflare Workers Static Assets 헤더는 `public/_headers`에서만 제어된다(`next.config.ts:45-47` 주석). 이미지 캐시 헤더가 필요하면 `_headers`에 `/content/instagram/*` 규칙을 추가한다. `next.config.ts:headers()`에 넣지 말 것.
- `next/image` 사용 선례가 레포에 없고 OpenNext Cloudflare 이미지 최적화 설정도 없다 → MVP는 `<img>` + 명시적 `width/height` + `loading="lazy"`(히어로는 eager)로 간다. `next/image` 도입은 별도 결정 사항(§11 Q5).

---

## 7. 지도 딥링크 사양

기존 홈 딥링크(`useBridgeParams`)를 확장한다. 새 라우트를 만들지 않는다.

**지원 쿼리 계약**

| 파라미터 | 소비 주체 | 비고 |
|---|---|---|
| `nudges` (CSV, 필수) | `setSelectedNudges` | 없으면 부트스트랩 자체가 동작 안 함 (`useBridgeParams.ts:45-46`) |
| `sigungu_code` | `selectRegion` | |
| `region_label` | `selectRegion` | 없으면 코드 문자열로 degrade (`:69`) |
| `min_area` `max_area` `min_price` `max_price` `min_floor` `min_hhld` `max_hhld` `built_after` `built_before` | `applyFilters` (**신규**) | allowlist = `FilterState` 키 9개 (`searchSlice.ts:6-16`). 숫자 파싱 실패/NaN은 주입하지 않는다 |
| `content_slug` `content_cta` | 로깅 컨텍스트 전용 (**신규**) | store에 넣지 않는다 |

**적용 순서 (중요)**: `applyFilters` → `selectRegion(내부에서 fetchApartments await)` → `setSelectedNudges`.
`selectRegion`이 `fetchApartments()`를 먼저 호출하므로(`searchSlice.ts:61-68`), 필터를 그 앞에 세팅하지 않으면 최초 아파트 조회가 필터 없이 나간다.

**기존 계약 보존**: 필터 없는 기존 링크(`/explore` 타일, 상세 CTA)는 현재와 동일하게 동작해야 한다 (`e2e/entry-flows.spec.ts:122-137` 유지).

**`/api/map` 단일핀 모드는 사용하지 않는다** (RN WebView 전용, `web/backend/main.py:172-200`).

---

## 8. 분석 이벤트 사양

전송 유틸: `logEvent()` (`src/lib/logEvent.ts:12`) → `POST /api/log/event` → `user_event`.
`/api/events`(화이트리스트, `events.py:21-26`)를 쓰면 백엔드 수정이 필요하므로 **MVP는 `logEvent` 경로를 채택**한다 (explore 선례와 동일).

| event_type | 발생 시점 | payload |
|---|---|---|
| `content_view` | 랜딩 mount 1회 | `slug`, `series`, `utm_source`, `utm_campaign` |
| `content_map_cta_click` | 지도 CTA 클릭 직전 | `slug`, `cta_id`, `placement`("inline"\|"sticky") |
| `content_apartment_click` | 후보 단지 상세 링크 클릭 | `slug`, `pnu`, `rank` |
| `content_map_arrival` | 홈에서 bridge 적용 직후 | `content_slug`, `content_cta`, `nudge_count`, `filter_count` |

규칙:
- UTM은 **허용 키만** 읽는다(`utm_source`, `utm_campaign`). 전체 URL·referrer 전송 금지 (개인정보/페이로드 비대화 방지).
- fire-and-forget — 로깅 실패가 네비게이션/추천을 막지 않는다 (`logEvent.ts:19-20` 규약).
- `content_view`는 mount당 1회 (`PresetTiles.tsx:34-38`의 `viewLoggedRef` 패턴 준용).

---

## 9. 시리즈별 예외 처리

### trade-top
- **신고일 기준**임을 `period_label`/`methodology`에 반드시 명시. "이번 주 거래"라고 쓰면 사실과 다르다 (`:234`).
- pnu 미확보 행(미매핑 거래)은 **텍스트로만** 표시하고 상세 링크를 만들지 않는다. 링크가 없다는 이유로 행을 숨기지 않는다.
- 로컬 DB 기준이므로 Railway → 로컬 sync 선행 필요(메모리 `reference_insta_cards`). 스냅샷의 `data_as_of`는 sync 이후 생성 실행일.
- 결과가 `CARD_LIST_SIZE`(5) 미만이면 발행 실패 처리(카드도 랜딩도 만들지 않음).

### compare
- 두 지역 중 하나라도 넛지 결과가 비면 이미 예외로 중단된다 (`:545`). 스냅샷 검증도 동일하게 유지.
- 점수는 **상위 10개 단지 평균**임을 methodology에 명시 (`:543-547`). "지역 전체 평균"으로 표현 금지.
- CTA 2개(지역별). CTA id는 게시물 내 유일.

### value
- `min_hhld` 미달 응답 혼입 시 예외 중단(:638-647) — 이 방어는 유지하고 스냅샷 생성 경로에도 적용.
- `price_per_m2` 없는 후보는 제외되며, 전부 없으면 예외(:660-663). 후보가 5개 미만이면 발행 실패.
- 운영 API(top 30) + 로컬 DB(price) 혼합이므로 두 소스의 신선도가 다를 수 있다 → `data_as_of` 1개 값만 노출하되, caveat에 "가격 데이터는 로컬 적재 기준"을 명시할지 §11 Q2에서 결정.

### 공통
- 랜딩 하단·CTA 근처에 "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다" 고지.
- `caveats` 누락은 검증 실패(발행 차단).

---

## 10. 테스트 / 검증 계획

프로젝트 표준 명령(CLAUDE.md) 기준.

| 단계 | 명령 |
|---|---|
| Python 생성기 단위 테스트 | `.venv/bin/python -m unittest scripts.tests.test_generate_insta_cards -v` |
| Python 포맷/린트 | `ruff format scripts/generate_insta_cards.py` / `ruff check --fix scripts/` |
| 프론트 타입체크 | `cd web/frontend-next && npx tsc --noEmit` |
| 프론트 린트 | `cd web/frontend-next && npm run lint` |
| E2E | `cd web/frontend-next && npm run e2e` |
| 빌드 | `cd web/frontend-next && npm run build` |
| Cloudflare 아티팩트 | `cd web/frontend-next && npm run cf:build` |

핵심 검증 케이스:

1. **생성기(Python)** — 필수 필드 누락, 중복 slug, 중복 rank, published 덮어쓰기(`--force` 없이), 5개 미만 후보, caveat 누락, 잘못된 pnu 포맷 → 모두 예외로 발행 차단.
2. **생성기 일관성** — 카드에 그린 값과 JSON `items[].metrics` 값이 동일(같은 publication 객체를 렌더가 소비).
3. **콘텐츠 조회 레이어(TS)** — unknown slug / draft slug → `null`. 지원하지 않는 filter key → 빌드 오류.
4. **E2E(Playwright)** — `/content/{slug}` 200, 첫 화면에 제목·기준일·CTA 노출; CTA 클릭 → 홈 이동 → 지역 태그 노출 + `/api/nudge/score` POST body가 스냅샷의 nudges/필터와 일치 (기존 `entry-flows.spec.ts:122-137` 패턴 재사용); `content_map_cta_click` 이벤트 요청 검증(`waitForRequest`로 `/api/log/event` 매칭).
5. **회귀** — 기존 explore 타일 딥링크 E2E가 그대로 통과.
6. **수동** — 모바일 뷰포트(360/390/768)에서 sticky CTA 가림 여부, 긴 단지명 말줄임, 뒤로가기 시 콘텐츠 페이지 복귀, 인스타 인앱 브라우저 실기기 스모크.

---

## 11. 핸드오프

집토리 subagent 실행 순서 규칙에 따라 분해한다.

### DB → db-architect
- **작업 없음.** 콘텐츠 전용 테이블을 만들지 않는다. 이벤트는 기존 `user_event`(`database.py:612-619`)와 기존 인덱스(`:729-732`)로 충분하다.
- (조건부) §11 Q4에서 `/api/events` 화이트리스트 경로를 선택하는 경우에도 스키마 변경은 없다.

### API → api-developer
- **기본 범위: 작업 없음** (`logEvent` → `/api/log/event`는 event_type 화이트리스트가 없다 — `log.py:24-38`).
- **조건부 작업 1 (G3 해소)**: `POST /api/nudge/score` 응답에 `sigungu_code`(및 필요 시 주소) 추가. SQL은 이미 조회 중이므로(`nudge.py:72`) 응답 dict(`:209-220`)에 키를 더하는 최소 변경. 기존 소비자(프론트 `ScoredApartment` 타입, MCP tool) 영향 확인 필수.
- **조건부 작업 2 (Q4 선택 시)**: `routers/events.py:21-26` `ALLOWED_EVENT_TYPES`에 `content_*` 4종 추가 + payload 계약 문서화.

### 생성기(Python) → api-developer 또는 별도 배치 담당
> 카드 생성기는 `scripts/`(로컬 배치)라 기존 subagent 분류에 정확히 대응하지 않는다. 백엔드/파이썬 담당(api-developer)이 맡되, `web/backend` 배포 제약(외부 모듈 import 금지)과 무관한 로컬 스크립트임을 유의.
- publication dict(§5 스키마)를 만드는 **순수 함수** 분리 — 렌더 함수가 이 dict의 `items`를 소비하도록 변경(이미지/JSON 값 이중 생성 제거).
- `trade-top` 쿼리에 `m.pnu` 추가(G2), `compare` 결과에 top1 `pnu` 보존(G4).
- 검증 함수(필수 필드/중복/포맷/최소 후보 수/caveat) — 실패 시 예외, fallback 금지.
- `--slug --summary --publish --force` CLI 옵션. `--publish` 없이는 기존 동작(reports 이미지만) 유지 — 하위호환.
- 원자적 쓰기: 임시 파일 → 최종 파일 교체. published slug 덮어쓰기는 `--force` 필수.
- cover 이미지를 `web/frontend-next/public/content/instagram/{slug}/cover.png`로 저장(G5).
- 테스트: `scripts/tests/test_generate_insta_cards.py`.

### FE → frontend-developer
> 시작 전 `npm install` 후 `node_modules/next/dist/docs/`(App Router / metadata / static generation) 를 읽을 것 (AGENTS.md 강제 규칙).
- `src/types/instagramContent.ts` — `series` discriminated union, `any` 금지.
- `src/lib/instagramContent.ts` — JSON 정적 import + type guard, `getPublishedPosts()`, `getPublishedPost(slug)`, 딥링크 URL 빌더(typedRoutes 대응: `` `/?${string}` `` 반환 — `PresetTiles.tsx:16-29` 선례).
- `src/app/content/[slug]/page.tsx` — Server Component, `params: Promise<{slug}>` await, `generateStaticParams()`(published만), `dynamicParams = false`, `generateMetadata()`(canonical/OG/article), Article + ItemList JSON-LD.
- `src/app/content/[slug]/_view.tsx` — 시리즈별 표현 분기(조건문 누적 대신 컴포넌트 분리), 공통 골격 공유.
- `src/app/content/[slug]/ContentActions.tsx` — Client Component. CTA(inline/sticky) + 이벤트 로깅만 담당.
- `src/app/content/page.tsx` — 목록(최신순).
- `src/hooks/useBridgeParams.ts` — 필터 allowlist 소비 + 적용 순서 고정(§7) + `content_map_arrival` 로깅. 기존 explore 딥링크 회귀 금지.
- `src/app/sitemap.ts:73-78` — `/content` 및 published 콘텐츠 URL 추가(draft 제외, UTM 미포함).
- (필요 시) `public/_headers` — `/content/instagram/*` 캐시 헤더.

### Test → test-writer
- `scripts/tests/test_generate_insta_cards.py` (§10 케이스 1~2).
- `web/frontend-next/e2e/entry-flows.spec.ts` 확장 또는 `e2e/content-landing.spec.ts` 신설 (§10 케이스 4~5). mock API(`e2e/mock-api.mjs`)에 `/api/log/event` 응답이 이미 있는지 확인 후 필요 시 확장.

### 리뷰 → code-reviewer (최후)

---

## 12. 작업 순서 (실행 계획)

| # | 단계 | 담당 | 의존성 |
|---|---|---|---|
| 0 | (선택) `/api/nudge/score` 응답에 `sigungu_code` 추가 — Q1 결정 시 | api-developer | — |
| 1 | 생성기 publication 모델 + 검증 + pnu 보존(G2/G4) + `--publish` CLI | api-developer(python) | 0 |
| 2 | 생성기 단위 테스트 GREEN + 샘플 draft 1건 산출 | test-writer / 1과 병행 | 1 |
| 3 | 콘텐츠 타입 + 조회 레이어(`types/`, `lib/`) | frontend-developer | 1(스키마 확정) |
| 4 | `/content/[slug]` + `/content` 렌더 | frontend-developer | 3 |
| 5 | 메타데이터·JSON-LD·sitemap | frontend-developer | 4 |
| 6 | 딥링크 확장(`useBridgeParams` 필터 allowlist) | frontend-developer | 4 |
| 7 | 퍼널 이벤트 4종 | frontend-developer | 6 |
| 8 | E2E(신규 + 기존 회귀) | test-writer | 7 |
| 9 | 전체 검증(§10) + `value` 파일럿 1건 발행 | frontend-developer + 사용자 | 8 |
| 10 | 배포 후 인앱 브라우저 스모크 → 1~2주 퍼널 수집 → compare, trade-top 순 확장 | 사용자 | 9 |

DB 단계는 없다(테이블 변경 없음).

---

## 13. 리스크 / 오픈 이슈

### 리스크

| 리스크 | 근거 | 대응 |
|---|---|---|
| **콘텐츠 페이지에서도 Kakao SDK가 로드된다** — 루트 layout 전역 `<Script>` (`layout.tsx:73-78`). "콘텐츠 페이지엔 지도 SDK 없음" 전제가 코드상 성립하지 않는다 | `layout.tsx:73-78` | `afterInteractive`라 첫 페인트는 막지 않지만 인앱 브라우저 대역폭을 소모. 측정 후 필요하면 SDK 로드를 지도 사용 라우트로 한정하는 별도 변경(범위 밖, 후속 이슈) |
| 발행 후 카드/지도 수치 불일치 | 지도는 항상 최신 재계산 | 본문은 불변 스냅샷 + 명시적 고지 |
| 필터 확장으로 기존 `/explore` 딥링크 회귀 | `useBridgeParams.ts:38-78` 단일 effect | allowlist + 기존 E2E 유지 + 적용 순서 테스트 |
| PNG 커밋 누적으로 레포 비대 | `.gitignore:85`가 reports만 제외 | public에는 cover 1장만. 20건 발행 후 재평가 |
| 순위 의미 오해(compare 상위10 평균, value 저가순) | `:543-547`, `:665-666` | `methodology` 필수 필드 + 누락 시 발행 실패 |

### 오픈 이슈 (결정 필요)

- **Q1.** value 후보의 지역 라벨(`item.region`)을 어떻게 채우는가?
  (A) `/api/nudge/score` 응답에 `sigungu_code` 추가(api-developer 최소 변경, `nudge.py:209-220`) / (B) 생성기가 로컬 DB `apartments`에서 pnu로 조회(운영 API와 소스 불일치 가능) / (C) MVP에서 region 생략.
- **Q2.** value 시리즈는 운영 API(점수) + 로컬 DB(price_per_m2) 혼합인데, `data_as_of` 를 단일 값으로 표기해도 되는가? 아니면 소스별 기준일을 caveat에 분리 표기하는가?
- **Q3.** trade-top의 메인 지도 CTA를 무엇으로 할 것인가? 랭킹은 넛지 조건이 아니다. (A) CTA 없이 단지 상세 링크만 / (B) "해당 지역 지도 보기"(sigungu_code만, nudges 없음 → **현재 `useBridgeParams`는 nudges 없으면 아무 것도 하지 않음**(`:45-46`) — 훅 계약 변경 필요) / (C) 사용자가 게시물마다 nudges를 수동 지정.
- **Q4.** 이벤트 수집 경로: `logEvent`(화이트리스트 없음, 백엔드 무변경) vs `/api/events`(화이트리스트, 스키마 검증 강함, 백엔드 변경 필요). 본 PRD는 전자를 기본안으로 제안.
- **Q5.** cover 이미지: `<img>` 유지 vs `next/image` 도입(OpenNext Cloudflare 이미지 최적화 설정 필요, 현 레포에 선례 없음).
- **Q6.** OG 이미지: 인스타 1080×1080을 그대로 쓰면 카톡/트위터 미리보기(1200×630)에서 크롭된다. 생성기가 OG 전용 letterbox 이미지를 추가 생성할지, MVP는 정사각 그대로 둘지.
- **Q7.** 카드 생성기의 발행 실행 주체 — 수동 CLI 유지 vs GitHub Actions 스케줄(현재 워크플로 없음). 로컬 DB(`batch.db`)와 macOS 시스템 폰트(`FONT_PATH = /System/Library/Fonts/...`, `:47`)에 의존하므로 CI 이관은 별도 검토 필요.
- **Q8.** `/content` 목록·상세를 sitemap에 넣는 시점(파일럿 1건부터 vs 3건 이상부터).

### ADR 작성 권고

다음 두 가지는 아키텍처 결정으로 `docs/adr/`에 기록을 권고한다(본 PRD는 권고만 하며 ADR을 직접 작성하지 않는다).

1. **콘텐츠 스냅샷을 DB/CMS가 아닌 레포 커밋 JSON + 빌드타임 SSG로 관리** — 다른 페이지(`apartment`, `region`)가 모두 API+ISR인 것과 다른 방향이므로 근거 기록 필요.
2. **`useBridgeParams` 딥링크 쿼리 계약의 공식화(allowlist)** — 홈 부트스트랩의 외부 진입 인터페이스가 explore/상세/콘텐츠 3곳으로 늘어난다.
