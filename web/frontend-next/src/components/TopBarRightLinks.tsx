import Link from 'next/link';
import TopBarMoreMenu from './TopBarMoreMenu';
import { TOP_BAR_LINKS, type TopBarLink } from './topBarLinks';

/**
 * 상단 바 오른쪽 묶음 — 휴대폰 폭 "⋯" 메뉴 + 넓은 화면 알약 링크(둘러보기·콘텐츠·가이드) + 도메인·이메일.
 * 홈(NudgeBar)과 가격흐름 페이지 상단 바가 함께 쓴다. 부모 flex 줄의 직접 자식으로 들어가야
 * 오른쪽 정렬(ml-auto)이 맞는다.
 */
function TopBarPillLink({ link, alignRight }: { link: TopBarLink; alignRight: boolean }) {
  // 첫 링크의 sm:ml-auto 로 우측 정렬 → 나머지와 SiteInfo(데스크톱 전용)는 바로 옆에 붙는다.
  return (
    <Link
      href={link.href}
      title={link.title}
      aria-label={link.ariaLabel}
      className={`hidden sm:inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium
                 text-gray-600 border border-gray-300 hover:border-blue-400 hover:text-blue-600
                 transition-all duration-200 whitespace-nowrap cursor-pointer flex-shrink-0 ${alignRight ? 'sm:ml-auto' : ''}`}
    >
      <span aria-hidden>{link.emoji}</span>
      <span>{link.label}</span>
    </Link>
  );
}

function SiteInfo() {
  // 도메인 + 운영자 이메일 (데스크톱 전용 — 좁은 화면은 공간 부족)
  return (
    <div className="hidden lg:flex flex-col items-end leading-tight text-[11px] text-gray-500 whitespace-nowrap flex-shrink-0">
      <a
        href="https://apt-recom.kr"
        target="_blank"
        rel="noreferrer"
        className="font-medium text-blue-600 hover:text-blue-700 hover:underline"
      >
        apt-recom.kr
      </a>
      <a href="mailto:apt.recom@gmail.com" className="text-gray-500 hover:text-gray-700 hover:underline">
        apt.recom@gmail.com
      </a>
    </div>
  );
}

export default function TopBarRightLinks() {
  return (
    <>
      <TopBarMoreMenu />
      {TOP_BAR_LINKS.map((link, index) => (
        <TopBarPillLink key={link.href} link={link} alignRight={index === 0} />
      ))}
      <SiteInfo />
    </>
  );
}
