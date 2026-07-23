import Link from "next/link";

/**
 * 콘텐츠 화면 상단 네비게이션 — 지도(홈)·실거래 대시보드 진입점.
 * 목록(/content)과 상세(/content/[slug]) 공용. 알약 스타일은 홈 상단바
 * (NudgeBar 의 ExploreLink 계열) 패턴 준용.
 */
export function ContentNav() {
  const pill =
    "inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium " +
    "text-gray-600 border border-gray-300 hover:border-blue-400 hover:text-blue-600 " +
    "transition-all duration-200 whitespace-nowrap";
  return (
    <nav aria-label="콘텐츠 바깥 이동" className="flex items-center gap-2">
      <Link href="/" className={pill}>
        <span aria-hidden>🗺️</span> 지도에서 찾기
      </Link>
      <Link href="/?view=dashboard" className={pill}>
        <span aria-hidden>📊</span> 실거래 대시보드
      </Link>
    </nav>
  );
}
