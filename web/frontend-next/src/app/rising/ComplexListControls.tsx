import type { RisingSort } from "@/types/rising";

const SORT_OPTIONS: { value: RisingSort; label: string }[] = [
  { value: "change_6m", label: "6개월 변화율 높은 순" },
  { value: "change_12m", label: "12개월 변화율 높은 순" },
  { value: "relative_6m", label: "지역 대비 상승률 높은 순" },
  { value: "region_price", label: "지역 가격대 높은 순" },
  { value: "complex_rank", label: "지역 내 가격 순위" },
  { value: "price_asc", label: "가격 낮은 순" },
  { value: "budget_near", label: "예산 상한에 가까운 순" },
];

interface ComplexListControlsProps {
  sort: RisingSort;
  query: string;
  onSortChange: (sort: RisingSort) => void;
  onQueryChange: (query: string) => void;
}

/** 단지 목록 정렬 드롭다운 + 단지명 검색창. */
export default function ComplexListControls({
  sort,
  query,
  onSortChange,
  onQueryChange,
}: ComplexListControlsProps) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <input
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="단지명 검색"
        aria-label="단지명 검색"
        className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
      <select
        value={sort}
        onChange={(e) => onSortChange(e.target.value as RisingSort)}
        aria-label="정렬"
        className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
      >
        {SORT_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
