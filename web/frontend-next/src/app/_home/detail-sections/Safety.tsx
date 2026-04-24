"use client";

import type { SafetyData } from "@/types/apartment";
import { Section } from "@/components/presentation/Section";
import { DataList } from "@/components/presentation/DataList";
import { formatMeters } from "@/components/presentation/format";

/**
 * 안전 섹션 — CCTV/범죄/응급시설 접근성.
 * safety_score 가 null 이면 섹션 생략.
 */
export function Safety({ safety }: { safety: SafetyData | null | undefined }) {
  if (!safety) return null;

  const items = [
    safety.safety_score != null
      ? { label: "안전 점수", value: safety.safety_score.toFixed(1) }
      : null,
    safety.crime_safety_score != null
      ? {
          label: "범죄 안전 점수",
          value: safety.crime_safety_score.toFixed(1),
        }
      : null,
    formatMeters(safety.police_nearest_m)
      ? { label: "가장 가까운 경찰서", value: formatMeters(safety.police_nearest_m)! }
      : null,
    formatMeters(safety.fire_nearest_m)
      ? { label: "가장 가까운 소방서", value: formatMeters(safety.fire_nearest_m)! }
      : null,
    formatMeters(safety.hospital_nearest_m)
      ? {
          label: "가장 가까운 병원",
          value: formatMeters(safety.hospital_nearest_m)!,
        }
      : null,
  ];

  const list = <DataList items={items} />;
  if (!list) return null;

  return (
    <Section title="안전">
      {list}
      {safety.crime_detail ? (
        <p className="mt-2 text-xs text-gray-500">
          * 범죄 점수는 시군구 단위 집계 기반 상대 점수입니다.
        </p>
      ) : null}
    </Section>
  );
}
