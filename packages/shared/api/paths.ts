/**
 * Toss 미니앱 v1에서 사용하는 백엔드 엔드포인트 URL 빌더.
 * 백엔드: web/backend/routers/{apartments,detail,codes,dashboard}.py
 *
 * 의도:
 *  - 웹/RN 양쪽이 동일한 경로 상수를 참조하도록 일원화.
 *  - 클라이언트(axios/fetch)는 각 환경에서 자유롭게 선택.
 */

export const apiPaths = {
  // 지역 코드
  codes: () => '/api/codes',
  codeGroup: (group: string) => `/api/codes/${encodeURIComponent(group)}`,

  // 아파트
  apartmentsList: () => '/api/apartments',
  apartmentsSearch: () => '/api/apartments/search',
  apartmentDetail: (pnu: string) => `/api/apartment/${encodeURIComponent(pnu)}`,
  apartmentTrades: (pnu: string) =>
    `/api/apartment/${encodeURIComponent(pnu)}/trades`,

  // 대시보드
  dashboardRegions: () => '/api/dashboard/regions',
  dashboardSummary: () => '/api/dashboard/summary',
  dashboardTrend: () => '/api/dashboard/trend',
  dashboardRanking: () => '/api/dashboard/ranking',
  dashboardRecent: () => '/api/dashboard/recent',
  dashboardTrades: () => '/api/dashboard/trades',
} as const;

export type ApiPaths = typeof apiPaths;
