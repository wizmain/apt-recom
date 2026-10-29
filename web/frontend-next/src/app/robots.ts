import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

/**
 * /robots.txt — Next.js 16 MetadataRoute.Robots 규약.
 *
 * AAO Phase 1 정책 그대로 유지:
 * - 전체 User-agent 에 대해 기본 Allow + /admin/ /api/ Disallow.
 * - 주요 AI 에이전트(ClaudeBot/GPTBot/PerplexityBot 등) 를 명시적 Allow 로 중복 선언.
 *   Cloudflare 등 중간 계층이 AI bot 만 골라 차단하는 시그니처 기반 기능이 있을 때
 *   명시적 Allow 로 의도 노출.
 * - Sitemap 지시어: 같은 host 의 /sitemap.xml.
 * - 서비스 노출에 기여하지 않는 SEO 분석 크롤러는 전체 Disallow.
 *   AhrefsBot 이 /apartment/* 를 대량 크롤링해 Workers 무료 플랜 CPU 한도
 *   초과(503)를 반복 유발 — 2026-10-26~28 /apartment 요청의 86% (2026-10-29).
 *
 * 이 파일은 기본적으로 정적 캐시됨 — SITE_URL 이 빌드타임에 결정.
 */
export default function robots(): MetadataRoute.Robots {
  const aiAgents = [
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "Claude-Web",
    "anthropic-ai",
    "PerplexityBot",
    "Google-Extended",
    "Applebot-Extended",
    "CCBot",
    "Bytespider",
    "Amazonbot",
    "FacebookBot",
  ];
  const blockedCrawlers = ["AhrefsBot"];

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/admin/", "/api/"],
      },
      ...aiAgents.map((agent) => ({
        userAgent: agent,
        allow: "/",
      })),
      ...blockedCrawlers.map((agent) => ({
        userAgent: agent,
        disallow: "/",
      })),
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
