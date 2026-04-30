import type { NextConfig } from "next";

/**
 * 집토리 Next.js 설정.
 *
 * - `typedRoutes`: Next.js 16 에서 타입 안전 라우팅 (실험적 아님, 권장).
 * - `redirects`: www.apt-recom.kr → apt-recom.kr 301 (canonical 단일화).
 * - `images`: Kakao CDN 도메인 허용 (추후 단지 사진 도입 시).
 * - `headers`: 홈페이지 `/` 응답에 RFC 8288 Link 헤더를 부착해 agent 가
 *   OpenAPI 스펙·Swagger 문서·llms.txt 를 자동 발견하게 한다.
 */

// RFC 8288 Link header — IANA registered relation types 만 사용.
// 다중 Link 헤더 대신 단일 헤더 + 콤마 결합 (OpenNext 헤더 직렬화 호환).
const AGENT_DISCOVERY_LINK = [
  '<https://api.apt-recom.kr/openapi.json>; rel="service-desc"; type="application/json"',
  '<https://api.apt-recom.kr/docs>; rel="service-doc"',
  '</.well-known/llms.txt>; rel="describedby"; type="text/plain"',
  // RFC 9727 §3 — Publisher 의 API catalog 위치 광고
  '</.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json"',
].join(", ");

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

  async headers() {
    return [
      {
        source: "/",
        headers: [{ key: "Link", value: AGENT_DISCOVERY_LINK }],
      },
    ];
  },
};

export default nextConfig;
