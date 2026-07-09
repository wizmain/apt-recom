import { API_URL } from "@/lib/site";
import type {
  RegionListItem,
  ParsedRegionName,
  DashboardSummary,
  TrendMonth,
  RecentTrade,
  RegionApartment,
} from "@/types/region";

/**
 * /region, /region/[code] 공용 서버 fetch — 두 라우트가 동일한 regions 목록/
 * 파싱 로직을 쓰므로 공통 모듈로 추출 (route-scoped private module).
 *
 * 모든 fetch 는 실패해도 throw 하지 않고 빈 값으로 degrade — 페이지 자체가
 * 죽지 않고, 호출부(page.tsx)가 notFound()/조건 렌더로 처리한다.
 */

const REGION_NAME_PATTERN = /^(.+)\((.+)\)$/;

/** "강남구(서울)" → { district: "강남구", parent: "서울" }. 괄호 없으면 parent 빈 문자열. */
export function parseRegionName(name: string): ParsedRegionName {
  const match = REGION_NAME_PATTERN.exec(name);
  if (!match) return { district: name, parent: "" };
  return { district: match[1], parent: match[2] };
}

export async function fetchRegions(): Promise<RegionListItem[]> {
  try {
    const res = await fetch(`${API_URL}/api/dashboard/regions`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    return (await res.json()) as RegionListItem[];
  } catch {
    return [];
  }
}

export async function fetchRegionSummary(
  code: string,
): Promise<DashboardSummary | null> {
  try {
    const res = await fetch(
      `${API_URL}/api/dashboard/summary?sigungu=${encodeURIComponent(code)}`,
      { next: { revalidate: 3600 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as DashboardSummary;
  } catch {
    return null;
  }
}

export async function fetchRegionTrend(
  code: string,
  months: number,
): Promise<TrendMonth[]> {
  try {
    const res = await fetch(
      `${API_URL}/api/dashboard/trend?sigungu=${encodeURIComponent(code)}&months=${months}`,
      { next: { revalidate: 3600 } },
    );
    if (!res.ok) return [];
    return (await res.json()) as TrendMonth[];
  } catch {
    return [];
  }
}

export async function fetchRegionRecentTrades(
  code: string,
  limit: number,
): Promise<RecentTrade[]> {
  try {
    const res = await fetch(
      `${API_URL}/api/dashboard/recent?sigungu=${encodeURIComponent(code)}&limit=${limit}`,
      { next: { revalidate: 3600 } },
    );
    if (!res.ok) return [];
    return (await res.json()) as RecentTrade[];
  } catch {
    return [];
  }
}

/** sigungu_code 만으로 동작 확인됨(실측) — viewport 파라미터 불필요. */
export async function fetchRegionApartments(
  code: string,
): Promise<RegionApartment[]> {
  try {
    const res = await fetch(
      `${API_URL}/api/apartments?sigungu_code=${encodeURIComponent(code)}`,
      { next: { revalidate: 3600 } },
    );
    if (!res.ok) return [];
    return (await res.json()) as RegionApartment[];
  } catch {
    return [];
  }
}
