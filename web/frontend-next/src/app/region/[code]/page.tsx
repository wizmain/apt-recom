import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { SITE_URL, BRAND } from "@/lib/site";
import type { RegionApartment } from "@/types/region";
import {
  fetchRegions,
  fetchRegionSummary,
  fetchRegionTrend,
  fetchRegionRecentTrades,
  fetchRegionApartments,
  parseRegionName,
} from "@/lib/regionData";
import { RegionHubView } from "./_view";

/**
 * /region/[code] — 시군구 허브 페이지. Server Component (on-demand ISR).
 *
 * apartment/[pnu]/page.tsx 패턴 준용: 서버 fetch 함수 + generateMetadata +
 * JSON-LD 스크립트 + notFound(). 시군구 코드→이름 해석은 dashboard/regions
 * 목록에서 검증하며(별도 "코드 존재 확인" 엔드포인트 없음), 미존재 코드는 404.
 */

export const revalidate = 3600;

type PageParams = { code: string };

const TREND_MONTHS = 12;
const RECENT_TRADE_LIMIT = 20;
const ITEM_LIST_LIMIT = 20;

/** regions 목록에서 code 에 해당하는 원본 name("강남구(서울)")을 찾는다. 없으면 null. */
async function resolveRegionName(code: string): Promise<string | null> {
  const regions = await fetchRegions();
  const matched = regions.find((r) => r.code === code);
  return matched ? matched.name : null;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<PageParams>;
}): Promise<Metadata> {
  const { code } = await params;
  const name = await resolveRegionName(code);
  if (!name) {
    return { title: "지역을 찾을 수 없습니다", robots: { index: false } };
  }
  const { district, parent } = parseRegionName(name);
  const label = parent ? `${parent} ${district}` : district;

  const [summary, apartments] = await Promise.all([
    fetchRegionSummary(code),
    // 본문 렌더와 동일 URL fetch — Next 요청 단위 dedupe 로 추가 호출 없음.
    fetchRegionApartments(code),
  ]);
  const description = summary
    ? `${label} 이번 달 아파트 거래량 ${summary.trade.volume}건, ㎡당 중위가 ${Math.round(summary.trade.median_price_m2).toLocaleString()}만원 — 실거래가·시세·단지 목록을 확인하세요.`
    : `${label} 아파트 실거래가·시세·단지 목록을 확인하세요.`;

  return {
    title: `${label} 아파트 실거래가·시세`,
    description,
    alternates: { canonical: `/region/${code}` },
    // 단지 0개 지역은 얇은/중복 콘텐츠 색인 방지를 위해 noindex — 신구
    // 행정코드 이원화(강원·전북)로 동일 title/h1 의 빈 쌍둥이 페이지 32쌍이
    // 존재한다 (2026-07-10 실측). 페이지 자체는 200 유지(직접 방문 허용),
    // /region 인덱스 제외와 같은 기준(단지 수 0)을 공유한다.
    ...(apartments.length === 0
      ? { robots: { index: false, follow: false } }
      : {}),
    openGraph: {
      title: `${label} 아파트 실거래가·시세 | ${BRAND.name}`,
      description,
      url: `/region/${code}`,
      type: "website",
    },
  };
}

function buildBreadcrumbJsonLd(code: string, label: string) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: BRAND.name, item: SITE_URL },
      {
        "@type": "ListItem",
        position: 2,
        name: "지역",
        item: `${SITE_URL}/region`,
      },
      {
        "@type": "ListItem",
        position: 3,
        name: label,
        item: `${SITE_URL}/region/${code}`,
      },
    ],
  };
}

function buildItemListJsonLd(apartments: RegionApartment[]) {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    itemListElement: apartments.slice(0, ITEM_LIST_LIMIT).map((apt, idx) => ({
      "@type": "ListItem",
      position: idx + 1,
      url: `${SITE_URL}/apartment/${apt.pnu}`,
      name: apt.bld_nm,
    })),
  };
}

export default async function RegionHubPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { code } = await params;
  const name = await resolveRegionName(code);
  if (!name) notFound();

  const { district, parent } = parseRegionName(name);
  const label = parent ? `${parent} ${district}` : district;

  const [summary, trend, recentTrades, apartmentsRaw] = await Promise.all([
    fetchRegionSummary(code),
    fetchRegionTrend(code, TREND_MONTHS),
    fetchRegionRecentTrades(code, RECENT_TRADE_LIMIT),
    fetchRegionApartments(code),
  ]);

  // 세대수 내림차순 — 내부 링크 그래프 상단에 대단지 노출.
  const apartments = [...apartmentsRaw].sort(
    (a, b) => (b.total_hhld_cnt ?? 0) - (a.total_hhld_cnt ?? 0),
  );

  const jsonLd = [buildBreadcrumbJsonLd(code, label), buildItemListJsonLd(apartments)];

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <RegionHubView
        code={code}
        district={district}
        parent={parent}
        summary={summary}
        trend={trend}
        recentTrades={recentTrades}
        apartments={apartments}
      />
    </>
  );
}
