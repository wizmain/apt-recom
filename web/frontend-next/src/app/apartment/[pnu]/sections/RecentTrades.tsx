import type { TradesResponse } from "@/types/apartment";
import { Section, formatPriceManwon } from "./_shared";

/** 최근 매매 거래 상위 5건 — 전세/월세는 별도 섹션으로 확장 가능. */
export function RecentTrades({ trades }: { trades: TradesResponse }) {
  const list = trades.trades.slice(0, 5);
  if (list.length === 0) return null;

  return (
    <Section title="최근 매매">
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {list.map((t, i) => {
          const price = formatPriceManwon(t.deal_amount);
          const date = `${t.deal_year}.${String(t.deal_month).padStart(2, "0")}`;
          return (
            <li
              key={i}
              className="flex items-center justify-between gap-3 px-4 py-3 text-sm"
            >
              <span className="text-gray-500 min-w-[56px]">{date}</span>
              <span className="font-medium text-gray-900 flex-1">{price}</span>
              {t.exclu_use_ar ? (
                <span className="text-gray-500">{t.exclu_use_ar}㎡</span>
              ) : null}
              {t.floor ? (
                <span className="text-gray-500 min-w-[32px] text-right">
                  {t.floor}층
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
