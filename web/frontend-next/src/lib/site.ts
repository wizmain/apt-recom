/**
 * 사이트 전역 상수 — 단일 소스로 canonical host·JSON-LD·브랜드 정보 관리.
 *
 * NEXT_PUBLIC_SITE_URL 을 설정하면 프리뷰·스테이징 등에서 override 가능.
 * 기본 프로덕션: https://apt-recom.kr (non-www, apex).
 */

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://apt-recom.kr"
).replace(/\/$/, "");

/** 백엔드 API origin. Server Component 의 fetch 에서 사용. */
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "https://api.apt-recom.kr"
).replace(/\/$/, "");

export const BRAND = {
  name: "집토리",
  nameEnglish: "apt-recom",
  description: "라이프스타일 기반 아파트 추천 서비스",
  locale: "ko_KR",
} as const;

/** Organization JSON-LD — 루트 layout 에 주입. */
export const ORGANIZATION_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: BRAND.name,
  alternateName: BRAND.nameEnglish,
  url: SITE_URL,
  logo: `${SITE_URL}/favicon.svg`,
  description: BRAND.description,
  // 외부 신뢰 신호(Wikipedia/Linkedin) 등록 시 여기 추가.
  sameAs: [] as string[],
};

/** WebSite JSON-LD — SearchAction 포함. */
export const WEBSITE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: BRAND.name,
  url: SITE_URL,
  inLanguage: BRAND.locale,
  potentialAction: {
    "@type": "SearchAction",
    target: `${SITE_URL}/?q={search_term_string}`,
    "query-input": "required name=search_term_string",
  },
};
