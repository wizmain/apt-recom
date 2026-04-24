import type { NextConfig } from "next";

/**
 * 집토리 Next.js 설정.
 *
 * - `typedRoutes`: Next.js 16 에서 타입 안전 라우팅 (실험적 아님, 권장).
 * - `redirects`: www.apt-recom.kr → apt-recom.kr 301 (canonical 단일화).
 * - `images`: Kakao CDN 도메인 허용 (추후 단지 사진 도입 시).
 */

const nextConfig: NextConfig = {
  typedRoutes: true,

  // www → apex canonical redirect 는 `src/middleware.ts` 에서 처리.
  // Next.js `redirects()` 의 `:path*` placeholder 치환이 OpenNext Cloudflare
  // 런타임에서 literal 로 나가는 이슈가 있어 middleware 방식으로 이관.

  images: {
    remotePatterns: [
      // 카카오 CDN — 단지 사진 도입 시 활용
      { protocol: "https", hostname: "**.daumcdn.net" },
      { protocol: "https", hostname: "**.kakaocdn.net" },
    ],
  },
};

export default nextConfig;
