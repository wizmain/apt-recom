const MANWON_PER_EOK = 10000;
const EMPTY_TEXT = "—";

/** 85000 → "8.5억", 100000 → "10억", 8500 → "8,500만" (만원 정수 입력). */
export function formatEok(manwon: number): string {
  if (manwon < MANWON_PER_EOK) return `${manwon.toLocaleString()}만`;
  const eok = Math.round((manwon / MANWON_PER_EOK) * 10) / 10;
  return `${eok}억`;
}

/** 29.94 → "+29.9%", -5.2 → "-5.2%", null → "—". */
export function formatChange(pct: number | null): string {
  if (pct === null) return EMPTY_TEXT;
  const rounded = pct.toFixed(1);
  return pct > 0 && Number(rounded) > 0 ? `+${rounded}%` : `${rounded}%`;
}

/** 202609 → "2026.09" */
export function formatBaseMonth(ym: number): string {
  const text = String(ym);
  return `${text.slice(0, 4)}.${text.slice(4)}`;
}
