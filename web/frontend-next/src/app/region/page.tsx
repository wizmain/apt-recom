import type { Metadata } from "next";
import Link from "next/link";
import { SITE_URL, BRAND } from "@/lib/site";
import { fetchRegions, parseRegionName } from "./_data";

/**
 * /region — 전국 시군구 인덱스. Server Component, 완전 정적 목록(외부 파라미터 없음).
 *
 * regions API 의 name("강남구(서울)")을 파싱해 괄호 안 값(parent)으로 그룹핑한다.
 * 주의: parent 는 대부분 시도명이지만, 강원·전북 등 행정구역 개편(구코드→신코드
 * 이관)으로 동일 지명이 2개 코드로 중복 등록된 케이스가 있고, 일부는 parent 가
 * 시도가 아닌 상위 시명(예: "전주")이다 — common_code.extra 원본을 그대로 쓴 결과.
 * DB/코드 정합성 수정은 이 작업 범위 밖이라, 그룹 내 동일 지명이 있으면 코드를
 * 병기해 사용자가 구분할 수 있게만 한다.
 */

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "지역별 아파트 시세",
  description:
    "전국 시군구별 아파트 실거래가·시세·단지 목록을 한눈에 확인하세요. 지역을 선택하면 최근 거래 동향과 단지 전체 목록을 볼 수 있습니다.",
  alternates: { canonical: "/region" },
  openGraph: {
    title: `지역별 아파트 시세 | ${BRAND.name}`,
    description: "전국 시군구별 아파트 실거래가·시세·단지 목록.",
    url: "/region",
    type: "website",
  },
};

const breadcrumbJsonLd = {
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: [
    { "@type": "ListItem", position: 1, name: BRAND.name, item: SITE_URL },
    { "@type": "ListItem", position: 2, name: "지역", item: `${SITE_URL}/region` },
  ],
};

interface DistrictLink {
  code: string;
  district: string;
}

function groupByParent(
  regions: { code: string; name: string }[],
): Map<string, DistrictLink[]> {
  const groups = new Map<string, DistrictLink[]>();
  for (const region of regions) {
    const { district, parent } = parseRegionName(region.name);
    const key = parent || district;
    const list = groups.get(key) ?? [];
    list.push({ code: region.code, district });
    groups.set(key, list);
  }
  return groups;
}

export default async function RegionIndexPage() {
  const regions = await fetchRegions();
  const groups = groupByParent(regions);
  const groupKeys = [...groups.keys()].sort((a, b) => a.localeCompare(b, "ko"));

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:py-12 text-gray-900">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />

      <h1 className="text-3xl font-bold">지역별 아파트 시세</h1>
      <p className="mt-4 text-base leading-relaxed text-gray-700">
        시군구를 선택하면 실거래가 요약, 월별 추이, 최근 거래, 단지 전체 목록을
        확인할 수 있습니다.
      </p>

      {groups.size === 0 ? (
        <p className="mt-8 text-sm text-gray-500">
          지역 목록을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.
        </p>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-8 sm:grid-cols-2">
          {groupKeys.map((key) => {
            const districts = groups.get(key)!;
            const nameCounts = new Map<string, number>();
            for (const d of districts) {
              nameCounts.set(d.district, (nameCounts.get(d.district) ?? 0) + 1);
            }
            const sorted = [...districts].sort((a, b) =>
              a.district.localeCompare(b.district, "ko"),
            );
            return (
              <section key={key}>
                <h2 className="border-b border-gray-200 pb-1 text-lg font-semibold">
                  {key}
                </h2>
                <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm">
                  {sorted.map((d) => {
                    const isDuplicateName = (nameCounts.get(d.district) ?? 0) > 1;
                    return (
                      <li key={d.code}>
                        <Link
                          href={`/region/${d.code}`}
                          className="text-blue-600 hover:underline"
                        >
                          {d.district}
                          {isDuplicateName ? ` (${d.code})` : ""}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </main>
  );
}
