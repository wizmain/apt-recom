import { memo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

export interface RankingItem {
  sigungu_code: string;
  sigungu_name: string;
  volume: number;
  avg_price?: number;
  avg_deposit?: number;
}

interface Props {
  data: RankingItem[];
  type: 'trade' | 'rent';
  onTypeChange: (type: 'trade' | 'rent') => void;
}

function RankingChart({ data, type, onTypeChange }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-700">시군구별 거래량 Top 10</h2>
        <div className="flex bg-gray-100 rounded-full p-0.5">
          <button
            onClick={() => onTypeChange('trade')}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors
              ${type === 'trade' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
          >
            매매
          </button>
          <button
            onClick={() => onTypeChange('rent')}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors
              ${type === 'rent' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
          >
            전월세
          </button>
        </div>
      </div>
      <div className="h-64 sm:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="sigungu_name" tick={{ fontSize: 11 }} width={80} />
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any -- recharts Formatter */}
            <Tooltip formatter={(val: any) => [`${Number(val).toLocaleString()}건`, '거래량']} />
            <Bar dataKey="volume" fill="#3b82f6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default memo(RankingChart);
