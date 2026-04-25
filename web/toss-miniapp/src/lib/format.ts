/**
 * 가격/면적/날짜 포매터. 기존 web/frontend Dashboard.tsx 의 헬퍼와 동일 동작.
 */

/** 만원 단위 정수를 한국식으로 표기 (1억 5,000 / 9,500). */
export function formatPrice(val: number | null | undefined): string {
  if (val == null) return '-';
  if (val >= 10000) {
    const eok = Math.floor(val / 10000);
    const rest = val % 10000;
    return `${eok}억${String(rest).padStart(4, '0').replace(/(\d)(?=(\d{3})+$)/g, '$1,')}`;
  }
  return val.toLocaleString();
}

/** 평방미터 → 평 표기. */
export function m2ToPyeong(m2: number | null | undefined): string {
  if (m2 == null) return '-';
  return `${(m2 * 0.3025).toFixed(1)}평`;
}

/** 변동률 표시 (전월 대비). */
export function changeRate(
  cur: number,
  prev: number
): { text: string; color: string } {
  if (!prev) return { text: '-', color: '#888' };
  const rate = ((cur - prev) / prev) * 100;
  const fixed = rate.toFixed(1);
  if (rate > 0) return { text: `+${fixed}%`, color: '#E84A4A' };
  if (rate < 0) return { text: `${fixed}%`, color: '#3182F6' };
  return { text: '0%', color: '#888' };
}

/** ISO 시간을 "방금 전 / N시간 전 / N일 전" 으로. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return '방금 전';
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}
