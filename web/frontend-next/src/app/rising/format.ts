const MANWON_PER_EOK = 10000;
const EMPTY_TEXT = "—";

/** 85000 → "8.5억", 100000 → "10억", 8500 → "8,500만" (만원 정수 입력). */
export function formatEok(manwon: number): string {
  if (manwon < MANWON_PER_EOK) return `${manwon.toLocaleString()}만`;
  const eok = Math.round((manwon / MANWON_PER_EOK) * 10) / 10;
  return `${eok}억`;
}

/** 표시 자릿수(소수 1자리)로 반올림했을 때 0 인지 (-0.04 → true). */
export function isRoundedZero(pct: number): boolean {
  return Number(pct.toFixed(1)) === 0;
}

/** 29.94 → "+29.9%", -5.2 → "-5.2%", -0.04 → "0.0%", null → "—". */
export function formatChange(pct: number | null): string {
  if (pct === null) return EMPTY_TEXT;
  if (isRoundedZero(pct)) return "0.0%";
  const rounded = pct.toFixed(1);
  return pct > 0 ? `+${rounded}%` : `${rounded}%`;
}

/** 3개월 중위가격 표본이 이 건수 이하면 "표본 적음" 표시. */
export const THIN_SAMPLE_MAX_TRADES = 2;
export const THIN_SAMPLE_TEXT = "표본 적음";

export function isThinSample(tradeCount: number | null): boolean {
  return tradeCount !== null && tradeCount <= THIN_SAMPLE_MAX_TRADES;
}

/** 202609 → "2026.09" */
export function formatBaseMonth(ym: number): string {
  const text = String(ym);
  return `${text.slice(0, 4)}.${text.slice(4)}`;
}
