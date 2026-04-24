import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Host-based canonical redirect — `www.apt-recom.kr` → `apt-recom.kr`.
 *
 * Next.js 의 `redirects()` config 에서 `:path*` placeholder 치환이 OpenNext
 * Cloudflare 런타임에서 일부 케이스에 literal 로 나가는 이슈 회피.
 * Proxy 는 edge 레벨에서 실행되며 OpenNext 가 안정적으로 지원.
 *
 * 308 (permanent) — SEO canonical + 브라우저 메서드 보존.
 *
 * Next.js 16: `middleware` 파일 규약이 `proxy` 로 변경됨 (동작 동일).
 */
export function proxy(request: NextRequest) {
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
