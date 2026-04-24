import type { TopContributor } from '@/types/apartment';

/** common_code('facility_label')에 없는 합성 subtype 라벨 */
const SYNTHETIC_LABELS: Record<string, string> = {
  score_price: '가격 경쟁력',
  score_jeonse: '전세가율',
  score_safety: '안전점수',
  score_crime: '치안',
};

/** 순위 배지(1~3위), 그 외 숫자 */
export function rankEmoji(rank: number): string {
  if (rank === 1) return '🥇';
  if (rank === 2) return '🥈';
  if (rank === 3) return '🥉';
  return '🏅';
}

function subtypeLabel(subtype: string, facilityLabels: Record<string, string>): string {
  return SYNTHETIC_LABELS[subtype] ?? facilityLabels[subtype] ?? subtype;
}

interface BuildRankReasonArgs {
  rank: number;
  selectedNudges: string[];
  contributors: TopContributor[];
  nudgeLabels: Record<string, string>;
  facilityLabels: Record<string, string>;
}

/**
 * 순위·기여 요소를 한 줄 자연어 문장으로 조합.
 */
export function buildRankReason({
  rank,
  selectedNudges,
  contributors,
  nudgeLabels,
  facilityLabels,
}: BuildRankReasonArgs): string {
  const nudgeNames = selectedNudges.map(nid => nudgeLabels[nid] ?? nid);
  const nudgeText = nudgeNames.length > 0
    ? nudgeNames.join('·')
    : '라이프 종합';
  const isMultiNudge = nudgeNames.length > 1;

  const topLabels = contributors
    .slice(0, isMultiNudge ? 2 : 2)
    .map(c => subtypeLabel(c.subtype, facilityLabels));

  if (topLabels.length === 0) {
    return `${nudgeText} 종합 평가에서 ${rank}위에 선정됐습니다.`;
  }

  if (isMultiNudge) {
    const labels = topLabels.join('·');
    return `${labels}이(가) 균형 있게 우수해 선정된 ${nudgeText} 넛지 종합 ${rank}위입니다.`;
  }

  if (topLabels.length >= 2) {
    return `${topLabels.join('·')} 접근성이 뛰어나 ${nudgeText} 관점에서 ${rank}위에 올랐습니다.`;
  }

  return `${topLabels[0]}이(가) 돋보여 ${nudgeText} ${rank}위에 올랐습니다.`;
}
