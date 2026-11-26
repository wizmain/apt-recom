import type { RisingItem } from "@/types/rising";

const NO_GRADE_TEXT = "등급 없음";
const REGION_GRADE_TITLE = "지역 가격 수준 등급(상승세 아님)";
/** 12개월 창으로만 산출된 등급은 순위 대신 참고 표기. */
const REFERENCE_WINDOW_MONTHS = 12;

interface GradeBadgeProps {
  grade: string | null;
  title?: string;
}

/** 등급 뱃지. grade null → "등급 없음". */
export default function GradeBadge({ grade, title }: GradeBadgeProps) {
  if (grade === null) {
    return (
      <span className="text-xs text-gray-400" title={title}>
        {NO_GRADE_TEXT}
      </span>
    );
  }
  return (
    <span
      title={title}
      className="inline-block rounded bg-blue-50 px-1.5 py-0.5 text-xs font-bold text-blue-700"
    >
      {grade}
    </span>
  );
}

/** 지역 가격 수준 등급 (툴팁으로 상승세 아님을 명시). */
export function RegionGradeBadge({ grade }: { grade: string | null }) {
  return <GradeBadge grade={grade} title={REGION_GRADE_TITLE} />;
}

/** 지역 내 단지 등급 + 순위(rank/total) 또는 "12개월 참고". */
/** 단지 등급 표시에 필요한 필드만 — 목록 항목(RisingItem)과 지도 추세(MapTrend)가 함께 쓴다. */
type ComplexGradeFields = Pick<
  RisingItem,
  "complex_grade" | "grade_window_months" | "complex_rank" | "complex_rank_total"
>;

export function ComplexGradeCell({ item }: { item: ComplexGradeFields }) {
  if (item.complex_grade === null) return <GradeBadge grade={null} />;
  const isReference = item.grade_window_months === REFERENCE_WINDOW_MONTHS;
  const hasRank = item.complex_rank !== null && item.complex_rank_total !== null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <GradeBadge grade={item.complex_grade} />
      {isReference ? (
        <span className="text-xs text-gray-500">12개월 참고</span>
      ) : (
        hasRank && (
          <span className="text-xs tabular-nums text-gray-500">
            {item.complex_rank}/{item.complex_rank_total}
          </span>
        )
      )}
    </span>
  );
}
