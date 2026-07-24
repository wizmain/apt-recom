# toss-miniapp 콘텐츠 추가 — WebView 임베드 설계

- 작성일: 2026-07-24
- 상태: 설계 확정 (구현 플랜 대기)
- 관련: frontend-next `/content` 아티클 기능, toss-miniapp v1

## 1. 목표

frontend-next에 있는 "숫자로 보는 집 이야기" 콘텐츠(카드뉴스 기반 아티클)를
toss-miniapp에서도 볼 수 있게 한다.

- 미니앱은 **네이티브 목록**만 렌더링한다.
- 아티클 **상세는 frontend-next의 웹 페이지를 WebView로 임베드**한다.
- 새 아티클 발행 시 **미니앱 재심사 없이** 목록에 반영된다.

## 2. 배경 / 현재 구조

### 콘텐츠 (frontend-next)
- 저작 소스: 정적 파일 `web/frontend-next/src/content/instagram/posts.json` (현재 published 4건).
- 로더: `@/lib/instagramContent`의 `getPublishedPosts()` — 로드 시점 전체 검증.
- 목록: `/content`, 상세: `/content/[slug]` (7개 섹션 컴포넌트로 구조 렌더, ISR 패턴 — 커밋 0c9fa57).
- 커버 이미지: `posts.json`의 `cover_image` = frontend-next public 하위 상대경로
  (예: `/content/instagram/<slug>/cover.png`).
- 백엔드 콘텐츠 API 없음 — 콘텐츠는 웹 앱에 정적으로 내장됨.

### toss-miniapp (React Native / granite)
- 이미 **WebView로 백엔드 서빙 HTML을 임베드**하는 패턴 사용
  (`src/components/AptLocationMap.tsx` — 지도 `/api/map`).
  `@granite-js/native/react-native-webview` 사용.
- 백엔드 데이터는 `src/api/client.ts`의 `request()` + `useApi` 훅으로 호출.
  `API_BASE = 'https://api.apt-recom.kr'`.
- 웹과 타입/경로는 **inline 복사**로 공유 (`src/shared/`, Metro symlink 제약 — `shared/README.md`).
- 파일 기반 라우팅: **진입점은 루트 `pages/*.tsx`**(`src/pages/*`를 재수출하는 shim),
  실제 화면은 `src/pages/*.tsx`가 `createRoute('/path', …)`로 선언.
  `src/router.gen.ts`(자동 생성, 커밋됨)가 루트 `pages/`를 스캔해 타입 레지스트리를 만든다 —
  새 화면은 루트 wrapper + src 구현 + `router.gen.ts` 재생성이 함께 필요.

### 제약 (필수)
- **백엔드는 Railway 배포 시 `web/backend/` 디렉토리만 존재.**
  `web/backend/` 런타임 코드에서 `web/frontend-next/**` 등 외부 파일을 읽거나 import 할 수 없다.
  (`web/backend/CLAUDE.md`)

## 3. 아키텍처 개요

```
[저작] posts.json (frontend-next)
   │  ← --publish 가 발행과 함께 인덱스 생성 (CI --check 로 드리프트 차단)
   ▼
web/backend/content/content_index.json  (생성 아티팩트, 커밋)
   │  ← 런타임 읽기
   ▼
GET /api/content  (백엔드)  ──▶  toss-miniapp 네이티브 목록 (홈 미리보기 + /content 화면)
                                        │ 카드 탭
                                        ▼
                          WebView: apt-recom.kr/content/<slug>/embed
                                (frontend-next 전용 static 임베드 라우트 —
                                 SiteNav·CTA·외부 링크 모두 서버 렌더에서 제거)
```

핵심 원칙: **콘텐츠 본문은 웹이 렌더링한다.** 미니앱은 목록만 네이티브로 그리고 상세는 위임한다.

## 4. 컴포넌트 설계

### A. 데이터 소스 (백엔드)

`posts.json`을 단일 저작 소스로 유지하고, 백엔드용 메타데이터는 **생성물**로 취급한다
(`router.gen.ts`와 동일 철학 — 손으로 관리하는 중복 없음).

