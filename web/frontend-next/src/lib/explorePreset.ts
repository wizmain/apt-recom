// src/lib/explorePreset.ts
import type { CodeItem } from "@/hooks/useCodes";

export interface ExplorePreset {
  code: string;
  title: string;
  emoji: string;
  description: string;
  nudges: string[];
  sigunguCode: string;
  regionLabel: string;
}

interface ExplorePresetExtra {
  emoji?: string;
  description?: string;
  nudges?: string[];
  sigungu_code?: string;
  region_label?: string;
}

/**
 * common_code(group='explore_preset') 행 → ExplorePreset 목록 (D안).
 *
 * extra 는 JSON 문자열 — 파싱에 실패하거나 필수 필드(nudges/sigungu_code/
 * region_label)가 빠진 행은 경고 후 건너뛴다. 운영 중 잘못 입력된 행 하나가
 * 갤러리 전체를 깨뜨리지 않게 하기 위함이다 (시드는 scripts/seed_explore_presets.py).
 */
export function parseExplorePresets(codes: CodeItem[]): ExplorePreset[] {
  const presets: ExplorePreset[] = [];
  for (const item of codes) {
    try {
      const extra = JSON.parse(item.extra) as ExplorePresetExtra;
      if (!Array.isArray(extra.nudges) || extra.nudges.length === 0) throw new Error("nudges 누락");
      if (!extra.sigungu_code || !extra.region_label) throw new Error("지역 필드 누락");
      presets.push({
        code: item.code,
        title: item.name,
        emoji: extra.emoji ?? "🏙",
        description: extra.description ?? "",
        nudges: extra.nudges,
        sigunguCode: extra.sigungu_code,
        regionLabel: extra.region_label,
      });
    } catch (err) {
      console.warn(`explore_preset 행 건너뜀 (${item.code}):`, err);
    }
  }
  return presets;
}
