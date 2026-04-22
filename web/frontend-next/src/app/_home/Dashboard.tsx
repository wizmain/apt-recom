"use client";

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { api, isCancel } from '@/lib/api';
import TradeHistoryPanel from './TradeHistoryPanel';
import { useAppStore } from '@/lib/store';

// Recharts를 포함한 차트 컴포넌트를 lazy 로드하여 초기 번들에서 분리.
// 첫 paint는 summary + recent만으로 완료되고, 차트는 별도 chunk로 순차 도착.
const VolumeTrendChart = lazy(() => import('./VolumeTrendChart'));
const PriceJeonseCharts = lazy(() => import('./PriceJeonseCharts'));
const RankingChart = lazy(() => import('./RankingChart'));

interface Summary {
  current_month: string;
  last_updated: string | null;
  new_today: number;
  current_period: string;
  prev_period: string;
  prev_label?: string;
  comparison_mode?: string;
  data_lag_notice?: string;
  trade: { volume: number; median_price_m2: number; prev_volume: number; prev_median_price_m2: number };
  rent: { volume: number; median_deposit_m2: number; prev_volume: number; prev_median_deposit_m2: number };
}

interface TrendItem {
  month: string;
  trade_volume: number;
  trade_avg_price: number;
  trade_avg_price_m2: number;
  rent_volume: number;
  rent_avg_deposit: number;
  jeonse_ratio: number;
}

interface RankingItem {
  sigungu_code: string;
  sigungu_name: string;
  volume: number;
  avg_price?: number;
  avg_deposit?: number;
}

interface RecentTrade {
  apt_nm: string;
  sgg_cd: string;
  sigungu: string;
  area: number | null;
  floor: number | null;
  date: string;
  price?: number;
  deposit?: number;
  monthly_rent?: number;
  pnu?: string;
}

interface RegionOption {
  code: string;
  name: string;
}

const REFRESH_INTERVAL = 5 * 60 * 1000; // 5분

function formatPrice(val: number): string {
  if (val >= 10000) {
    const eok = Math.floor(val / 10000);
    const rest = val % 10000;
    return `${eok}억${String(rest).padStart(4, '0').replace(/(\d)(?=(\d{3})+$)/g, '$1,')}`;
  }
  return `${val.toLocaleString()}`;
}

function changeRate(cur: number, prev: number): { text: string; color: string } {
  if (prev === 0) return { text: '-', color: 'text-gray-400' };
  const rate = ((cur - prev) / prev * 100).toFixed(1);
  const num = parseFloat(rate);
  if (num > 0) return { text: `+${rate}%`, color: 'text-red-500' };
  if (num < 0) return { text: `${rate}%`, color: 'text-blue-500' };
  return { text: '0%', color: 'text-gray-400' };
}

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return '방금 전';
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