1. **`scripts/sync_content_index.py`** — 인덱스 생성/검증 도구(백엔드 런타임 아님).
   - 입력: `web/frontend-next/src/content/instagram/posts.json`
   - 처리: `status == "published"` 항목만, 메타 필드만 추출 → `published_at` DESC 정렬.
   - 출력: `web/backend/content/content_index.json` **원자적 쓰기**(tmp write→rename).
   - `--check` 모드: 파일을 다시 쓰지 않고, 현재 커밋된 인덱스가 `posts.json` 투영과
     일치하는지만 비교. 불일치 시 비-0 종료 → **CI 가 드리프트를 병합 전에 차단**.
   - **자동화 (P1-3 반영)**: `scripts/insta_cards/cli.py`의 `--publish` 경로가
     `publish_to_frontend()` 성공 직후 이 생성을 호출한다. 인덱스는 `posts.json`의
     순수 투영이라 언제 재생성해도 안전하며, `--check`가 최종 안전망이다.
     발행자가 수동 실행을 잊어도 CI 가 막는다.

2. **`web/backend/content/content_index.json`** — 커밋되는 생성 아티팩트.
   - 항목 필드: `slug`, `series`, `title`, `eyebrow`, `summary`,
     `cover_image`(상대경로 원본 보존), `cover_alt`, `data_as_of`, `published_at`.

3. **`web/backend/routers/content.py`** — `GET /api/content`
   - `content_index.json` 읽기 → `published_at` 내림차순 정렬.
   - `cover_image`는 `FRONTEND_BASE_URL`(기본 `https://apt-recom.kr`, 환경변수)을 붙여
     **절대 URL**(`cover_image_url`)로 응답 → 미니앱이 origin을 몰라도 이미지 로드 가능.
   - **응답 계약 (P1-4 반영)** — 빈 목록과 배포 결함을 구분한다:
     - 파일이 있고 내용이 `[]`(정상적으로 발행분 없음) → `200 []`.
     - **파일 누락 / JSON 손상 / 스키마 오류**(커밋·패키징·발행 실패의 신호) →
       **에러 로그 + 5xx**. 조용히 `[]`로 감추지 않는다.
   - `main.py`에 `app.include_router(content.router, prefix="/api")` 등록.
   - `FRONTEND_BASE_URL`은 현재 `sitemap.py`에만 있음 → 공용 상수/헬퍼로 추출해 중복 제거.

**배포 순서 (운영 절차)**: Cloudflare(웹)와 Railway(백엔드) 배포가 어긋나면
API 목록엔 새 slug가 있으나 웹 상세가 아직 404인 구간이 생길 수 있다.
발행 절차에 "웹(Cloudflare) 배포 확인 후 백엔드 노출" 순서를 명시한다.

응답 항목 shape:
```json
{
  "slug": "value-seoul-20260718",
  "series": "value",
  "title": "…",
  "eyebrow": "…",
  "summary": "…",
  "cover_image_url": "https://apt-recom.kr/content/instagram/value-seoul-20260718/cover.png",
  "cover_alt": "…",
  "data_as_of": "…",
  "published_at": "2026-07-23"
}
```

4. **테스트** (`web/backend/tests/test_core.py`): `GET /api/content`가
   배열 반환 / published-only / `published_at` 내림차순 / `cover_image_url` 절대 URL 포함 확인.

### B. embed 라우트 + 네비게이션 정책 (frontend-next) — P1-2 반영

`?embed=1` 쿼리는 `searchParams` 접근으로 페이지를 dynamic 으로 전환시켜 ISR 을 깬다.
대신 **전용 static 임베드 라우트**를 둔다.

- **`/content/[slug]/embed`** — `generateStaticParams`로 정적 생성(ISR 유지).
  기존 `page.tsx`의 메타/`notFound`/조회 로직을 공유하고, `ContentView`를 `embed` prop 으로 렌더.
- **`ContentView(embed=true)`가 서버 렌더 단계에서 제거/치환하는 항목** (현재 `ContentView.tsx` 구성 기준):
  - `SiteNav` — 제거 (웹 메뉴).
  - `DashboardCta` (trade_top) — 제거 (웹 대시보드로 이탈).
  - `ContentActions` (map CTA, `href=/?…` 웹 홈) — 제거.
  - `ApartmentLink` (`/apartment/{pnu}`) — 링크 대신 **plain text**(span)로 렌더.
  - `RelatedContent` — 링크를 `/content/{slug}/embed`로 (embed 유지) 하여 콘텐츠 내 이동은 임베드에 머문다.
