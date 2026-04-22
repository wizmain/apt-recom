import type { PopulationData } from "@/types/apartment";
import { DataList, Section } from "./_shared";

/**
 * 인구 섹션 — 시군구 단위 총인구·성별.
 * 연령대 분포는 배열이 크므로 상위 3개 그룹만 요약해 본문에 노출.
 */
export function Population({
  population,
}: {
  population: PopulationData | null | undefined;
}) {
  if (!population) return null;

  const { sigungu_name, total_pop, male_pop, female_pop, age_groups } = population;
  if (!sigungu_name && !total_pop) return null;

  const items = [
    sigungu_name ? { label: "지역", value: sigungu_name } : null,
    total_pop
      ? { label: "총인구", value: `${total_pop.toLocaleString()}명` }
      : null,
    male_pop
      ? { label: "남성", value: `${male_pop.toLocaleString()}명` }
      : null,
    female_pop
      ? { label: "여성", value: `${female_pop.toLocaleString()}명` }
      : null,
  ];

  const topAgeGroups = (age_groups ?? [])
    .filter(
      (g): g is { age_group: string; total: number } =>
        !!g && !!g.age_group && typeof g.total === "number",
    )
    .sort((a, b) => b.total - a.total)
    .slice(0, 3);

  return (
    <Section title="인구">
      <DataList items={items} />
      {topAgeGroups.length > 0 ? (
        <p className="mt-3 text-sm text-gray-600">
          상위 연령대:{" "}
          {topAgeGroups
            .map((g) => `${g.age_group} ${g.total.toLocaleString()}명`)
            .join(", ")}
        </p>
      ) : null}
    </Section>
  );
}
