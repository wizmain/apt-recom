/**
 * 홈 상단 바 오른쪽 탐색 링크 — 넓은 화면은 알약 버튼(NudgeBar), 휴대폰 폭은 "⋯" 메뉴(TopBarMoreMenu)가
 * 같은 목록을 쓴다. 순서: 탐색성(둘러보기·콘텐츠) → 유틸리티(가이드).
 */
import type { Route } from 'next';

export interface TopBarLink {
  /** typedRoutes — 존재하는 앱 경로만 허용 */
  href: Route;
  emoji: string;
  label: string;
  title: string;
  ariaLabel: string;
}

export const TOP_BAR_LINKS: readonly TopBarLink[] = [
  // /explore 큐레이션 갤러리 (D안 홈 진입점)
  { href: '/explore', emoji: '✨', label: '둘러보기', title: '추천 둘러보기', ariaLabel: '추천 둘러보기' },
  // /content 카드뉴스 랜딩
  {
    href: '/content',
    emoji: '📰',
    label: '콘텐츠',
    title: '숫자로 보는 집 이야기',
    ariaLabel: '콘텐츠 — 숫자로 보는 집 이야기',
  },
  // 사용 가이드 / MCP 연결 안내
  { href: '/guide', emoji: '❓', label: '가이드', title: '사용 가이드', ariaLabel: '사용 가이드' },
];
