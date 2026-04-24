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

  // www → apex canonical redirect 는 `src/middleware.ts` 에서 edge runtime 으로 처리.
  // Next.js 16 의 `proxy` 파일 규약은 Node.js 런타임 전용이며 OpenNext Cloudflare
  // 에서 지원되지 않아 `middleware.ts` 를 유지. 자세한 이유는 `src/middleware.ts`
  // 상단 주석 참조.

  images: {
    remotePatterns: [
      // 카카오 CDN — 단지 사진 도입 시 활용
      { protocol: "https", hostname: "**.daumcdn.net" },
      { protocol: "https", hostname: "**.kakaocdn.net" },
    ],
  },
};

export default nextConfig;
