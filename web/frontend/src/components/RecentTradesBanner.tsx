import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';

interface RecentTrade {
  apt_nm: string;
  sigungu: string;
  area: number | null;
  floor: number | null;
  date: string;
  price?: number;
  pnu?: string;
}

interface Props {
  onSelect?: (pnu: string, aptName: string) => void;
  onGoToDashboard?: () => void;
  hasResults?: boolean;
}

const REFRESH_INTERVAL_MS = 60_000;
const ROTATE_INTERVAL_MS = 4_000;

function formatPrice(price?: number): string {
  if (!price) return '';
  if (price >= 10_000) {
    const eok = Math.floor(price / 10_000);
    const man = price % 10_000;
    return man > 0 ? `${eok}억 ${man.toLocaleString()}` : `${eok}억`;
  }
  return `${price.toLocaleString()}만`;
}

export default function RecentTradesBanner({ onSelect, onGoToDashboard, hasResults }: Props) {
  const [trades, setTrades] = useState<RecentTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);

  // 최근 거래 조회 (초기 + 60초 주기)
  useEffect(() => {
    let cancelled = false;
    const fetchRecent = async () => {
      try {
        const res = await axios.get<RecentTrade[]>(`${API_BASE}/api/dashboard/recent`, {
          params: { type: 'trade', limit: 20 },
        });
        if (!cancelled) {
          setTrades(res.data);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };
    fetchRecent();
    const timer = window.setInterval(fetchRecent, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // 순환 표시 (확장 상태가 아닐 때만)
  useEffect(() => {
    if (expanded || trades.length === 0) return;
    const timer = window.setInterval(() => {
      setIndex((i) => (i + 1) % trades.length);
    }, ROTATE_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [expanded, trades.length]);

  const current = trades[index];

  const bottomClass = useMemo(() => {
    if (hasResults) return 'bottom-28 sm:bottom-32';
    return 'bottom-4 sm:bottom-6';
  }, [hasResults]);

  if (loading || trades.length === 0 || !current) return null;

  return (
    <div className={`fixed left-4 sm:left-6 z-20 transition-all duration-300 ${bottomClass}`}>
      {expanded ? (
        <div className="bg-white rounded-2xl shadow-xl border border-gray-200 w-72 sm:w-80 max-h-96 overflow-hidden animate-slide-down">
          <div className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white">
            <button
              type="button"
              onClick={() => {
                onGoToDashboard?.();
                setExpanded(false);
              }}
              className="flex items-center gap-2 hover:text-yellow-200 transition-colors group"
              aria-label="실거래 대시보드로 이동"
              title="실거래 대시보드로 이동"
            >
              <span className="inline-block w-2 h-2 rounded-full bg-red-400 animate-pulse" aria-hidden />
              <span className="text-sm font-semibold">실거래대시보드</span>
              <svg
                className="w-3.5 h-3.5 opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-transform"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden
              >
                <path fillRule="evenodd" d="M5.22 14.78a.75.75 0 001.06 0l7.22-7.22v5.69a.75.75 0 001.5 0V5.25a.75.75 0 00-.75-.75H7.47a.75.75 0 000 1.5h5.69l-7.22 7.22a.75.75 0 000 1.06z" clipRule="evenodd" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              aria-label="닫기"
              className="text-white/80 hover:text-white"
            >
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
          <ul className="divide-y divide-gray-100 overflow-y-auto max-h-[21rem]">
            {trades.map((t, i) => (
              <li key={`${t.pnu ?? t.apt_nm}-${i}`}>
                <button
                  type="button"
                  disabled={!t.pnu}
                  onClick={() => {
                    if (t.pnu) {
                      onSelect?.(t.pnu, t.apt_nm);
                      setExpanded(false);
                    }
                  }}
                  className="w-full text-left px-4 py-2.5 hover:bg-blue-50 disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-gray-900 truncate">{t.apt_nm}</span>
                    <span className="text-sm font-bold text-blue-700 flex-shrink-0">{formatPrice(t.price)}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-0.5">
                    <span>{t.date}</span>
                    <span>·</span>
                    <span className="truncate">{t.sigungu}</span>
                    {t.area != null && <><span>·</span><span>{Math.round(t.area)}㎡</span></>}
                    {t.floor != null && <><span>·</span><span>{t.floor}층</span></>}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="group flex items-center gap-2 bg-white/95 backdrop-blur-sm rounded-full shadow-lg border border-gray-200 pl-3 pr-4 py-2 hover:shadow-xl transition-shadow max-w-[calc(100vw-2rem)] sm:max-w-sm"
          aria-label="최근 거래 내역 열기"
        >
          <span className="inline-flex items-center gap-1.5 text-[11px] sm:text-xs font-semibold text-blue-700 flex-shrink-0">
            <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" aria-hidden />
            신규거래
          </span>
          <span className="text-gray-400 text-xs flex-shrink-0">|</span>
          <div className="flex items-center gap-1.5 text-xs sm:text-sm text-gray-800 min-w-0">
            <span className="font-semibold truncate max-w-[6rem] sm:max-w-[10rem]">{current.apt_nm}</span>
            <span className="font-bold text-blue-700 flex-shrink-0">{formatPrice(current.price)}</span>
          </div>
        </button>
      )}
    </div>
  );
}
