/**
 * presentation 공유 포매터 — Server/Client 경계 중립 (순수 함수).
 *
 * 상세 페이지 섹션(Server Component) 및 홈 detail-sections(Client Component) 에서
 * 공통으로 사용. async/DOM 의존 없음.
 */

export function formatYyyymmdd(s: string | null | undefined): string | null {
  if (!s) return null;
  if (s.length === 8) return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`;
  return s;
}

export function formatPriceManwon(amount: number | null | undefined): string | null {
  if (amount == null) return null;
  if (amount >= 10000) {
    const ok = Math.floor(amount / 10000);
    const rest = amount % 10000;
    return rest > 0 ? `${ok}억 ${rest.toLocaleString()}만원` : `${ok}억원`;
  }
  return `${amount.toLocaleString()}만원`;
}

export function formatMeters(m: number | null | undefined): string | null {
  if (m == null) return null;
  if (m < 1000) return `${Math.round(m)}m`;
  return `${(m / 1000).toFixed(1)}km`;
}
