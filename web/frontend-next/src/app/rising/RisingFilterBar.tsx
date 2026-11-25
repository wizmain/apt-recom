import type { RisingBand } from "@/types/rising";
import BudgetRange from "./BudgetRange";

/** 이 값(㎡) 이상에서 시작하는 면적대는 "대형" 그룹으로 묶는다 (common_code 의 min_area 기준). */
const LARGE_BAND_MIN_AREA = 100;
const LARGE_GROUP_LABEL = "대형 ▾";

interface RisingFilterBarProps {
  bands: RisingBand[];
  areaBand: string;
  budgetMin: number;
  budgetMax: number;
  onAreaBandChange: (code: string) => void;
  onBudgetChange: (range: { min: number; max: number }) => void;
}

function segmentClass(active: boolean): string {
  return `rounded-lg px-3 py-1.5 text-sm font-medium ${
    active ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"
  }`;
}

/** 면적대 세그먼트(59·84·대형 → 대형 하위 구간) + 예산 범위. */
export default function RisingFilterBar({
  bands,
  areaBand,
  budgetMin,
  budgetMax,
  onAreaBandChange,
  onBudgetChange,
}: RisingFilterBarProps) {
  const standardBands = bands.filter((b) => b.min_area < LARGE_BAND_MIN_AREA);
  const largeBands = bands.filter((b) => b.min_area >= LARGE_BAND_MIN_AREA);
  const isLargeSelected = largeBands.some((b) => b.code === areaBand);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="면적대">
        {standardBands.map((band) => (
          <button
            key={band.code}
            type="button"
            aria-pressed={areaBand === band.code}
            onClick={() => onAreaBandChange(band.code)}
            className={segmentClass(areaBand === band.code)}
          >
            {band.name}
          </button>
        ))}
        {largeBands.length > 0 && (
          <button
            type="button"
            aria-pressed={isLargeSelected}
            onClick={() => !isLargeSelected && onAreaBandChange(largeBands[0].code)}
            className={segmentClass(isLargeSelected)}
          >
            {LARGE_GROUP_LABEL}
          </button>
        )}
      </div>
      {isLargeSelected && (
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="대형 면적 구간">
          {largeBands.map((band) => (
            <button
              key={band.code}
              type="button"
              aria-pressed={areaBand === band.code}
              onClick={() => onAreaBandChange(band.code)}
              className={`rounded-full border px-2.5 py-1 text-xs ${
                areaBand === band.code
                  ? "border-blue-600 bg-blue-50 text-blue-700"
                  : "border-gray-300 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {band.name}
            </button>
          ))}
        </div>
      )}
      <div className="mt-4">
        <BudgetRange budgetMin={budgetMin} budgetMax={budgetMax} onChange={onBudgetChange} />
      </div>
    </div>
  );
}
