import type { RisingMonthlyPoint, RisingRecentTrade } from "@/types/rising";
import { formatBaseMonth, formatEok } from "./format";

const EMPTY_TEXT = "—";
const TRADES_CAPTION =
  "최근 3개월 실거래 전체입니다. 3개월 중위가격 계산에서는 직거래와 이상거래(단지 중앙값 ±25%)를 뺍니다.";

const HEAD = "px-2 py-1.5 text-left text-xs font-medium text-gray-500";
const CELL = "px-2 py-1.5 text-sm tabular-nums text-gray-800";

/** 접이식 월별 가격·거래량 표(차트의 텍스트 대체). */
export function MonthlyTable({ monthly }: { monthly: RisingMonthlyPoint[] }) {
  return (
    <details className="rounded-lg border border-gray-200">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-gray-700">
        월별 가격·거래량 표
      </summary>
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-gray-50">
            <tr>
              <th className={HEAD}>월</th>
              <th className={HEAD}>중위가격</th>
              <th className={HEAD}>거래량</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {[...monthly].reverse().map((point) => (
              <tr key={point.ym}>
                <td className={CELL}>{formatBaseMonth(point.ym)}</td>
                <td className={CELL}>
                  {point.median_price === null ? EMPTY_TEXT : formatEok(point.median_price)}
                </td>
                <td className={CELL}>{point.trade_count}건</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** 최근 3개월 실거래 전체(직거래 포함, 직거래는 태그). */
export function RecentTradesTable({ trades }: { trades: RisingRecentTrade[] }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-gray-800">최근 실거래</h3>
      <p className="mt-1 text-[11px] text-gray-500">{TRADES_CAPTION}</p>
      {trades.length === 0 ? (
        <p className="mt-2 text-sm text-gray-400">최근 3개월 거래가 없습니다.</p>
      ) : (
        <table className="mt-2 w-full">
          <thead className="border-b border-gray-200">
            <tr>
              <th className={HEAD}>계약일</th>
              <th className={HEAD}>전용면적</th>
              <th className={HEAD}>층</th>
              <th className={HEAD}>거래가격</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {trades.map((trade, index) => (
              <tr key={`${trade.deal_date ?? "none"}-${index}`}>
                <td className={CELL}>{trade.deal_date ?? EMPTY_TEXT}</td>
                <td className={CELL}>{trade.exclu_use_ar}㎡</td>
                <td className={CELL}>{trade.floor ?? EMPTY_TEXT}</td>
                <td className={CELL}>
                  {formatEok(trade.deal_amount)}
                  {trade.is_direct_deal && (
                    <span className="ml-1.5 rounded bg-amber-50 px-1 py-0.5 text-[11px] font-medium text-amber-700">
                      직거래
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