- 근거: 이 CTA/링크들은 미니앱이 이미 네이티브로 제공하는 기능(지도·대시보드·단지 상세)과 중복이며,
  WebView 안에서 누르면 네이티브 상세 라우트와 분리되어 흐름이 풀린다. Apps-in-Toss 도
  핵심 기능이 외부 웹 이동에 의존하지 않기를 요구한다.
- **미니앱 측 방어선(defense-in-depth)**: WebView 가 `onShouldStartLoadWithRequest`로
  `https://apt-recom.kr/content/*/embed` 외 이동을 차단한다(§4C). 서버에서 링크를 제거해도
  누락 링크가 있으면 여기서 막힌다.
- 범위: 네비게이션 억제 + 정적 임베드 라우트. 웹 본문 재디자인 아님.

### C. toss-miniapp

**라우트 등록 구조 (P1-1 반영)**: Granite 파일 라우터의 진입점은 **루트 `pages/*.tsx`**이며,
각 파일은 `src/pages/*`를 재수출하는 얇은 shim(`export { Route } from 'pages/<name>'`)이다.
`src/router.gen.ts`(자동 생성, 커밋)가 이들을 스캔해 타입 레지스트리를 만든다.
→ **새 화면마다 루트 wrapper + src 구현 2개가 필요**하고, `router.gen.ts`는 손으로 편집하지 않고
**Granite(`granite dev`/`build`)로 재생성**한다.

| 파일 | 책임 |
|------|------|
| `src/shared/api/paths.ts` (+ `packages/shared/api/paths.ts`) | `content: () => '/api/content'` 추가 (양쪽 동기화) |
| `src/api/client.ts` | `SITE_BASE = 'https://apt-recom.kr'` + `buildSiteUrl(path, query)` 추가 (쿼리 인코딩 포함, WebView URL 조립용) |
| `src/types/content.ts` | `ContentListItem` 타입 정의 (API 응답 shape) |
| `src/components/ContentCard.tsx` | 카드 UI (커버 이미지·eyebrow·title·summary·기준일). **홈 미리보기와 목록 화면이 공유** |
| `pages/content.tsx` (루트 wrapper) | `export { Route } from 'pages/content'` 재수출 shim |
| `src/pages/content.tsx` | 목록 화면 `/content` — `useApi<ContentListItem[]>(apiPaths.content())`, 카드 탭 → 상세 이동 |
| `pages/content-article.tsx` (루트 wrapper) | `export { Route } from 'pages/content-article'` 재수출 shim |
| `src/pages/content-article.tsx` | WebView 상세 화면 — route param `slug` → `${SITE_BASE}/content/${slug}/embed` 임베드 (§ WebView 화면) |
| `src/pages/index.tsx` | 홈에 "숫자로 보는 집 이야기" 섹션 추가 — 최신 2건 `ContentCard` + "전체 보기" → `navigate('/content')` |
| `src/router.gen.ts` | **Granite 로 재생성** — `/content`·`/content-article` 등록 (수동 편집 금지) |

- 별도 훅은 만들지 않는다 — 기존 관례대로 페이지에서 `useApi`를 직접 사용.
- 라우트 이름: 웹은 `/content/[slug]`지만 미니앱 flat 라우팅에서는 상세를 `/content-article`로 둔다
  (`/content` 목록과 충돌 회피).

**WebView 상세 화면 (`src/pages/content-article.tsx`)**
- **slug 검증 (P2-2 반영)**: `validateParams`에서 문자열 여부만 보지 않고 원본과 동일한
  slug 정규식 `^[a-z0-9]+(-[a-z0-9]+)*$`(`lib/instagramContent`의 `SLUG_PATTERN`)로 검증.
  불일치 시 빈 slug 처리 → 에러 상태. `parserParams`는 identity(문자열 유지, `apt.tsx` 패턴).
- URL 조립은 문자열 보간 대신 `buildSiteUrl('/content/' + slug + '/embed')` (검증된 slug + 인코딩).
- **로드 상태/에러 (P2-1 반영 — `AptLocationMap`에는 선례 없음, 신규 설계)**:
  - `onLoadStart`/`onLoadEnd`로 로딩 인디케이터, `onError`(네트워크)·`onHttpError`(404/5xx) 각각 처리.
  - 재시도: `WebView.reload()` ref 또는 `key` 재마운트로 명시적 재시도 버튼 제공.
  - `onShouldStartLoadWithRequest`: `https://apt-recom.kr/content/*/embed`만 허용,
    그 외 origin/경로 이동은 차단(§4B 방어선).

