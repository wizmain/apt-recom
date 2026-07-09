import Link from "next/link";

/**
 * 단지 상세 하단 "지역 아파트 전체 보기" 링크 — 지역 허브(/region/{code})로 연결.
 *
 * Server Component (상호작용 없음). region 이 null 이면(sigungu_code 부재·
 * 미등록 코드) 렌더 생략 — page.tsx 의 resolveRegion() degrade 경로와 짝을 이룬다.
 */
export function RegionLink({
  code,
  label,
}: {
  code: string;
  label: string;
}) {
  return (
    <div className="mt-8 text-center">
      <Link
        href={`/region/${code}`}
        className="text-sm font-medium text-violet-600 hover:text-violet-700 hover:underline"
      >
        {label} 아파트 전체 보기 →
      </Link>
    </div>
  );
}
