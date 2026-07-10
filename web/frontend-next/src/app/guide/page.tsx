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

// 자주 묻는 질문 — 본문에 그대로 렌더하고 FAQPage JSON-LD 로도 구조화한다.
// (Google FAQ 리치결과는 2023-08 이후 일반 사이트 미노출 — 목적은 리치결과가
// 아니라 LLM 질의 응답 인용용 SSR 텍스트이며, 마크업은 부가 신호.)
const faqItems = [
  {
    q: "집토리는 어떤 데이터를 사용하나요?",
    a: "국토교통부 실거래가(매매·전월세), K-APT 공동주택 관리비·시설 정보, 공공데이터포털 안전 시설물(CCTV 등), 시·도 교육청 학군 배정 정보 등 공공 데이터를 사용합니다. 원천 데이터의 출처는 서비스 소개 페이지에 명시되어 있습니다.",
  },
  {
    q: "라이프스타일 추천 점수(NUDGE 점수)는 무엇인가요?",
    a: "가성비·신혼육아·학군·시니어 같은 라이프스타일 유형별로 지하철·학교·병원·공원 등 시설 접근성과 가격·안전 지표를 가중 합산한 0~100 점수입니다. 유형마다 가중치가 달라 같은 단지라도 라이프스타일에 따라 점수가 다릅니다.",
  },
  {
    q: "금액과 면적 단위는 무엇인가요?",
    a: "금액은 만원 단위(예: 120,000 = 12억 원), 면적은 전용면적 제곱미터(㎡) 기준입니다.",
  },
  {
    q: "Claude나 Cursor에서 집토리 MCP는 어떻게 연결하나요?",
    a: "MCP 서버 주소 https://api.apt-recom.kr/mcp/ 를 MCP 클라이언트 설정에 추가하면 됩니다(인증 불필요, Streamable HTTP). 자세한 클라이언트별 설정은 이 페이지의 MCP 연결 안내 섹션을 참고하세요.",
  },
  {
    q: "추천 결과는 투자 자문인가요?",
    a: "아닙니다. 집토리의 점수와 추천은 공공 데이터를 요약한 참고 정보이며, 투자 권유나 자문이 아닙니다. 실제 거래 결정 전에는 반드시 실물 확인과 전문가 상담을 권장합니다.",
  },
];

const faqJsonLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map((item) => ({
    "@type": "Question",
    name: item.q,
    acceptedAnswer: { "@type": "Answer", text: item.a },
  })),
};

export default function GuidePage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:py-12 text-gray-900">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify([howToJsonLd, faqJsonLd]),
        }}
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

      <section id="faq" className="mt-12">
        <h2 className="text-2xl font-bold">자주 묻는 질문</h2>
        <dl className="mt-4 space-y-5">
          {faqItems.map((item) => (
            <div key={item.q}>
              <dt className="font-semibold text-gray-900">{item.q}</dt>
              <dd className="mt-1 text-base leading-relaxed text-gray-700">
                {item.a}
              </dd>
            </div>
          ))}
        </dl>
      </section>

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
