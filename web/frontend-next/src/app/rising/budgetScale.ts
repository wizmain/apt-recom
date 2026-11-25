/** 예산 슬라이더 눈금 — 3~100억, 15억이 트랙 중앙(구간별 선형). */
export const BUDGET_MIN_EOK = 3;
export const BUDGET_MAX_EOK = 100;
const BUDGET_MID_EOK = 15;
export const SLIDER_STEPS = 1000;
const SLIDER_MID = SLIDER_STEPS / 2;
/** 저가 구간(~15억) 0.5억, 고가 구간 1억 단위로 반올림. */
const LOW_STEP_EOK = 0.5;
const HIGH_STEP_EOK = 1;

export function eokToSlider(eok: number): number {
  const clamped = Math.min(BUDGET_MAX_EOK, Math.max(BUDGET_MIN_EOK, eok));
  if (clamped <= BUDGET_MID_EOK) {
    return ((clamped - BUDGET_MIN_EOK) / (BUDGET_MID_EOK - BUDGET_MIN_EOK)) * SLIDER_MID;
  }
  return (
    SLIDER_MID +
    ((clamped - BUDGET_MID_EOK) / (BUDGET_MAX_EOK - BUDGET_MID_EOK)) * SLIDER_MID
  );
}

export function sliderToEok(pos: number): number {
  if (pos <= SLIDER_MID) {
    const eok = BUDGET_MIN_EOK + (pos / SLIDER_MID) * (BUDGET_MID_EOK - BUDGET_MIN_EOK);
    return Math.round(eok / LOW_STEP_EOK) * LOW_STEP_EOK;
  }
  const eok =
    BUDGET_MID_EOK +
    ((pos - SLIDER_MID) / SLIDER_MID) * (BUDGET_MAX_EOK - BUDGET_MID_EOK);
  return Math.round(eok / HIGH_STEP_EOK) * HIGH_STEP_EOK;
}

/** 하한 ≤ 상한 불변: 움직인 쪽에 맞춰 반대쪽을 같은 값으로 민다. */
export function applyBudgetChange(
  edge: "min" | "max",
  value: number,
  current: { min: number; max: number },
): { min: number; max: number } {
  const next = Math.min(BUDGET_MAX_EOK, Math.max(BUDGET_MIN_EOK, value));
  if (edge === "min") return { min: next, max: Math.max(current.max, next) };
  return { min: Math.min(current.min, next), max: next };
}
