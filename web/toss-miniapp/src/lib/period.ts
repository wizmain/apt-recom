/**
 * 기간 프리셋 ↔ 날짜 범위 변환 헬퍼.
 *
 * - presetToRange: 프리셋(1주/1개월/3개월/6개월/전체/직접) → {from, to, label}
 * - parseYmdInput: 사용자 입력(YYYY-MM-DD 또는 YYYYMMDD)을 검증하여 YYYYMMDD 로 정규화
 * - formatYmdHuman: YYYYMMDD → YYYY.MM.DD
 *
 * 모두 순수 함수. 단위 테스트 가능.
 */

export type PeriodPreset = '1w' | '1m' | '3m' | '6m' | 'all' | 'custom';

export const PRESET_LIST: ReadonlyArray<{
  value: PeriodPreset;
  label: string;
}> = [
  { value: '1w', label: '1주' },
  { value: '1m', label: '1개월' },
  { value: '3m', label: '3개월' },
  { value: '6m', label: '6개월' },
  { value: 'all', label: '전체' },
  { value: 'custom', label: '직접선택' },
];

export interface PeriodRange {
  /** YYYYMMDD or undefined (전체) */
  from?: string;
  /** YYYYMMDD or undefined (전체) */
  to?: string;
  /** 표시용 라벨 (예: '최근 3개월', '2026.02.01 ~ 2026.05.01', '전체') */
  label: string;
}

const PRESET_LABELS: Record<PeriodPreset, string> = {
  '1w': '최근 1주',
  '1m': '최근 1개월',
  '3m': '최근 3개월',
  '6m': '최근 6개월',
  all: '전체',
  custom: '직접 선택',
};

const DAYS_BY_PRESET: Partial<Record<PeriodPreset, number>> = {
  '1w': 6, // 오늘 포함 7일
  '1m': 29, // 오늘 포함 30일
  '3m': 89,
  '6m': 179,
};

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function dateToYmd(d: Date): string {
  return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}`;
}

function addDays(d: Date, days: number): Date {
  const next = new Date(d);
  next.setDate(next.getDate() + days);
  return next;
}

/**
 * 프리셋과 사용자 지정 날짜를 받아 API 쿼리에 쓸 from/to 와 표시 라벨을 반환.
 *
 * - 'all': from/to 미지정 (전체 데이터)
 * - 'custom': 인자로 받은 customFrom/customTo 사용. 둘 다 유효해야 라벨에 범위 표시.
 * - 그 외: today - DAYS_BY_PRESET ~ today
 */
export function presetToRange(
  preset: PeriodPreset,
  customFrom: string,
  customTo: string,
  today: Date = new Date(),
): PeriodRange {
  if (preset === 'all') {
    return { label: PRESET_LABELS.all };
  }
  if (preset === 'custom') {
    if (customFrom && customTo) {
      return {
        from: customFrom,
        to: customTo,
        label: `${formatYmdHuman(customFrom)} ~ ${formatYmdHuman(customTo)}`,
      };
    }
    return { label: PRESET_LABELS.custom };
  }
  const days = DAYS_BY_PRESET[preset] ?? 0;
  const start = addDays(today, -days);
  return {
    from: dateToYmd(start),
    to: dateToYmd(today),
    label: PRESET_LABELS[preset],
  };
}

/**
 * 사용자 입력 정규화. 'YYYY-MM-DD', 'YYYY.MM.DD', 'YYYYMMDD' 모두 허용.
 * 실제 Date 로 검증하여 2026-02-30 같은 잘못된 날짜 거부.
 *
 * @returns 'YYYYMMDD' 문자열 또는 null (검증 실패)
 */
export function parseYmdInput(raw: string): string | null {
  const digits = raw.replace(/[^\d]/g, '');
  if (digits.length !== 8) return null;
  const y = Number(digits.slice(0, 4));
  const m = Number(digits.slice(4, 6));
  const d = Number(digits.slice(6, 8));
  if (!y || !m || !d) return null;
  const dt = new Date(y, m - 1, d);
  if (
    dt.getFullYear() !== y ||
    dt.getMonth() !== m - 1 ||
    dt.getDate() !== d
  ) {
    return null;
  }
  return digits;
}

export function formatYmdHuman(ymd: string): string {
  if (!/^\d{8}$/.test(ymd)) return ymd;
  return `${ymd.slice(0, 4)}.${ymd.slice(4, 6)}.${ymd.slice(6, 8)}`;
}

/** 두 YYYYMMDD 문자열의 일수 차이 (to - from). 음수 가능. */
export function daysBetween(fromYmd: string, toYmd: string): number {
  const toDate = (s: string) =>
    new Date(
      Number(s.slice(0, 4)),
      Number(s.slice(4, 6)) - 1,
      Number(s.slice(6, 8)),
    );
  const ms = toDate(toYmd).getTime() - toDate(fromYmd).getTime();
  return Math.round(ms / 86400000);
}
