"use client";

import type { SchoolZone } from "@/types/apartment";
import { Section } from "@/components/presentation/Section";
import { DataList } from "@/components/presentation/DataList";

export function School({ school }: { school: SchoolZone | null | undefined }) {
  if (!school) return null;
  const items = [
    school.elementary_school_full_name
      ? { label: "초등학교", value: school.elementary_school_full_name }
      : school.elementary_school_name
        ? { label: "초등학교", value: school.elementary_school_name }
        : null,
    school.middle_school_zone
      ? { label: "중학교 학군", value: school.middle_school_zone }
      : null,
    school.high_school_zone
      ? {
          label: "고등학교 학군",
          value: school.high_school_zone_type
            ? `${school.high_school_zone} (${school.high_school_zone_type})`
            : school.high_school_zone,
        }
      : null,
    school.edu_district
      ? { label: "교육지원청", value: school.edu_district }
      : null,
  ];
  const list = <DataList items={items} />;
  if (!list) return null;
  return <Section title="학군">{list}</Section>;
}
