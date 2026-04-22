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
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
