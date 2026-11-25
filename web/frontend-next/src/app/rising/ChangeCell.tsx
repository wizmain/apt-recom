import { formatChange, isRoundedZero } from "./format";

const NO_COMPARISON_TEXT = "비교 부족";
const SINGLE_TYPE_TEXT = "한 주택형만 비교";

interface ChangeCellProps {
  pct: number | null;
  matchedTypeCount: number | null;
}

/** 변화율 + 신뢰도 문구. 양수 초록·음수 빨강(기존 화면의 emerald/red 계열). */
export default function ChangeCell({ pct, matchedTypeCount }: ChangeCellProps) {
  const note =
    pct === null
      ? NO_COMPARISON_TEXT
      : matchedTypeCount === 1
        ? SINGLE_TYPE_TEXT
        : null;
  const tone =
    pct === null || isRoundedZero(pct)
      ? "text-gray-400"
      : pct > 0
        ? "text-emerald-600"
        : "text-red-500";
  return (
    <div>
      <span className={`font-semibold tabular-nums ${tone}`}>
        {formatChange(pct)}
      </span>
      {note && <span className="block whitespace-nowrap text-[11px] text-gray-400">{note}</span>}
    </div>
  );
}
