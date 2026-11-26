'use client';

import Link from 'next/link';
import { logEvent } from '@/lib/logEvent';

/**
 * 상단 바 보기 탭 [지도 | 대시보드 | 가격흐름] — 홈(NudgeBar)과 가격흐름 페이지(/rising)가 함께 쓴다.
 * - 홈: 지도·대시보드는 같은 화면 안의 전환 버튼(onSwitchHomeView), 가격흐름은 /rising 이동.
 * - 홈 밖: 지도·대시보드는 홈으로 이동하는 링크(대시보드는 유입 계측 from 포함), 현재 화면은 선택 표시.
 */
export type AppView = 'map' | 'dashboard' | 'priceFlow';
type HomeView = Exclude<AppView, 'priceFlow'>;

const PRICE_FLOW_PATH = '/rising';
const PRICE_FLOW_LABEL = '가격흐름';

const TAB_BASE = 'px-2.5 sm:px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors';
const TAB_ACTIVE = 'bg-white text-gray-900 shadow-sm';
const TAB_INACTIVE = 'text-gray-500 hover:text-gray-700';

function tabClass(active: boolean): string {
  return `${TAB_BASE} ${active ? TAB_ACTIVE : TAB_INACTIVE}`;
}

function HomeViewLabel({ view }: { view: HomeView }) {
  if (view === 'map') return <>지도</>;
  return (
    <>
      {/* 1280px 미만은 짧은 라벨 — 탭 3개를 넣어도 상단 바가 넘치지 않게 */}
      <span className="xl:hidden">대시보드</span>
      <span className="hidden xl:inline">실거래대시보드</span>
    </>
  );
}

function homeViewHref(view: HomeView, dashboardFrom: string) {
  return view === 'map' ? '/' : (`/?view=dashboard&from=${dashboardFrom}` as const);
}

interface ViewTabsProps {
  active: AppView;
  /** 홈 안에서 지도·대시보드를 전환하는 함수. 없으면(홈 밖) 홈으로 이동하는 링크를 그린다. */
  onSwitchHomeView?: (view: HomeView) => void;
  /** 홈 밖에서 대시보드로 갈 때 유입 계측 출처(useViewParam 의 dashboard_arrival source). */
  dashboardFrom?: string;
}

export default function ViewTabs({ active, onSwitchHomeView, dashboardFrom = 'nav' }: ViewTabsProps) {
  return (
    <div className="flex items-center bg-gray-100 rounded-full p-0.5 flex-shrink-0">
      {(['map', 'dashboard'] as const).map((view) =>
        onSwitchHomeView ? (
          <button key={view} type="button" onClick={() => onSwitchHomeView(view)} className={tabClass(active === view)}>
            <HomeViewLabel view={view} />
          </button>
        ) : (
          <Link key={view} href={homeViewHref(view, dashboardFrom)} className={tabClass(active === view)}>
            <HomeViewLabel view={view} />
          </Link>
        ),
      )}
      {active === 'priceFlow' ? (
        <span aria-current="page" className={tabClass(true)}>
          {PRICE_FLOW_LABEL}
        </span>
      ) : (
        <Link
          href={PRICE_FLOW_PATH}
          onClick={() => logEvent('price_flow_shortcut_click', { view_mode: active })}
          className={tabClass(false)}
        >
          {PRICE_FLOW_LABEL}
          <span aria-hidden className="ml-0.5 text-[10px] hidden xl:inline">↗</span>
        </Link>
      )}
    </div>
  );
}
