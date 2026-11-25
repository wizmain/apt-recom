import type { RisingItem, RisingRegion } from "@/types/rising";
import ChangeCell from "./ChangeCell";
import GradeBadge, { RegionGradeBadge } from "./GradeBadge";
import { THIN_SAMPLE_TEXT, formatEok, isThinSample } from "./format";

const REFERENCE_WINDOW_MONTHS = 12;
const DECILE_COUNT = 10;
const DECILE_STEP_PCT = 10;

/** 순위/전체 → 십분위(1~10). rank 1 of 100 → 1. */
export function toDecile(rank: number, total: number): number {
  return Math.min(DECILE_COUNT, Math.max(1, Math.ceil((rank * DECILE_COUNT) / total)));
}

/** 십분위 → "가격 상위 10%"(1분위) / "가격 상위 10–20%". */
export function formatDecileText(decile: number): string {
  if (decile === 1) return `가격 상위 ${DECILE_STEP_PCT}%`;
  return `가격 상위 ${(decile - 1) * DECILE_STEP_PCT}–${decile * DECILE_STEP_PCT}%`;
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-gray-50 p-3">
      <dt className="text-[11px] text-gray-500">{label}</dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
}

function RegionGradeMetric({ region, grade }: { region: RisingRegion | null; grade: string | null }) {
  const hasRank = region?.region_rank != null && region.region_rank_total != null;
  return (
    <>
      <RegionGradeBadge grade={grade} />
      {hasRank && (
        <span className="block text-[11px] text-gray-500">
          {region.region_rank_total}곳 중 {region.region_rank}위
        </span>
      )}
    </>
  );
}

function ComplexGradeMetric({ item }: { item: RisingItem }) {
  if (item.complex_grade === null) return <GradeBadge grade={null} />;
  if (item.grade_window_months === REFERENCE_WINDOW_MONTHS) {
    return (
      <>
        <GradeBadge grade={item.complex_grade} />
        <span className="block text-[11px] text-gray-500">12개월 참고</span>
      </>
    );
  }
  const { complex_rank: rank, complex_rank_total: total } = item;
  return (
    <>
      <GradeBadge grade={item.complex_grade} />
      {rank !== null && total !== null && (
        <span className="block text-[11px] text-gray-500">
          {total}곳 중 {rank}위 · {formatDecileText(toDecile(rank, total))}
        </span>
      )}
    </>
  );
}

interface DetailMetricsProps {
  item: RisingItem;
  region: RisingRegion | null;
}

/** 지표 5칸: 지역 가격 등급 / 지역 내 단지 등급 / 3개월 중위가격 / 6개월 / 12개월. */
export default function DetailMetrics({ item, region }: DetailMetricsProps) {
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <Metric label="지역 가격 등급">
        <RegionGradeMetric region={region} grade={item.region_grade} />
      </Metric>
      <Metric label="지역 내 단지 등급">
        <ComplexGradeMetric item={item} />
      </Metric>
      <Metric label="3개월 중위가격">
        {item.median_price_3m === null ? (
          <span className="text-gray-400">—</span>
        ) : (
          <>
            <span className="font-semibold tabular-nums text-gray-900">
              {formatEok(item.median_price_3m)}
            </span>
            {item.trade_count_3m !== null && (
              <span className="block text-[11px] text-gray-500">{item.trade_count_3m}건 기준</span>
            )}
            {isThinSample(item.trade_count_3m) && (
              <span className="block text-[11px] text-amber-600">{THIN_SAMPLE_TEXT}</span>
            )}
          </>
        )}
      </Metric>
      <Metric label="6개월 변화">
        <ChangeCell pct={item.change_6m_pct} matchedTypeCount={item.matched_type_count_6m} />
        {item.matched_type_count_6m !== null && (
          <span className="block text-[11px] text-gray-500">
            비교 주택형 {item.matched_type_count_6m}개
          </span>
        )}
      </Metric>
      <Metric label="12개월 변화">
        <ChangeCell pct={item.change_12m_pct} matchedTypeCount={item.matched_type_count_12m} />
      </Metric>
    </dl>
  );
}
