"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RisingMonthlyPoint } from "@/types/rising";
import { formatEok } from "./format";

const PRICE_COLOR = "#2563eb";
const VOLUME_COLOR = "#d1d5db";
const CHART_CAPTION = "2021.11 이전 거래 유형 미분류 포함";
const PRICE_AXIS_ID = "price";
const VOLUME_AXIS_ID = "volume";

interface BandPriceChartProps {
  monthly: RisingMonthlyPoint[];
}

/** 202609 → "26.09" */
function formatShortMonth(ym: number): string {
  const text = String(ym);
  return `${text.slice(2, 4)}.${text.slice(4)}`;
}

/** 가격이 있는 마지막 달만 강조 점을 그린다. */
function findLastPricedYm(monthly: RisingMonthlyPoint[]): number | null {
  for (let i = monthly.length - 1; i >= 0; i -= 1) {
    if (monthly[i].median_price !== null) return monthly[i].ym;
  }
  return null;
}

/** 월별 중위가격(선) + 거래량(막대, 보조 축). 빈 달은 선을 잇는다. */
export default function BandPriceChart({ monthly }: BandPriceChartProps) {
  const lastPricedYm = findLastPricedYm(monthly);
  return (
    <div>
      <div className="h-56 sm:h-64" role="img" aria-label="월별 중위가격과 거래량 차트">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={monthly} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="ym"
              tickFormatter={formatShortMonth}
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis
              yAxisId={PRICE_AXIS_ID}
              tick={{ fontSize: 11 }}
              tickFormatter={formatEok}
              width={44}
              domain={["auto", "auto"]}
            />
            <YAxis
              yAxisId={VOLUME_AXIS_ID}
              orientation="right"
              tick={{ fontSize: 11 }}
              allowDecimals={false}
              width={28}
            />
            <Tooltip
              labelFormatter={(label) => formatShortMonth(Number(label))}
              formatter={(value, name) =>
                name === "중위가격" && typeof value === "number"
                  ? [formatEok(value), name]
                  : [value, name]
              }
            />
            <Bar
              yAxisId={VOLUME_AXIS_ID}
              dataKey="trade_count"
              name="거래량"
              fill={VOLUME_COLOR}
              isAnimationActive={false}
            />
            <Line
              yAxisId={PRICE_AXIS_ID}
              dataKey="median_price"
              name="중위가격"
              type="monotone"
              stroke={PRICE_COLOR}
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
              dot={(props: { cx?: number; cy?: number; payload?: RisingMonthlyPoint }) => {
                const { cx, cy, payload } = props;
                const key = `dot-${payload?.ym}`;
                if (payload?.ym !== lastPricedYm || cx === undefined || cy === undefined) {
                  return <g key={key} />;
                }
                return <circle key={key} cx={cx} cy={cy} r={5} fill={PRICE_COLOR} stroke="#fff" strokeWidth={2} />;
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[11px] text-gray-400">{CHART_CAPTION}</p>
    </div>
  );
}