export default function Dashboard() {
  const clearKeywords = useAppStore((s) => s.clearKeywords);
  const clearRegion = useAppStore((s) => s.clearRegion);
  const clearSelectedNudges = useAppStore((s) => s.clearSelectedNudges);
  const selectApartment = useAppStore((s) => s.selectApartment);
  const clearHighlights = useAppStore((s) => s.clearHighlights);
  const setFocusApts = useAppStore((s) => s.setFocusApts);
  const focusApartment = useAppStore((s) => s.focusApartment);
  const switchView = useAppStore((s) => s.switchView);

  const handleGoToMap = useCallback(async (aptName: string, _sggCd: string, pnu: string) => {
    clearKeywords();
    clearRegion();
    clearSelectedNudges();
    selectApartment(null);
    clearHighlights();
    setFocusApts([]);
    try {
      const res = await api.get<{ basic?: { lat?: number; lng?: number; bld_nm?: string } }>(
        `/api/apartment/${encodeURIComponent(pnu)}`,
      );
      const b = res.data?.basic;
      if (b?.lat && b?.lng) {
        focusApartment({ pnu, lat: b.lat, lng: b.lng, name: b.bld_nm || aptName });
      }
    } catch {
      // swallow — still switch to map
    } finally {
      switchView('map');
    }
  }, [clearKeywords, clearRegion, clearSelectedNudges, selectApartment, clearHighlights, setFocusApts, focusApartment, switchView]);

  const [summary, setSummary] = useState<Summary | null>(null);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [ranking, setRanking] = useState<RankingItem[]>([]);
  const [recent, setRecent] = useState<RecentTrade[]>([]);
  const [sggFilter, setSggFilter] = useState('');
  const [sggLabel, setSggLabel] = useState('전국');
  const [regionQuery, setRegionQuery] = useState('');
  const [regionResults, setRegionResults] = useState<RegionOption[]>([]);
  const [showRegionDropdown, setShowRegionDropdown] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const [rankingType, setRankingType] = useState<'trade' | 'rent'>('trade');
  const [recentType, setRecentType] = useState<'trade' | 'rent'>('trade');
  const [selectedApt, setSelectedApt] = useState<{ aptName: string; sggCd: string; area: number | null; pnu?: string } | null>(null);
  const [loading, setLoading] = useState(true);

  // 바깥 클릭 시 드롭다운 닫기
  const regionRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (regionRef.current && !regionRef.current.contains(e.target as Node)) {
        setShowRegionDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // 지역 검색 (debounce 200ms + AbortController로 stale 응답 덮어쓰기 방지)
  useEffect(() => {
    if (!regionQuery.trim()) {
      setRegionResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await api.get<RegionOption[]>(`/api/dashboard/regions`, {
          params: { q: regionQuery },
          signal: controller.signal,
        });
        setRegionResults(res.data);
        setHighlightIndex(0);
      } catch (err) {
        if (isCancel(err)) return;
        // 그 외 에러는 무시 (일시적 네트워크 실패 시 사용자가 다시 입력하면 됨)
      }
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [regionQuery]);

  const handleSelectRegion = useCallback((code: string, name: string) => {
    setSggFilter(code);
    setSggLabel(name);
    setRegionQuery('');
    setRegionResults([]);
    setShowRegionDropdown(false);
    setHighlightIndex(-1);
  }, []);

  const dropdownRef = useRef<HTMLDivElement>(null);

  // 하이라이트 변경 시 스크롤 추적
  useEffect(() => {
    if (highlightIndex < 0 || !dropdownRef.current) return;
    const item = dropdownRef.current.children[highlightIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: 'nearest' });
  }, [highlightIndex]);

  const handleRegionKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
    if (!showRegionDropdown || regionResults.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex(prev => (prev + 1) % regionResults.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex(prev => (prev <= 0 ? regionResults.length - 1 : prev - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightIndex >= 0 && highlightIndex < regionResults.length) {
        const r = regionResults[highlightIndex];
        handleSelectRegion(r.code, r.name);
      }
    } else if (e.key === 'Escape') {
      setShowRegionDropdown(false);
      setHighlightIndex(-1);
    }
  }, [showRegionDropdown, regionResults, highlightIndex, handleSelectRegion]);

  const handleClearRegion = useCallback(() => {
    setSggFilter('');
    setSggLabel('전국');
    setRegionQuery('');
    setRegionResults([]);
    setShowRegionDropdown(false);
  }, []);

  const abortRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async () => {
    // 이전 요청 전부 취소 — rankingType/recentType/sggFilter 연타 시 stale 응답이
    // 최신 state를 덮어쓰는 것을 방지.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const signal = controller.signal;

    try {
      // 요약 카드 + 최근 거래를 먼저 로드 (가장 빠름)
      const [summaryRes, recentRes] = await Promise.all([
        api.get<Summary>(`/api/dashboard/summary`, { params: { sigungu: sggFilter }, signal }),
        api.get<RecentTrade[]>(`/api/dashboard/recent`, { params: { type: recentType, limit: 20, sigungu: sggFilter }, signal }),
      ]);
      setSummary(summaryRes.data);
      setRecent(recentRes.data);
      setLoading(false);

      // 차트 + 랭킹은 백그라운드 로드 (이전 데이터 유지하며 업데이트)
      const [trendRes, rankingRes] = await Promise.all([
        api.get<TrendItem[]>(`/api/dashboard/trend`, { params: { months: 12, sigungu: sggFilter }, signal }),
        api.get<RankingItem[]>(`/api/dashboard/ranking`, { params: { type: rankingType }, signal }),
      ]);
      setTrend(trendRes.data);
      setRanking(rankingRes.data);
    } catch (err) {
      if (isCancel(err)) return;
      console.error('대시보드 데이터 로드 실패:', err);
      setLoading(false);
    }
  }, [sggFilter, rankingType, recentType]);

  // 최신 fetchData를 ref로 보관 — interval은 마운트 1회만 설치해 버그 방지.
  const fetchRef = useRef(fetchData);
  useEffect(() => {
    fetchRef.current = fetchData;
  }, [fetchData]);

  // 필터/타입 변경 시 로딩 + fetch (첫 로드 포함).
  useEffect(() => {
    setLoading(true);
    fetchRef.current();
  }, [sggFilter, rankingType, recentType]);

  // 주기적 새로고침 — deps 빈 배열로 한 번만 설치, ref 통해 최신 fetcher 호출.
  useEffect(() => {
    const timer = setInterval(() => fetchRef.current(), REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, []);

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400 text-sm">실거래대시보드 로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-3 sm:px-6 py-4 sm:py-6 space-y-5 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-lg sm:text-xl font-bold text-gray-900">
            {sggFilter ? `${sggLabel} 아파트 거래 동향` : '전국 아파트 거래 동향'}
          </h1>
          {summary?.last_updated && (
            <p className="text-xs text-gray-400 mt-0.5">
              마지막 갱신: {timeAgo(summary.last_updated)}
              {summary.new_today > 0 && summary.new_today < 100000 && (
                <span className="ml-2 text-blue-500">오늘 신규 {summary.new_today.toLocaleString()}건</span>
              )}
            </p>
          )}
        </div>
        <div className="relative" ref={regionRef}>
          <div className="flex items-center gap-2">
            {sggFilter && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 text-blue-700 text-xs rounded-full border border-blue-200">
                {sggLabel}
                <button onClick={handleClearRegion} className="hover:text-blue-900">&times;</button>
              </span>
            )}
            <input
              type="text"
              value={regionQuery}
              onChange={(e) => { setRegionQuery(e.target.value); setShowRegionDropdown(true); }}
              onFocus={() => setShowRegionDropdown(true)}
              onKeyDown={handleRegionKeyDown}
              placeholder={sggFilter ? '지역 변경...' : '지역 검색 (예: 강남, 해운대)'}
              className="w-36 sm:w-44 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
            />
          </div>
          {showRegionDropdown && regionResults.length > 0 && (
            <div ref={dropdownRef} className="absolute right-0 top-full mt-1 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-60 overflow-y-auto">
              {regionResults.map((r, idx) => (
                <button
                  key={r.code}
                  onClick={() => handleSelectRegion(r.code, r.name)}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors
                    ${idx === highlightIndex ? 'bg-blue-50 text-blue-700' : 'hover:bg-blue-50 hover:text-blue-700'}`}
                >
                  {r.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          {[
            { label: `매매 거래량`, value: `${summary.trade.volume.toLocaleString()}건`, sub: summary.current_period, prev: `${summary.prev_label ?? '전년 동기'} ${summary.trade.prev_volume.toLocaleString()}건`, change: changeRate(summary.trade.volume, summary.trade.prev_volume) },
            { label: '㎡당 중위 매매가', value: `${Math.round(summary.trade.median_price_m2).toLocaleString()}만`, sub: `평당 ${Math.round(summary.trade.median_price_m2 * 3.3).toLocaleString()}만`, prev: `${summary.prev_label ?? '전년 동기'} ${Math.round(summary.trade.prev_median_price_m2).toLocaleString()}만/㎡`, change: changeRate(summary.trade.median_price_m2, summary.trade.prev_median_price_m2) },
            { label: `전월세 거래량`, value: `${summary.rent.volume.toLocaleString()}건`, sub: summary.current_period, prev: `${summary.prev_label ?? '전년 동기'} ${summary.rent.prev_volume.toLocaleString()}건`, change: changeRate(summary.rent.volume, summary.rent.prev_volume) },
            { label: '㎡당 중위 전세가', value: `${Math.round(summary.rent.median_deposit_m2).toLocaleString()}만`, sub: `평당 ${Math.round(summary.rent.median_deposit_m2 * 3.3).toLocaleString()}만`, prev: `${summary.prev_label ?? '전년 동기'} ${Math.round(summary.rent.prev_median_deposit_m2).toLocaleString()}만/㎡`, change: changeRate(summary.rent.median_deposit_m2, summary.rent.prev_median_deposit_m2) },
          ].map((card) => (
            <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-3 sm:p-4 shadow-sm">
              <p className="text-xs text-gray-500">{card.label}</p>
              <p className="text-lg sm:text-2xl font-bold text-gray-900 mt-1">{card.value}</p>
              {card.sub && <p className="text-[10px] text-gray-400">{card.sub}</p>}
              <p className={`text-xs mt-0.5 ${card.change.color}`}>
                {card.change.text} <span className="text-gray-400">({card.prev})</span>
              </p>
            </div>
          ))}
        </div>
      )}

      {summary?.data_lag_notice && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 sm:px-4 sm:py-3 shadow-sm">
          <span aria-hidden className="mt-0.5 text-base leading-none">⚠️</span>
          <div className="flex-1">
            <p className="text-xs sm:text-sm font-semibold text-amber-900">데이터 수집 진행 중</p>
            <p className="mt-0.5 text-xs sm:text-[13px] text-amber-800 leading-relaxed">
              {summary.data_lag_notice}
            </p>
          </div>
        </div>
      )}

      {/* Recent trades */}
      {recent.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700">최근 거래 내역</h2>
            <div className="flex bg-gray-100 rounded-full p-0.5">
              <button
                onClick={() => setRecentType('trade')}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors
                  ${recentType === 'trade' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
              >
                매매
              </button>
              <button
                onClick={() => setRecentType('rent')}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors
                  ${recentType === 'rent' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
              >
                전월세
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">거래일</th>
                  <th className="px-3 py-2 text-left font-medium">지역</th>
                  <th className="px-3 py-2 text-left font-medium">단지명</th>
                  <th className="px-3 py-2 text-right font-medium">면적(㎡)</th>
                  <th className="px-3 py-2 text-right font-medium">층</th>
                  <th className="px-3 py-2 text-right font-medium">
                    {recentType === 'trade' ? '매매가(만원)' : '보증금(만원)'}
                  </th>
                  {recentType === 'rent' && (
                    <th className="px-3 py-2 text-right font-medium">월세(만원)</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recent.map((r) => (
                  <tr
                    key={`${r.sgg_cd}-${r.date}-${r.apt_nm}-${r.area ?? ''}-${r.floor ?? ''}`}
                    className="hover:bg-blue-50 cursor-pointer transition-colors"
                    onClick={() => setSelectedApt({ aptName: r.apt_nm, sggCd: r.sgg_cd, area: r.area, pnu: r.pnu })}
                  >
                    <td className="px-3 py-2 text-gray-500 whitespace-nowrap text-xs">{r.date}</td>
                    <td className="px-3 py-2 text-gray-600 whitespace-nowrap text-xs">{r.sigungu}</td>
                    <td className="px-3 py-2 text-gray-900 font-medium truncate max-w-[160px]">{r.apt_nm}</td>
                    <td className="px-3 py-2 text-right text-gray-600">{r.area ? Math.round(r.area) : '-'}</td>
                    <td className="px-3 py-2 text-right text-gray-600">{r.floor ?? '-'}</td>
                    <td className="px-3 py-2 text-right font-semibold text-blue-600">
                      {recentType === 'trade'
                        ? (r.price ? formatPrice(r.price) : '-')
                        : (r.deposit ? formatPrice(r.deposit) : '-')}
                    </td>
                    {recentType === 'rent' && (
                      <td className="px-3 py-2 text-right text-gray-600">
                        {r.monthly_rent ? r.monthly_rent.toLocaleString() : '0'}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trade history modal */}
      {selectedApt && (
        <TradeHistoryPanel
          aptName={selectedApt.aptName}
          sggCd={selectedApt.sggCd}
          area={selectedApt.area}
          pnu={selectedApt.pnu}
          onClose={() => setSelectedApt(null)}
          onGoToMap={handleGoToMap}
        />
      )}

      {/* Volume trend (lazy — recharts 초기 번들 제외) */}
      {trend.length > 0 && (
        <Suspense fallback={<div className="h-56 sm:h-72 bg-gray-50 rounded-xl animate-pulse" />}>
          <VolumeTrendChart data={trend} />
        </Suspense>
      )}

      {/* Price + Jeonse ratio (lazy) */}
      {trend.length > 0 && (
        <Suspense
          fallback={
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="h-48 sm:h-64 bg-gray-50 rounded-xl animate-pulse" />
              <div className="h-48 sm:h-64 bg-gray-50 rounded-xl animate-pulse" />
            </div>
          }
        >
          <PriceJeonseCharts data={trend} />
        </Suspense>
      )}

      {/* Ranking (lazy) */}
      {ranking.length > 0 && (
        <Suspense fallback={<div className="h-64 sm:h-80 bg-gray-50 rounded-xl animate-pulse" />}>
          <RankingChart data={ranking} type={rankingType} onTypeChange={setRankingType} />
        </Suspense>
      )}
    </div>
  );
}
