import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { API_URL, SITE_URL, BRAND } from "@/lib/site";
import type {
  ApartmentDetail,
  TradesResponse,
} from "@/types/apartment";
import type { ResolvedRegion } from "@/types/region";
import { fetchRegions, parseRegionName } from "@/lib/regionData";
import { ApartmentDetailView } from "./_view";

/**
 * 아파트 상세 페이지 — Server Component (SSG + On-demand ISR).
 *
 * - `revalidate = 3600`: 1시간 간격 재검증.
 * - `dynamicParams = true` (기본값 명시): generateStaticParams 밖 경로도 첫 요청 시 생성.
 * - `generateStaticParams`: 빈 배열 — 현 단계는 전부 on-demand ISR.
 *   Phase B 후반에 상위 도시 PNU 만 pre-render 로 전환.
 *
 * agent 목적: Server Component 에서 fetch → HTML 본문에 아파트명·주소·점수·학군 렌더,
 * ApartmentComplex JSON-LD 주입.
 */

export const revalidate = 3600;
export const dynamicParams = true;

const PNU_PATTERN = /^[0-9]{19}$/;

async function fetchDetail(pnu: string): Promise<ApartmentDetail | null> {
  if (!PNU_PATTERN.test(pnu)) return null;
  try {
    const res = await fetch(`${API_URL}/api/apartment/${pnu}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return (await res.json()) as ApartmentDetail;
  } catch {
    return null;
  }
}

async function fetchTrades(pnu: string): Promise<TradesResponse> {
  try {
    const res = await fetch(`${API_URL}/api/apartment/${pnu}/trades`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return { trades: [], rents: [] };
    return (await res.json()) as TradesResponse;
  } catch {
    return { trades: [], rents: [] };
  }
}

export async function generateStaticParams(): Promise<Array<{ pnu: string }>> {
  // TODO(Phase B 후반): 상위 도시 PNU pre-render. 현재는 on-demand ISR 전용.
  return [];
}

/**
 * 단지의 sigungu_code → 지역 허브 링크용 {code, label} 해석.
 * region/[code]/page.tsx 의 resolveRegionName() 과 동일한 dashboard/regions
 * 목록 조회 방식 — 별도 "코드 단건 조회" 엔드포인트가 없어 목록에서 찾는다.
 *
 * sigungu_code 가 없거나 regions 목록에 없으면 null 로 degrade — breadcrumb 는
 * 2단계로, 하단 "지역 아파트 더보기" 링크는 생략된다(단지 자체 정보는 그대로 노출).
 */
async function resolveRegion(
  sigunguCode: string | null | undefined,
): Promise<ResolvedRegion | null> {
  if (!sigunguCode) return null;
  const regions = await fetchRegions();
  const matched = regions.find((r) => r.code === sigunguCode);
  if (!matched) return null;
  const { district, parent } = parseRegionName(matched.name);
  const label = parent ? `${parent} ${district}` : district;
  return { code: sigunguCode, label };
}

type PageParams = { pnu: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<PageParams>;
}): Promise<Metadata> {
  const { pnu } = await params;
  const detail = await fetchDetail(pnu);
  if (!detail) {
    return { title: "아파트를 찾을 수 없습니다", robots: { index: false } };
  }
  const name = detail.basic.bld_nm;
  const address = detail.basic.new_plat_plc ?? detail.basic.plat_plc ?? "";
  const description = `${address} ${name} — NUDGE 점수·실거래가·학군·안전·주변시설.`;
  return {
    title: name,
    description,
    alternates: { canonical: `/apartment/${pnu}` },
    openGraph: {
      title: `${name} | ${BRAND.name}`,
      description,
      url: `/apartment/${pnu}`,
      type: "website",
    },
  };
}

function buildApartmentJsonLd(pnu: string, detail: ApartmentDetail) {
  const { basic } = detail;
  const address = basic.new_plat_plc ?? basic.plat_plc ?? undefined;
  const yearBuilt =
    basic.use_apr_day && basic.use_apr_day.length >= 4
      ? basic.use_apr_day.slice(0, 4)
      : undefined;
  return {
    "@context": "https://schema.org",
    "@type": "ApartmentComplex",
    name: basic.bld_nm,
    url: `${SITE_URL}/apartment/${pnu}`,
    ...(address
      ? {
          address: {
            "@type": "PostalAddress",
            streetAddress: address,
            addressCountry: "KR",
          },
        }
      : {}),
    geo: {
      "@type": "GeoCoordinates",
      latitude: basic.lat,
      longitude: basic.lng,
    },
    ...(basic.total_hhld_cnt
      ? { numberOfAccommodationUnits: basic.total_hhld_cnt }
      : {}),
    ...(yearBuilt ? { yearBuilt } : {}),
  };
}

interface BreadcrumbListItem {
  "@type": "ListItem";
  position: number;
  name: string;
  item: string;
}

// 크롤러용 위치 계층 신호. region 해석에 성공하면 집토리 > {시군구} > 단지
// 3단계, 실패(sigungu_code 부재·미등록 코드)하면 기존 2단계로 degrade.
function buildBreadcrumbJsonLd(
  pnu: string,
  detail: ApartmentDetail,
  region: ResolvedRegion | null,
) {
  const itemListElement: BreadcrumbListItem[] = [
    { "@type": "ListItem", position: 1, name: "집토리", item: SITE_URL },
  ];
  if (region) {
    itemListElement.push({
      "@type": "ListItem",
      position: 2,
      name: region.label,
      item: `${SITE_URL}/region/${region.code}`,
    });
  }
  itemListElement.push({
    "@type": "ListItem",
    position: itemListElement.length + 1,
    name: detail.basic.bld_nm,
    item: `${SITE_URL}/apartment/${pnu}`,
  });
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement,
  };
}

export default async function ApartmentDetailPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { pnu } = await params;
  const detail = await fetchDetail(pnu);
  if (!detail) notFound();

  // 거래이력·지역 해석 병렬 조회 (둘 다 실패해도 페이지는 렌더)
  const [trades, region] = await Promise.all([
    fetchTrades(pnu),
    resolveRegion(detail.basic.sigungu_code),
  ]);

  // 배열 JSON-LD — ApartmentComplex + BreadcrumbList 를 한 스크립트로.
  const jsonLd = [
    buildApartmentJsonLd(pnu, detail),
    buildBreadcrumbJsonLd(pnu, detail, region),
  ];

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <ApartmentDetailView pnu={pnu} detail={detail} trades={trades} region={region} />
    </>
  );
}
