"use client";

import { Section } from "@/components/presentation/Section";
import { DataList } from "@/components/presentation/DataList";

/**
 * 라이프 점수(NUDGE) — 카테고리별 0~100 점수.
 * 점수 코드→한국어 라벨은 common_code 에서 받아오는 게 원칙이나 빌드 시점에 얻기
 * 어려우므로 주요 카테고리만 수동 매핑. 매핑 없는 코드는 코드 그대로 표시.
 */
const LABELS: Record<string, string> = {
  cost: "가성비",
  pet: "반려동물",
  commute: "출퇴근",
  newlywed: "신혼부부",
  education: "교육",
  senior: "시니어",
  investment: "투자",
  nature: "자연친화",
  safety: "안전",
};

export function LifeScores({
  scores,
}: {
  scores: Record<string, number> | null | undefined;
}) {
  if (!scores || Object.keys(scores).length === 0) return null;
  // 점수 내림차순
  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const items = sorted.map(([k, v]) => ({
    label: LABELS[k] ?? k,
    value: typeof v === "number" ? v.toFixed(1) : String(v),
  }));
  return (
    <Section title="라이프 점수 (NUDGE)">
      <DataList items={items} />
    </Section>
  );
}
