import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Host-based canonical redirect — `www.apt-recom.kr` → `apt-recom.kr`.
 *
 * Next.js 의 `redirects()` config 에서 `:path*` placeholder 치환이 OpenNext
 * Cloudflare 런타임에서 일부 케이스에 literal 로 나가는 이슈 회피.
 * Middleware 는 edge runtime 에서 실행되어 OpenNext 가 안정적으로 지원.
 *
 * 308 (permanent) — SEO canonical + 브라우저 메서드 보존.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * Next.js 16 에서 `middleware` 파일 규약이 `proxy` 로 변경되며 deprecation
 * 경고가 발생한다 (build log 의 "middleware-to-proxy" 안내).
 *
 * 그러나 현 시점(Next 16.2.3) 의 `proxy` 는 **Node.js 런타임 전용이며 edge
 * runtime 설정이 불가능**하다. 이는 공식 업그레이드 가이드(version-16.md) 에
 * 다음과 같이 명시되어 있다:
 *
 *   > The `edge` runtime is NOT supported in `proxy`. The `proxy` runtime is
 *   > `nodejs`, and it cannot be configured. If you want to continue using the
 *   > `edge` runtime, keep using `middleware`. We will follow up on a minor
 *   > release with further `edge` runtime instructions.
 *
 * OpenNext Cloudflare 는 Node.js middleware 를 지원하지 않으므로
 * (`ERROR Node.js middleware is not currently supported. Consider switching to
 * Edge Middleware.`) `proxy.ts` 로 이관하면 배포가 실패한다.
 *
 * → 이 파일을 `middleware.ts` 로 유지하고, Next.js 가 proxy 에 edge runtime
 * 지원을 추가할 때까지 deprecation 경고를 감내한다.
 * ─────────────────────────────────────────────────────────────────────────────
 */
export function middleware(request: NextRequest) {
  const host = request.headers.get("host");
  if (host === "www.apt-recom.kr") {
    const url = request.nextUrl.clone();
    url.host = "apt-recom.kr";
    url.protocol = "https:";
    return NextResponse.redirect(url, 308);
  }
  return NextResponse.next();
}

/**
 * 정적 자원(`_next/*`, 이미지, favicon 등)은 매칭 제외 — redirect 영향 없이
 * 직접 서빙되게 한다.
 */
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico)$).*)",
  ],
};
