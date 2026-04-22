"use client";

import { Section } from "@/components/presentation/Section";
import { DataList } from "@/components/presentation/DataList";

/**
 * 주변시설 요약 — facility_summary 객체의 상위 N 개 카테고리만.
 * 실제 facility_subtype 코드는 common_code 참조로 한국어로 치환 가능하나,
 * 빌드 시점에 얻기 어려워 현재는 코드 그대로 라벨로 사용.
 */

const FACILITY_LABELS: Record<string, string> = {
  subway: "지하철역",
  bus: "버스정류장",
  school_elementary: "초등학교",
  school_middle: "중학교",
  school_high: "고등학교",
  kindergarten: "유치원",
  daycare: "어린이집",
  park: "공원",
  mart: "대형마트",
  hospital: "병원",
  pharmacy: "약국",
  police: "경찰서",
  fire: "소방서",
  convenience: "편의점",
};

const DISPLAY_ORDER = [
  "subway",
  "bus",
  "school_elementary",
  "school_middle",
  "school_high",
  "kindergarten",
  "park",
  "mart",
  "hospital",
  "pharmacy",
  "police",
  "fire",
];

export function Facilities({
  summary,
}: {
  summary:
    | Record<
        string,
        {
          nearest_distance_m?: number | null;
          count_1km?: number | null;
        }
      >
    | null
    | undefined;
}) {
  if (!summary || Object.keys(summary).length === 0) return null;

  const items = DISPLAY_ORDER.map((code) => {
    const entry = summary[code];
    if (!entry) return null;
    const m = entry.nearest_distance_m;
    const cnt = entry.count_1km;
    if (m == null && (cnt == null || cnt === 0)) return null;
    const parts: string[] = [];
    if (m != null) parts.push(`${Math.round(m)}m`);
    if (cnt) parts.push(`1km 내 ${cnt}개`);
    return {
      label: FACILITY_LABELS[code] ?? code,
      value: parts.join(" · "),
    };
  });

  const list = <DataList items={items} />;
  if (!list) return null;
  return <Section title="주변시설">{list}</Section>;
}
