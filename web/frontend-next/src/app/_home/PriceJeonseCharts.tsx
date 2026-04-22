"use client";

import { memo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

export interface PriceJeonseItem {
  month: string;
  trade_avg_price: number;
  jeonse_ratio: number;
}

interface Props {
  data: PriceJeonseItem[];
}

function formatPrice(val: number): string {
  if (val >= 10000) {
    const eok = Math.floor(val / 10000);
    const rest = val % 10000;
    return `${eok}억${String(rest).padStart(4, '0').replace(/(\d)(?=(\d{3})+$)/g, '$1,')}`;
  }
  return `${val.toLocaleString()}`;
}

function PriceJeonseCharts({ data }: Props) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">평균 매매가 추이</h2>
        <div className="h-48 sm:h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 10 }} />
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any -- recharts Formatter */}
              <Tooltip formatter={(val: any) => [`${formatPrice(Number(val))}`, '평균가']} />
              <Line type="monotone" dataKey="trade_avg_price" name="매매 평균가" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">전세가율 추이</h2>
        <div className="h-48 sm:h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any -- recharts Formatter */}
              <Tooltip formatter={(val: any) => [`${val}%`, '전세가율']} />
              <Line type="monotone" dataKey="jeonse_ratio" name="전세가율" stroke="#10b981" strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

export default memo(PriceJeonseCharts);
