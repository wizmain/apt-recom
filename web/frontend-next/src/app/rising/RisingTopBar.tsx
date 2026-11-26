import TopBarRightLinks from '@/components/TopBarRightLinks';
import ViewTabs from '@/components/ViewTabs';

/** 가격흐름 페이지 상단 바 — 홈 대시보드 화면의 상단 바와 같은 구성(로고 · 보기 탭 · 오른쪽 링크). */
export default function RisingTopBar() {
  return (
    <header className="fixed top-0 left-0 right-0 z-10 bg-white/95 backdrop-blur-sm shadow-sm">
      <div className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 h-12 sm:h-14">
        <span className="text-sm font-semibold text-gray-700 whitespace-nowrap mr-0.5 sm:mr-1">🐿</span>
        <ViewTabs active="priceFlow" dashboardFrom="rising" />
        <TopBarRightLinks />
      </div>
    </header>
  );
}
