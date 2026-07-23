import Link from "next/link";

/**
 * 콘텐츠·단지 상세 등 홈 밖 화면 공용 네비게이션 — 지도(홈)·실거래
 * 대시보드(·콘텐츠) 알약. 스타일은 홈 상단바(NudgeBar ExploreLink 계열) 준용.
 *
 * `from` 은 대시보드 유입 계측용(useViewParam 의 dashboard_arrival source) —
 * 화면 정체를 나타내는 소문자 슬러그를 넘긴다 (예: "content", "apartment").
 */
const PILL =
  "inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium " +
  "text-gray-600 border border-gray-300 hover:border-blue-400 hover:text-blue-600 " +
  "transition-all duration-200 whitespace-nowrap";

export function SiteNav({
  from,
  showContentLink = false,
}: {
  from: string;
  showContentLink?: boolean;
}) {
  return (
    <nav aria-label="주요 화면 이동" className="flex items-center gap-2">
      <Link href="/" className={PILL}>
        <span aria-hidden>🗺️</span> 지도에서 찾기
      </Link>
      <Link href={`/?view=dashboard&from=${from}`} className={PILL}>
        <span aria-hidden>📊</span> 실거래 대시보드
      </Link>
      {showContentLink && (
        <Link href="/content" className={PILL}>
          <span aria-hidden>📰</span> 콘텐츠
        </Link>
      )}
    </nav>
  );
}
