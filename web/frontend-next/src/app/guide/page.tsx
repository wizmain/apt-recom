import type { Metadata } from "next";
import Link from "next/link";
import { BRAND, SITE_URL } from "@/lib/site";
import UsageSection, { usageSteps } from "@/app/_guide/UsageSection";
import McpSection from "@/app/_guide/McpSection";

/**
 * /guide — 사이트 사용 방법 + MCP 서버 연결 안내.
 *
 * 초보자와 MCP 연동 개발자 모두 한 페이지에서 필요한 정보를 얻을 수 있도록 구성.
 * Server Component — 외부 API 호출 없이 완전 정적.
 */

export const metadata: Metadata = {
  title: "사용 가이드",
  description:
    "집토리 사용 방법과 MCP (Model Context Protocol) 서버 연결 방법을 안내합니다. Claude Desktop·Cursor·Claude Code 에서 집토리 아파트 데이터를 직접 조회할 수 있습니다.",
  alternates: { canonical: "/guide" },
  openGraph: {
    title: `사용 가이드 | ${BRAND.name}`,
    description:
      "지도·필터·AI 챗봇 사용법과 MCP 서버 연결 가이드 (Claude Desktop·Cursor·Claude Code·Python SDK).",
    url: "/guide",
    type: "article",
  },
};

const howToJsonLd = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: `${BRAND.name} 사용 방법`,
  description:
    "라이프스타일 기반 아파트 탐색부터 AI 챗봇 질의, MCP 서버 연결까지 집토리 사용법을 단계별로 안내합니다.",
  inLanguage: BRAND.locale,
  url: `${SITE_URL}/guide`,
  step: usageSteps.map((step, idx) => ({
    "@type": "HowToStep",
    position: idx + 1,
    name: step.title,
    text: step.body,
    url: `${SITE_URL}/guide#usage`,
  })),
};

export default function GuidePage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:py-12 text-gray-900">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(howToJsonLd) }}
      />

      <h1 className="text-3xl font-bold">집토리 사용 가이드</h1>
      <p className="mt-4 text-base leading-relaxed text-gray-700">
        {BRAND.name} 의 지도·필터·AI 챗봇 사용 방법과 MCP (Model Context Protocol)
        서버 연결 방법을 한 페이지에 정리했습니다. 처음이신 분은 아래{" "}
        <Link href="#usage" className="text-blue-600 hover:underline">
          사용 방법
        </Link>
        부터, AI 에이전트에서 직접 조회하고 싶다면{" "}
        <Link href="#mcp" className="text-blue-600 hover:underline">
          MCP 연결 안내
        </Link>
        로 이동하세요.
      </p>

      <UsageSection />
      <McpSection />

      <div className="mt-12 border-t border-gray-200 pt-6 text-sm text-gray-600">
        더 자세한 서비스 소개는{" "}
        <Link href="/about" className="text-blue-600 hover:underline">
          서비스 소개
        </Link>
        {" "}페이지에서 확인할 수 있습니다.
      </div>
    </main>
  );
}
