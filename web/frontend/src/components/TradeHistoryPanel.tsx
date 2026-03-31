import { useState, useEffect } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';

interface TradeRecord {
  date: string;
  price: number;
  area: number | null;
  floor: number | null;
}

interface RentRecord {
  date: string;
  deposit: number | null;
  monthly_rent: number | null;
  area: number | null;
  floor: number | null;
}

interface TradesResponse {
  apt_nm: string;
  sigungu: string;
  trades: TradeRecord[];
  rents: RentRecord[];
}

interface TradeHistoryPanelProps {
  aptName: string;
  sggCd: string;
  onClose: () => void;
}

function formatPrice(val: number): string {
  if (val >= 10000) {
    const eok = Math.floor(val / 10000);
    const rest = val % 10000;
    return rest > 0 ? `${eok}억${rest.toLocaleString()}` : `${eok}억`;
  }
  return `${val.toLocaleString()}`;
}

export default function TradeHistoryPanel({ aptName, sggCd, onClose }: TradeHistoryPanelProps) {
  const [data, setData] = useState<TradesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'trade' | 'rent'>('trade');

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading must reset when apt changes
    setLoading(true);
    axios.get<TradesResponse>(`${API_BASE}/api/dashboard/trades`, {
      params: { apt_nm: aptName, sgg_cd: sggCd },
    }).then(res => {
      setData(res.data);
    }).finally(() => {
      setLoading(false);
    });
  }, [aptName, sggCd]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-gray-900 truncate">{aptName}</h3>
          {data && <p className="text-xs text-gray-500">{data.sigungu}</p>}
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-gray-200 text-gray-400 hover:text-gray-600 flex-shrink-0"
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-100">
        <TabButton label="매매" count={data?.trades.length ?? 0} active={tab === 'trade'} onClick={() => setTab('trade')} />
        <TabButton label="전월세" count={data?.rents.length ?? 0} active={tab === 'rent'} onClick={() => setTab('rent')} />
      </div>

      {/* Content */}
      <div className="max-h-80 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-gray-400 text-sm">불러오는 중...</div>
        ) : tab === 'trade' ? (
          <TradeTable trades={data?.trades ?? []} />
        ) : (
          <RentTable rents={data?.rents ?? []} />
        )}
      </div>
    </div>
  );
}

/* ── 하위 컴포넌트 ── */

function TabButton({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 py-2 text-xs font-medium text-center transition-colors relative
        ${active ? 'text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
    >
      {label} ({count})
      {active && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600" />}
    </button>
  );
}

function TradeTable({ trades }: { trades: TradeRecord[] }) {
  if (trades.length === 0) return <EmptyMessage text="매매 이력이 없습니다." />;

  return (
    <table className="w-full text-xs">
      <thead className="bg-gray-50 text-gray-500 sticky top-0">
        <tr>
          <th className="px-3 py-1.5 text-left font-medium">거래일</th>
          <th className="px-3 py-1.5 text-right font-medium">면적</th>
          <th className="px-3 py-1.5 text-right font-medium">층</th>
          <th className="px-3 py-1.5 text-right font-medium">매매가</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {trades.map((t, i) => (
          <tr key={i} className="hover:bg-gray-50">
            <td className="px-3 py-1.5 text-gray-500">{t.date}</td>
            <td className="px-3 py-1.5 text-right text-gray-600">{t.area ? `${Math.round(t.area)}㎡` : '-'}</td>
            <td className="px-3 py-1.5 text-right text-gray-600">{t.floor ?? '-'}</td>
            <td className="px-3 py-1.5 text-right font-semibold text-blue-600">{formatPrice(t.price)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RentTable({ rents }: { rents: RentRecord[] }) {
  if (rents.length === 0) return <EmptyMessage text="전월세 이력이 없습니다." />;

  return (
    <table className="w-full text-xs">
      <thead className="bg-gray-50 text-gray-500 sticky top-0">
        <tr>
          <th className="px-3 py-1.5 text-left font-medium">거래일</th>
          <th className="px-3 py-1.5 text-right font-medium">면적</th>
          <th className="px-3 py-1.5 text-right font-medium">층</th>
          <th className="px-3 py-1.5 text-right font-medium">보증금</th>
          <th className="px-3 py-1.5 text-right font-medium">월세</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {rents.map((r, i) => (
          <tr key={i} className="hover:bg-gray-50">
            <td className="px-3 py-1.5 text-gray-500">{r.date}</td>
            <td className="px-3 py-1.5 text-right text-gray-600">{r.area ? `${Math.round(r.area)}㎡` : '-'}</td>
            <td className="px-3 py-1.5 text-right text-gray-600">{r.floor ?? '-'}</td>
            <td className="px-3 py-1.5 text-right font-semibold text-blue-600">{r.deposit ? formatPrice(r.deposit) : '-'}</td>
            <td className="px-3 py-1.5 text-right text-gray-600">{r.monthly_rent ? `${r.monthly_rent.toLocaleString()}` : '0'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EmptyMessage({ text }: { text: string }) {
  return <div className="text-center text-gray-400 text-xs py-8">{text}</div>;
}
