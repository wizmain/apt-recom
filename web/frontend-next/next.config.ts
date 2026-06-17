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
      {
        // SEP-2127 MCP Server Card — agent 발견 용 정적 JSON.
        // browser-based 클라이언트의 fetch 를 위해 CORS 와 Content-Type 명시.
        source: "/.well-known/mcp/server-card.json",
        headers: [
          { key: "Content-Type", value: "application/json; charset=utf-8" },
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, OPTIONS" },
          { key: "Access-Control-Allow-Headers", value: "Content-Type" },
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
      // llms.txt — agent 가 읽는 사이트 설명 파일.
      // charset 미지정 시 일부 클라이언트(예: Python requests)가 text/* 를
      // ISO-8859-1 로 디코딩해 한글이 깨지므로 charset=utf-8 을 명시한다.
      // cross-origin agent fetch 를 위해 CORS 도 허용.
      // headers() 의 source 는 glob 만 지원(정규식 불가) → 경로별 항목 분리.
      {
        source: "/llms.txt",
        headers: [
          { key: "Content-Type", value: "text/plain; charset=utf-8" },
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, OPTIONS" },
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
      {
        source: "/.well-known/llms.txt",
        headers: [
          { key: "Content-Type", value: "text/plain; charset=utf-8" },
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, OPTIONS" },
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
      // skill.md — agent 가 읽어 apt-recom API 사용법을 따르는 Agent Skill 문서.
      // text/markdown + charset=utf-8 + CORS. 편의 경로(/skill.md)와
      // 스펙 정합 경로(/.well-known/skills/apt-recom/skill.md) 둘 다 서빙.
      {
        source: "/skill.md",
        headers: [
          { key: "Content-Type", value: "text/markdown; charset=utf-8" },
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, OPTIONS" },
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
      {
        source: "/.well-known/skills/apt-recom/skill.md",
        headers: [
          { key: "Content-Type", value: "text/markdown; charset=utf-8" },
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, OPTIONS" },
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
    ];
  },
};

export default nextConfig;
