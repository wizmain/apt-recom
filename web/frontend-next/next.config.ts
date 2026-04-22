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

  // AAO 관점: canonical 호스트 단일화. www/vercel 도메인 진입 시 apex 로 영구 이동.
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "www.apt-recom.kr" }],
        destination: "https://apt-recom.kr/:path*",
        permanent: true,
      },
    ];
  },

  images: {
    remotePatterns: [
      // 카카오 CDN — 단지 사진 도입 시 활용
      { protocol: "https", hostname: "**.daumcdn.net" },
      { protocol: "https", hostname: "**.kakaocdn.net" },
    ],
  },
};

export default nextConfig;