## 5. 데이터 흐름

1. 홈 mount → `GET /api/content` → 미리보기 최신 2건 렌더 + "전체 보기".
2. "전체 보기" 탭 → `/content` 목록 화면 → `GET /api/content` → 전체 카드.
3. 카드 탭 → `/content-article?slug=X` → WebView가 `apt-recom.kr/content/X/embed` 로드 → 웹이 풀 렌더.
4. 커버 이미지는 API가 준 절대 URL(`cover_image_url`, apt-recom.kr)에서 로드.

홈 미리보기와 목록 화면이 각각 `/api/content`를 호출한다(작은 페이로드라 허용). 필요 시 `?limit`은 후속.

## 6. 에러 처리

- API 실패 (5xx/네트워크)
  - 목록 화면: 기존 `Status`/empty 패턴 재사용 + **에러 상태 명시**(재시도) — 인앱에서도 조용히 사라지지 않음.
  - 홈 미리보기: 실패 시 **섹션 자체를 숨김** — 홈 주 흐름(거래·검색)을 방해하지 않음.
- 백엔드 인덱스 상태 구분 (P1-4)
  - 파일 있고 `[]`: `200 []` → 미니앱은 "발행된 콘텐츠 없음" 표시(정상).
  - 파일 누락/손상/스키마 오류: **로그 + 5xx** → 배포 결함이 드러남. CI 가 누락·드리프트를 병합 전에 먼저 차단.
- WebView 로드 실패: `onError`/`onHttpError` 상태 + `WebView.reload()`(또는 key 재마운트) 재시도 버튼 (신규 설계, §4C).

## 7. 테스트 (P2-3 반영)

- **동기화 스크립트 `sync_content_index.py`** — 로직의 실제 검증 지점(이미 필터된 API 결과만으로는
  published-only를 검증할 수 없음). fixture 기반 단위 테스트:
  - draft fixture 가 결과에서 **제외**되는지 (published-only).
  - `published_at` DESC **정렬** 순서.
  - 필수 메타 필드 존재/누락 처리.
  - **원자적 쓰기**(tmp→rename) — 중간 실패 시 잔존물 없음.
  - `--check`: 일치 시 0 종료, 드리프트 시 비-0 종료.
- **백엔드** (`test_core.py`): `GET /api/content` 구조/정렬/절대 URL(`cover_image_url`);
  **인덱스 계약** — 파일 `[]` → `200 []`, 파일 누락/손상 → 5xx.
- **frontend-next E2E** (`e2e/`, 기존 `content-landing.spec.ts` 확장):
  - 일반 상세(`/content/[slug]`) — `SiteNav` **노출**.
  - 임베드 상세(`/content/[slug]/embed`) — `SiteNav`·map CTA·DashboardCta **미노출**, 단지명 plain text.
  - 임베드의 관련 아티클 링크가 `/content/{slug}/embed`로 **embed 유지**.
- **frontend-next 타입/빌드**: `typecheck` 스크립트가 없으므로 `npx tsc --noEmit` 사용(또는 스크립트 추가).
  ISR 보존 확인은 `npm run build` 로 임베드 라우트가 정적 생성되는지 검증.
- **미니앱**: `tsc --noEmit` 통과. WebView·네비게이션·에러 재시도는 수동 확인.

## 8. 범위 밖 (YAGNI)

- 아티클 섹션의 네이티브 재구현 (WebView에 위임).
- 콘텐츠용 DB 테이블 (문서형 4건 → 파일로 충분. 볼륨 증가 시 재검토).
- 오프라인 캐싱, 콘텐츠 검색/필터.
- 백엔드가 요청 때 frontend 목록 JSON을 fetch+캐시하는 방식(런타임 결합 발생) — 보류.

## 9. 열린 구현 세부 (플랜에서 확정)

- `/content/[slug]/embed` 라우트와 기존 `page.tsx`의 조회/메타 로직 공유 방식
  (공통 함수 추출 vs 라우트별 중복 최소화).
- `granite dev`/`build` 재생성을 CI/로컬 어느 단계에서 강제할지 (router.gen 드리프트 방지).
- `sync_content_index.py --check`를 어느 CI 워크플로에 추가할지.
