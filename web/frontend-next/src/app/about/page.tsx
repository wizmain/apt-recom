import type { Metadata } from "next";
import { BRAND, SITE_URL } from "@/lib/site";

/**
 * /about — Entity Home (AAO Phase 2).
 *
 * agent 가 "집토리가 뭐 하는 서비스" 를 즉시 이해할 수 있도록 조직·데이터 출처·
 * 스코어링 방법론·커버리지를 한 페이지에 구조화. AboutPage + Organization
 * JSON-LD 로 명시적 메타 전달.
 *
 * Server Component — 서버 렌더 + 정적. 외부 API 호출 없음.
 */

export const metadata: Metadata = {
  title: "서비스 소개",
  description:
    "집토리는 국토교통부 실거래가·K-APT 시설·학군 배정 등 공공데이터를 기반으로 라이프스타일 키워드에 맞춰 아파트를 추천·비교·분석하는 서비스입니다.",
  alternates: { canonical: "/about" },
  openGraph: {
    title: `서비스 소개 | ${BRAND.name}`,
    description:
      "라이프스타일 기반 NUDGE 스코어링, 가격·안전 점수, 학군 분석, MCP 서버 등 집토리의 데이터·방법론·API 소개.",
    url: "/about",
    type: "article",
  },
};

const aboutPageJsonLd = {
  "@context": "https://schema.org",
  "@type": "AboutPage",
  name: `${BRAND.name} 서비스 소개`,
  url: `${SITE_URL}/about`,
  inLanguage: BRAND.locale,
  about: {
    "@type": "Organization",
    name: BRAND.name,
    alternateName: BRAND.nameEnglish,
    url: SITE_URL,
    description: BRAND.description,
  },
};

export default function AboutPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:py-12 text-gray-900">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(aboutPageJsonLd) }}
      />

      <h1 className="text-3xl font-bold">집토리 서비스 소개</h1>
      <p className="mt-4 text-base leading-relaxed text-gray-700">
        {BRAND.name} ({BRAND.nameEnglish}) 는 대한민국 아파트 데이터를 라이프스타일
        키워드로 검색·추천·비교·분석하는 공개 서비스입니다. 국토교통부 실거래가
        공개시스템, K-APT (공동주택 관리정보 시스템), 공공데이터포털 CCTV, 교육청
        학군 배정 등 공식 공공데이터를 수집·정규화해 활용합니다.
      </p>

      <Section title="무엇이 다른가">
        <ul className="list-disc space-y-2 pl-6 text-gray-700">
          <li>
            <strong>라이프스타일 NUDGE 스코어링</strong> — 출퇴근·가성비·신혼부부·
            시니어·반려동물·자연친화·안전·교육·투자 항목을 조합해 단지별 적합도
            점수(0~100) 를 산출합니다.
          </li>
          <li>
            <strong>가격·안전 점수</strong> — ㎡당 단가·전세비율 기반 상대 점수,
            500m 내 CCTV 밀도 기반 안전 점수.
          </li>
          <li>
            <strong>학군·시설 거리 분석</strong> — 초·중·고 학군 배정 정보 + 지하철·
            공원·병원 등 주요 편의시설까지 거리와 1km 내 개수.
          </li>
          <li>
            <strong>AI 에이전트 지원</strong> — <code>/mcp/</code> MCP (Model Context
            Protocol) 엔드포인트로 Claude Desktop·Cursor·Codex 등에서 직접 검색·상세
            조회·시장 동향을 쿼리할 수 있습니다.
          </li>
        </ul>
      </Section>

      <Section title="데이터 출처">
        <ul className="list-disc space-y-2 pl-6 text-gray-700">
          <li>국토교통부 — 아파트 실거래가 (매매·전월세)</li>
          <li>K-APT 공동주택 관리정보 시스템 — 관리비·시설·구조</li>
          <li>공공데이터포털 — CCTV 위치, 안전 관련 지표</li>
          <li>교육청 — 학군 배정</li>
        </ul>
      </Section>

      <Section title="주요 페이지·엔드포인트">
        <ul className="list-disc space-y-2 pl-6 text-gray-700">
          <li>
            <a className="text-blue-600 hover:underline" href="/">
              홈
            </a>{" "}
            — 지도·필터·라이프스타일 스코어링
          </li>
          <li>
            <code>/apartment/[pnu]</code> — 개별 아파트 상세 (기본·점수·학군·시설·
            거래이력)
          </li>
          <li>
            <code>/sitemap.xml</code> — 전체 아파트 URL
          </li>
          <li>
            <code>/llms.txt</code> — LLM·agent 를 위한 사이트 설명
          </li>
          <li>
            <code>https://api.apt-recom.kr/mcp/</code> — MCP 서버 (Streamable HTTP)
          </li>
          <li>
            <code>https://api.apt-recom.kr/openapi.json</code> — OpenAPI 스펙
          </li>
        </ul>
      </Section>

      <Section title="공지">
        <p className="text-sm leading-relaxed text-gray-600">
          본 서비스는 공공데이터 기반 정보 제공 목적이며, 법적·금융적 자문이나
          공식 시세를 보장하지 않습니다. 실제 거래·계약 시 반드시 공식 원천
          (국토교통부 실거래가 공개시스템 등) 을 확인하시기 바랍니다.
        </p>
      </Section>
    </main>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-xl font-semibold text-gray-800">{title}</h2>
      {children}
    </section>
  );
}
