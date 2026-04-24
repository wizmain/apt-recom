# Cloudflare Workers 배포 (OpenNext)

Next.js 16 `apt-recom-next` 를 Cloudflare Workers 에 OpenNext adapter 로 배포한다.

## 구성 파일

- `wrangler.jsonc` — Worker 이름/엔트리/asset 바인딩/환경변수
- `open-next.config.ts` — OpenNext 빌드 옵션 (현재 기본값)
- `.gitignore` — `.open-next/`, `.dev.vars`, `.wrangler/` 제외
- `.dev.vars` — 로컬 프리뷰용 환경변수 (git 미추적)
- `../../.github/workflows/ci-frontend-next.yml` — PR typecheck/build + main push 자동 배포

## 초기 1회 설정

### 1. Cloudflare API Token 발급

1. <https://dash.cloudflare.com/profile/api-tokens> 접속
2. **Create Token** → **Edit Cloudflare Workers** 템플릿 선택
3. 계정/존 permissions 확인 후 Create
4. 발급된 토큰과 Account ID 복사

### 2. GitHub Secrets 등록

`wizmain/apt-recom` 저장소 → Settings → Secrets and variables → Actions → New repository secret:

- `CLOUDFLARE_API_TOKEN` — 위 토큰
- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare 대시보드 우측 하단 Account ID
- `KAKAO_MAPS_APPKEY` — `832af9764dadaf139a8e82517d49e9f3` (도메인 등록된 appkey)

### 3. Worker 최초 배포 (로컬)

```bash
cd web/frontend-next
npx wrangler login             # 브라우저 OAuth
npm run cf:build               # .open-next/ 생성
npx wrangler deploy            # 최초 배포 — Worker 프로젝트 생성
```

배포 완료 시 워커 URL 출력 (예: `https://apt-recom-next.<subdomain>.workers.dev`).

### 4. 커스텀 도메인 연결

Cloudflare 대시보드 → Workers & Pages → `apt-recom-next` → Settings → Triggers → Custom Domains → Add `apt-recom.kr` (및 `www.apt-recom.kr`).

Next `next.config.ts` 의 `redirects()` 가 `www` → apex 301 을 처리하므로 두 도메인 모두 워커에 연결.

### 5. 기존 Vite Pages 프로젝트 정리

기존 `web/frontend/` 를 서빙하던 Cloudflare Pages 프로젝트에서 `apt-recom.kr` 커스텀 도메인 해제 (트래픽이 새 워커로 옮겨가도록). 전환 확인 후 Pages 프로젝트 삭제 또는 보존.

## 일상 워크플로우

- **PR**: `web/frontend-next/**` 변경 시 `ci-frontend-next.yml` 자동 실행 (lint + tsc + build). 빌드 실패 시 머지 차단.
- **main 머지**: 자동으로 OpenNext 빌드 + `wrangler deploy` 실행 → 프로덕션 Worker 업데이트.
- **프리뷰 URL**: `wrangler-action` 기본은 프로덕션 배포. 프리뷰가 필요하면 `command: versions upload` 또는 환경 분리 설정 추가.

## 로컬 프리뷰

```bash
npm run cf:build && npm run cf:preview   # http://localhost:8787
```

`.dev.vars` 파일의 env 값이 로컬 워커에 주입된다.

## 환경변수 관리

| 변수 | 위치 | 값 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `wrangler.jsonc` `vars` | `https://api.apt-recom.kr` |
| `NEXT_PUBLIC_SITE_URL` | `wrangler.jsonc` `vars` | `https://apt-recom.kr` |
| `NEXT_PUBLIC_KAKAO_MAPS_APPKEY` | Cloudflare Secret (`wrangler secret put …`) 또는 GHA secret 빌드 시 주입 | 도메인 등록된 appkey |

Public 아닌 민감 키는 반드시 `wrangler secret put` 으로 Worker secret 에 저장 (plaintext vars 에 넣지 않음).

## 트러블슈팅

- **`peerDependencies` 경고 (wrangler 4.84.1 요구)**: 현재 4.83.0 사용 중이지만 기능상 문제 없음. npm registry 제한으로 최신 버전 설치 불가 시 유지.
- **`Failed to set Next.js data cache … 2MB` 경고**: 빌드 시점 sitemap fetch 의 응답이 2MB 초과라 data cache 생략. 런타임엔 영향 없음.
- **Kakao Maps appkey domain-restricted**: 프로덕션은 `apt-recom.kr` 로 등록된 appkey 사용 → 정상. 프리뷰/워커 서브도메인(`*.workers.dev`) 은 Kakao 콘솔에 추가 도메인 등록 필요.
- **ISR 캐시**: 기본값은 메모리 캐시(인스턴스 수명). 프로덕션 규모 ISR 이 필요하면 `open-next.config.ts` 에 R2 또는 Workers KV 기반 `incrementalCache` 설정.
