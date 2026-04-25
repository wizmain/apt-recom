/**
 * SYNCED FROM packages/shared/api/paths.ts — keep in sync.
 * 원본 변경 시 본 파일도 갱신할 것. 자세한 사유는 src/shared/README.md.
 *
 * Toss 미니앱 v1 에서 사용하는 백엔드 엔드포인트 URL 빌더.
 * 백엔드: web/backend/routers/{apartments,detail,codes,dashboard}.py
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
