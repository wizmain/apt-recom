/**
 * 단지 상세 nudge 점수에서 라이프스타일 추천 프리셋을 추출하는 순수 함수.
 *
 * 입력: 단지 상세 API 의 `scores` 필드(9종 nudge 코드 → 점수 0~100).
 * 출력: `{ nudges: string[], region: SelectedRegion | null }` — first-visit PRD 와 공유하는
 *       단일 출력 계약(PRD §6.4). region 은 호출 측에서 채운다.
 */

import type { SelectedRegion } from "@/types/apartment";

/** 프리셋에 포함할 최대 nudge 개수. */
const PRESET_MAX_COUNT = 2;

/**
 * 저점 가드: 이 임계값 미만의 점수는 단지의 강점으로 보기 어려움.
 * 0~100 점 스케일에서 50 이상이어야 프리셋에 포함.
 */
const SCORE_MIN_THRESHOLD = 50;

/** 최종 출력 계약 — first-visit PRD, detail bridge 공용. */
export interface DetailPresetResult {
  nudges: string[];
  region: SelectedRegion | null;
}

/**
 * `scores` 에서 상위 nudge 코드를 추출해 프리셋을 만든다.
 *
 * - `scores` 가 비었거나 null/undefined 면 `{ nudges: [] }` 반환.
 * - 점수가 SCORE_MIN_THRESHOLD 미만인 항목은 제외.
 * - 나머지를 내림차순 정렬 후 PRESET_MAX_COUNT 개 선택.
 * - 동점 처리: 정렬 안정성은 JS Array.sort 의 stable sort 에 위임.
 *   동점 항목 사이에서는 입력 배열 순서를 유지한다.
 *
 * @param scores - `detail.scores` (Record<nudge_code, 점수>) or null/undefined
 * @param region - 단지 sigungu_code 기반 SelectedRegion (옵션)
 */
export function buildDetailPreset(
  scores: Record<string, number> | null | undefined,
  region: SelectedRegion | null = null,
): DetailPresetResult {
  if (!scores || Object.keys(scores).length === 0) {
    return { nudges: [], region };
  }

  const qualified = Object.entries(scores).filter(
    ([, score]) => score >= SCORE_MIN_THRESHOLD,
  );

  if (qualified.length === 0) {
    return { nudges: [], region };
  }

  const sorted = qualified.sort((a, b) => b[1] - a[1]);
  const nudges = sorted.slice(0, PRESET_MAX_COUNT).map(([code]) => code);

  return { nudges, region };
}
