import { useState, useEffect, useCallback } from 'react';
import { api } from '../lib/api';
import { useCodes } from '../hooks/useCodes';
import type { TopContributor } from '../types/apartment';
import { buildRankReason, rankEmoji } from '../utils/scoreReason';
import ChartFrame from './ChartFrame';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  LineChart, Line, BarChart, Bar, Legend,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface BasicInfo {
  pnu: string;
  bld_nm: string;
  total_hhld_cnt?: number;
  dong_count?: number;
  max_floor?: number;
  use_apr_day?: string;
  plat_plc?: string;
  new_plat_plc?: string;
  bjd_code?: string;
  sigungu_code?: string;
  lat?: number;
  lng?: number;
  min_area?: number;
  max_area?: number;
  avg_area?: number;
  min_supply_area?: number;
  max_supply_area?: number;
  avg_supply_area?: number;
}

interface KaptInfo {
  sale_type?: string;
  heat_type?: string;
  builder?: string;
  developer?: string;
  apt_type?: string;
  mgr_type?: string;
  hall_type?: string;
  structure?: string;
  total_area?: number;
  priv_area?: number;
  parking_cnt?: number;
  cctv_cnt?: number;
  elevator_cnt?: number;
  ev_charger_cnt?: number;
  subway_info?: string;
  bus_time?: string;
}

interface MgmtCostMonth {
  year_month: string;
  common_cost: number;
  individual_cost: number;
  repair_fund: number;
  total_cost: number;
  cost_per_unit: number;
  detail: Record<string, number>;
}

interface MgmtCostByArea {
  exclusive_area: number;  // 정수 그룹 대표 면적 (예: 84)
  unit_count: number;
  per_unit_cost: number;
  area_min: number;
  area_max: number;
  subtype_count: number;
}

interface MgmtCost {
  months: MgmtCostMonth[];
  region_avg_per_unit: number | null;
  by_area: MgmtCostByArea[] | null;
  cost_per_m2: number | null;
  region_avg_per_m2: number | null;
  latest_year_month: string | null;
}

interface ApartmentDetail {
  basic: BasicInfo;
  scores: Record<string, number>;
  facility_summary: Record<string, { nearest_distance_m: number; count_1km: number; count_3km: number; count_5km: number }>;
  nearby_facilities: Record<string, { name: string; distance_m: number; lat: number; lng: number }[]>;
  school: SchoolInfo | null;
  safety?: SafetyData | null;
  population?: PopulationData;
  kapt_info?: KaptInfo | null;
  mgmt_cost?: MgmtCost | null;
}

interface SchoolInfo {
  elementary_school_name?: string;
  elementary_school_full_name?: string;
  elementary_school_id?: string;
  middle_school_zone?: string;
  high_school_zone?: string;
  high_school_zone_type?: string;
  edu_office_name?: string;
  edu_district?: string;
  estimated?: boolean;
}

interface TradeRecord {
  deal_year: number;
  deal_month: number;
  deal_day: number;
  floor: number;
  exclu_use_ar: number;
  deal_amount: number;
  build_year?: number;
}

interface RentRecord {
  deal_year: number;
  deal_month: number;
  deal_day: number;
  floor: number;
  exclu_use_ar: number;
  deposit: number;
  monthly_rent: number;
}

interface TradesResponse {
  trades: TradeRecord[];
  rents: RentRecord[];
}

/* ------------------------------------------------------------------ */
/*  Labels                                                             */
/* ------------------------------------------------------------------ */

// nudgeLabels, facilityLabels는 컴포넌트 내부에서 useCodes로 로드

const TABS = ['기본정보', '가격분석', '관리비', '주변시설', '학군', '안전', '인구'] as const;
type TabName = (typeof TABS)[number];

const BLUE = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd'];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export interface RankContext {
  rank: number;
  selectedNudges: string[];
  topContributors: TopContributor[];
}

interface DetailModalProps {
  pnu: string;
  onClose: () => void;
  rankContext?: RankContext | null;
}

export default function DetailModal({ pnu, onClose, rankContext }: DetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabName>('기본정보');
  const [detail, setDetail] = useState<ApartmentDetail | null>(null);
  const [tradesData, setTradesData] = useState<TradesResponse>({ trades: [], rents: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading must reset when pnu changes
    setLoading(true);

    Promise.all([
      api.get<ApartmentDetail>(`/api/apartment/${pnu}`),
      api.get<TradesResponse>(`/api/apartment/${pnu}/trades`),
    ])
      .then(([detailRes, tradesRes]) => {
        if (cancelled) return;
        setDetail(detailRes.data);
        setTradesData(tradesRes.data ?? { trades: [], rents: [] });
      })
      .catch((err) => {
        console.error('Failed to fetch apartment detail', err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [pnu]);

  const handleBackdrop = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in"
      onClick={handleBackdrop}
    >
      <div className="relative w-full max-w-4xl h-[95dvh] sm:h-[85vh] mx-2 sm:mx-4 bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between px-4 pt-4 pb-2 sm:px-6 sm:pt-5 sm:pb-3 border-b border-gray-100">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-gray-900 truncate">
              {detail?.basic?.bld_nm ?? '로딩 중...'}
            </h2>
            {detail?.basic?.new_plat_plc && (
              <p className="text-sm text-gray-500 mt-0.5 truncate">{detail.basic.new_plat_plc}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-4 flex-shrink-0 p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="닫기"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 px-2 sm:px-6 overflow-x-auto scrollbar-hide">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-2.5 sm:px-4 py-2 sm:py-2.5 text-sm font-medium transition-colors relative whitespace-nowrap flex-shrink-0
                ${activeTab === tab
                  ? 'text-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
                }`}
            >
              {tab}
              {activeTab === tab && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 rounded-full" />
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3 sm:p-6">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="flex items-center gap-2 text-gray-500 text-sm">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                데이터를 불러오는 중...
              </div>
            </div>
          ) : (
            <>
              {activeTab === '기본정보' && <TabBasicInfo detail={detail} rankContext={rankContext ?? null} />}
              {activeTab === '가격분석' && <TabPriceAnalysis trades={tradesData.trades} rents={tradesData.rents} />}
              {activeTab === '관리비' && <TabMgmtCost mgmtCost={detail?.mgmt_cost ?? undefined} />}
              {activeTab === '주변시설' && <TabFacilities detail={detail} />}
              {activeTab === '학군' && <TabSchool school={detail?.school ?? undefined} />}
              {activeTab === '안전' && <TabSafety safety={detail?.safety} />}
              {activeTab === '인구' && <TabPopulation population={detail?.population} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Tab 1 – 기본정보                                                    */
/* ================================================================== */

function TabBasicInfo({ detail, rankContext }: { detail: ApartmentDetail | null; rankContext: RankContext | null }) {
  const { codeMap: nudgeLabels } = useCodes('nudge');
  const { codeMap: facilityLabels } = useCodes('facility_label');
  if (!detail) return <EmptyState text="기본 정보를 불러올 수 없습니다." />;

  const b = detail.basic;
  const fmtRange = (lo?: number, hi?: number) => {
    const l = lo != null ? Math.round(lo) : null;
    const h = hi != null ? Math.round(hi) : null;
    if (l == null && h == null) return '-';
    if (l != null && h != null) return l === h ? `${l}㎡` : `${l}~${h}㎡`;
    return `${l ?? h}㎡`;
  };
  const exclusiveLabel = fmtRange(b.min_area, b.max_area);
  const supplyLabel = fmtRange(b.min_supply_area, b.max_supply_area);
  const infoItems = [
    { label: '세대수', value: b.total_hhld_cnt != null ? `${b.total_hhld_cnt}세대` : '-' },
    { label: '동수', value: b.dong_count != null ? `${b.dong_count}동` : '-' },
    { label: '최고층', value: b.max_floor != null ? `${b.max_floor}층` : '-' },
    { label: '전용면적', value: exclusiveLabel },
    { label: '공급면적', value: supplyLabel },
    { label: '사용승인일', value: b.use_apr_day ?? '-' },
  ];

  const k = detail.kapt_info;
  const kaptItems = k ? [
    k.builder && { label: '시공사', value: k.builder },
    k.heat_type && { label: '난방', value: k.heat_type },
    k.hall_type && { label: '복도', value: k.hall_type },
    k.structure && { label: '구조', value: k.structure },
    k.parking_cnt && { label: '주차', value: `${k.parking_cnt}대` },
    k.elevator_cnt && { label: '승강기', value: `${k.elevator_cnt}대` },
    k.cctv_cnt && { label: 'CCTV', value: `${k.cctv_cnt}대` },
    k.ev_charger_cnt && { label: '전기차충전', value: `${k.ev_charger_cnt}대` },
    k.mgr_type && { label: '관리', value: k.mgr_type },
    k.sale_type && { label: '분양형태', value: k.sale_type },
  ].filter(Boolean) as { label: string; value: string }[] : [];

  const radarData = detail.scores
    ? Object.entries(detail.scores).map(([key, value]) => ({
        subject: nudgeLabels[key] ?? key,
        score: value,
        fullMark: 100,
      }))
    : [];

  return (
    <div className="space-y-6">
      {/* 순위·기여 요소 요약 배너 (ResultCards에서 열었을 때만) */}
      {rankContext && (
        <RankReasonBanner
          rankContext={rankContext}
          nudgeLabels={nudgeLabels}
          facilityLabels={facilityLabels}
        />
      )}

      {/* Info cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {infoItems.map((item) => (
          <div key={item.label} className="bg-gray-50 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-500">{item.label}</p>
            <p className="text-base font-semibold text-gray-800 mt-1">{item.value}</p>
          </div>
        ))}
      </div>

      {/* K-APT 상세정보 */}
      {kaptItems.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">단지 상세</h3>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {kaptItems.map((item) => (
              <div key={item.label} className="bg-blue-50 rounded-lg px-3 py-2">
                <p className="text-xs text-blue-500">{item.label}</p>
                <p className="text-sm font-semibold text-blue-800">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Radar chart */}
      {radarData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">라이프 점수</h3>
          <ChartFrame className="bg-gray-50 rounded-lg p-3 sm:p-4 h-56 sm:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                <PolarGrid stroke="#e5e7eb" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: '#6b7280' }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Radar name="점수" dataKey="score" stroke={BLUE[0]} fill={BLUE[0]} fillOpacity={0.25} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </ChartFrame>
        </div>
      )}
    </div>
  );
}

function RankReasonBanner({
  rankContext,
  nudgeLabels,
  facilityLabels,
}: {
  rankContext: RankContext;
  nudgeLabels: Record<string, string>;
  facilityLabels: Record<string, string>;
}) {
  const { rank, selectedNudges, topContributors } = rankContext;
  const sentence = buildRankReason({
    rank,
    selectedNudges,
    contributors: topContributors,
    nudgeLabels,
    facilityLabels,
  });
  return (
    <div className="rounded-xl border border-amber-200 bg-gradient-to-r from-amber-50 to-yellow-50 p-3 sm:p-4 flex items-start gap-3">
      <span className="text-2xl flex-shrink-0 leading-none" aria-hidden>
        {rankEmoji(rank)}
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-amber-700 mb-0.5">{rank}위 선정 이유</p>
        <p className="text-sm text-gray-800 leading-relaxed">{sentence}</p>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Tab 2 – 가격분석                                                    */
/* ================================================================== */

function TabPriceAnalysis({ trades, rents }: { trades: TradeRecord[]; rents: RentRecord[] }) {
  if (trades.length === 0 && rents.length === 0) return <EmptyState text="거래 데이터가 없습니다." />;

  const saleTrades = trades;
  const rentTrades = rents;

  // 실제 거래 면적 타입 추출 (ROUND하여 그룹핑, 거래량 상위 5개)
  const AREA_COLORS = ['#93c5fd', '#3b82f6', '#2563eb', '#1e40af', '#7c3aed'];
  const MAX_AREA_TYPES = 5;

  const roundArea = (ar: number) => Math.round(ar);

  const areaCountMap = new Map<number, number>();
  saleTrades.forEach(t => {
    if (t.exclu_use_ar != null) {
      const key = roundArea(t.exclu_use_ar);
      areaCountMap.set(key, (areaCountMap.get(key) ?? 0) + 1);
    }
  });
  // 거래량 상위 면적 타입 (오름차순 정렬)
  const topAreaTypes = [...areaCountMap.entries()]
    .sort(([, a], [, b]) => b - a)
    .slice(0, MAX_AREA_TYPES)
    .map(([area]) => area)
    .sort((a, b) => a - b);

  const areaTypes = topAreaTypes.map((area, idx) => ({
    key: `a${area}`,
    label: `${area}㎡`,
    area,
    color: AREA_COLORS[idx % AREA_COLORS.length],
  }));

  const getAreaType = (ar: number) => {
    const rounded = roundArea(ar);
    const found = areaTypes.find(t => t.area === rounded);
    return found ?? null;
  };

  // Monthly trend by actual area type
  const monthlyByArea = new Map<string, Record<string, { sum: number; cnt: number }>>();
  saleTrades.forEach((t) => {
    if (t.deal_year && t.deal_month && t.deal_amount && t.exclu_use_ar != null) {
      const aType = getAreaType(t.exclu_use_ar);
      if (!aType) return;
      const month = `${t.deal_year}-${String(t.deal_month).padStart(2, '0')}`;
      if (!monthlyByArea.has(month)) monthlyByArea.set(month, {});
      const monthData = monthlyByArea.get(month)!;
      if (!monthData[aType.key]) monthData[aType.key] = { sum: 0, cnt: 0 };
      monthData[aType.key].sum += t.deal_amount;
      monthData[aType.key].cnt += 1;
    }
  });

  const trendData = [...monthlyByArea.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, areas]) => {
      const row: Record<string, unknown> = { month };
      for (const at of areaTypes) {
        const d = areas[at.key];
        row[at.key] = d ? Math.round(d.sum / d.cnt) : null;
      }
      return row;
    });

  // Price by area type (bar chart)
  const areaData = areaTypes.map((at) => {
    const matched = saleTrades.filter(
      (t) => t.exclu_use_ar != null && t.deal_amount != null && roundArea(t.exclu_use_ar) === at.area
    );
    const avg = matched.length > 0
      ? matched.reduce((s, t) => s + (t.deal_amount ?? 0), 0) / matched.length / 10000
      : 0;
    return { range: at.label, avg: parseFloat(avg.toFixed(2)), count: matched.length, color: at.color };
  });

  // Jeonse ratio trend by actual area type
  type JeonseAccum = { tradeSum: number; tradeCnt: number; depositSum: number; depositCnt: number };
  const jeonseByArea = new Map<string, Record<string, JeonseAccum>>();

  saleTrades.forEach((t) => {
    if (t.deal_year && t.deal_month && t.deal_amount && t.exclu_use_ar != null) {
      const aType = getAreaType(t.exclu_use_ar);
      if (!aType) return;
      const month = `${t.deal_year}-${String(t.deal_month).padStart(2, '0')}`;
      if (!jeonseByArea.has(month)) jeonseByArea.set(month, {});
      const monthData = jeonseByArea.get(month)!;
      if (!monthData[aType.key]) monthData[aType.key] = { tradeSum: 0, tradeCnt: 0, depositSum: 0, depositCnt: 0 };
      monthData[aType.key].tradeSum += t.deal_amount;
      monthData[aType.key].tradeCnt += 1;
    }
  });

  rentTrades.forEach((t) => {
    if (t.deal_year && t.deal_month && t.deposit && (!t.monthly_rent || t.monthly_rent === 0) && t.exclu_use_ar != null) {
      const aType = getAreaType(t.exclu_use_ar);
      if (!aType) return;
      const month = `${t.deal_year}-${String(t.deal_month).padStart(2, '0')}`;
      if (!jeonseByArea.has(month)) jeonseByArea.set(month, {});
      const monthData = jeonseByArea.get(month)!;
      if (!monthData[aType.key]) monthData[aType.key] = { tradeSum: 0, tradeCnt: 0, depositSum: 0, depositCnt: 0 };
      monthData[aType.key].depositSum += t.deposit;
      monthData[aType.key].depositCnt += 1;
    }
  });

  // 전세가율에 실제 데이터가 있는 면적 타입 (매매+전세 모두 있어야 함)
  const jeonseAreaKeys = new Set<string>();
  for (const areas of jeonseByArea.values()) {
    for (const [areaKey, v] of Object.entries(areas)) {
      if (v.tradeCnt > 0 && v.depositCnt > 0) jeonseAreaKeys.add(areaKey);
    }
  }
  const jeonseActiveTypes = areaTypes.filter(at => jeonseAreaKeys.has(at.key));

  const jeonseData = [...jeonseByArea.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, areas]) => {
      const row: Record<string, unknown> = { month };
      for (const at of jeonseActiveTypes) {
        const v = areas[at.key];
        if (v && v.tradeCnt > 0 && v.depositCnt > 0) {
          const avgTrade = v.tradeSum / v.tradeCnt;
          const avgDeposit = v.depositSum / v.depositCnt;
          row[at.key] = parseFloat((avgDeposit / avgTrade * 100).toFixed(1));
        } else {
          row[at.key] = null;
        }
      }
      return row;
    })
    .filter(row => jeonseActiveTypes.some(at => row[at.key] != null));

  // Recent trades
  const recentTrades = [...saleTrades]
    .sort((a, b) => {
      const da = (a.deal_year ?? 0) * 10000 + (a.deal_month ?? 0) * 100 + (a.deal_day ?? 0);
      const db = (b.deal_year ?? 0) * 10000 + (b.deal_month ?? 0) * 100 + (b.deal_day ?? 0);
      return db - da;
    })
    .slice(0, 10);

  return (
    <div className="space-y-8">
      {/* 데이터 출처 안내 */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 leading-relaxed flex items-start gap-2">
        <span aria-hidden className="flex-shrink-0">ⓘ</span>
        <span>
          국토교통부 실거래가 신고 자료 원본입니다. 일부 거래는 가족간 직거래·1층 할인·신고 입력 오류 등으로 시세와 다를 수 있습니다.
        </span>
      </div>

      {/* Price trend by area */}
      {trendData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">월별 매매가 추이 (면적별)</h3>
          <ChartFrame className="bg-gray-50 rounded-lg p-3 sm:p-4 h-56 sm:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} angle={-45} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => fmtManwon(v)} />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- recharts Formatter type is complex
                  formatter={(val: any, name: any) => {
                    const at = areaTypes.find((t: { key: string }) => t.key === name);
                    return [fmtManwon(Number(val)), at?.label ?? name];
                  }}
                />
                <Legend
                  formatter={(value: string) => {
                    const at = areaTypes.find(t => t.key === value);
                    return at?.label ?? value;
                  }}
                />
                {areaTypes.map((at) => (
                  <Line
                    key={at.key}
                    type="monotone"
                    dataKey={at.key}
                    stroke={at.color}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </ChartFrame>
        </div>
      )}

      {/* Price by area */}
      {areaData.some((d) => d.count > 0) && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">면적별 평균가</h3>
          <ChartFrame className="bg-gray-50 rounded-lg p-3 sm:p-4 h-56 sm:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={areaData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="range" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: '억원', position: 'insideTopLeft', offset: -5, fontSize: 11 }} />
                <Tooltip formatter={(val) => [`${val}억원`, '평균가']} />
                <Bar dataKey="avg" fill={BLUE[1]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartFrame>
        </div>
      )}

      {/* Jeonse ratio by area */}
      {jeonseData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">전세가율 추이 (면적별)</h3>
          <ChartFrame className="bg-gray-50 rounded-lg p-3 sm:p-4 h-56 sm:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={jeonseData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} angle={-45} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} label={{ value: '%', position: 'insideTopLeft', offset: -5, fontSize: 11 }} />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- recharts Formatter type is complex
                  formatter={(val: any, name: any) => {
                    const at = jeonseActiveTypes.find((t: { key: string }) => t.key === name);
                    return [`${val}%`, at?.label ?? name];
                  }}
                />
                <Legend
                  formatter={(value: string) => {
                    const at = jeonseActiveTypes.find(t => t.key === value);
                    return at?.label ?? value;
                  }}
                />
                {jeonseActiveTypes.map((at) => (
                  <Line
                    key={at.key}
                    type="monotone"
                    dataKey={at.key}
                    stroke={at.color}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </ChartFrame>
        </div>
      )}

      {/* Recent trades table */}
      {recentTrades.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">최근 거래 내역</h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">거래일</th>
                  <th className="px-3 py-2 text-right font-medium">층</th>
                  <th className="px-3 py-2 text-right font-medium">면적(㎡)</th>
                  <th className="px-3 py-2 text-right font-medium">가격(만원)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentTrades.map((t, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-gray-700">
                      {t.deal_year}.{String(t.deal_month ?? '').padStart(2, '0')}.{String(t.deal_day ?? '').padStart(2, '0')}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-700">{t.floor ?? '-'}</td>
                    <td className="px-3 py-2 text-right text-gray-700">{t.exclu_use_ar ?? '-'}</td>
                    <td className="px-3 py-2 text-right font-medium text-blue-600">
                      {t.deal_amount != null ? fmtManwon(t.deal_amount) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  Tab 3 – 주변시설                                                    */
/* ================================================================== */

function TabFacilities({ detail }: { detail: ApartmentDetail | null }) {
  const { codeMap: facilityLabels } = useCodes('facility_label');
  if (!detail) return <EmptyState text="주변 시설 데이터가 없습니다." />;

  const summary = detail.facility_summary;
  const nearby = detail.nearby_facilities;

  const facilityEntries = Object.entries(summary).sort((a, b) => a[1].nearest_distance_m - b[1].nearest_distance_m);

  // Bar chart data
  const barData = facilityEntries.map(([subtype, data]) => ({
    type: facilityLabels[subtype] ?? subtype,
    count: data.count_1km ?? 0,
  }));

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {facilityEntries.map(([subtype, data]) => (
          <div key={subtype} className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">
              {facilityLabels[subtype] ?? subtype}
            </p>
            <p className="text-sm font-semibold text-gray-800">
              {data.nearest_distance_m >= 5000 ? '최근접 없음' : `최근접 ${Math.round(data.nearest_distance_m)}m`}
            </p>
            <div className="flex gap-3 mt-1 text-xs text-gray-500">
              <span>1km: {data.count_1km}개</span>
              <span>3km: {data.count_3km}개</span>
            </div>
          </div>
        ))}
      </div>

      {/* Bar chart */}
      {barData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">1km 내 시설 수</h3>
          <ChartFrame className="bg-gray-50 rounded-lg p-3 sm:p-4 h-56 sm:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} layout="vertical" margin={{ left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="type" tick={{ fontSize: 11 }} width={65} />
                <Tooltip formatter={(val) => [`${val}개`, '시설 수']} />
                <Bar dataKey="count" fill={BLUE[1]} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartFrame>
        </div>
      )}

      {/* Nearest facilities list */}
      {Object.keys(nearby).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">가장 가까운 시설</h3>
          <div className="space-y-2">
            {Object.entries(nearby).map(([type, items]) => (
              <div key={type} className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-medium text-gray-600 mb-1">{facilityLabels[type] ?? type}</p>
                <div className="space-y-1">
                  {items.slice(0, 3).map((item, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-gray-700">{item.name}</span>
                      <span className="text-gray-500">{Math.round(item.distance_m)}m</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  Tab – 관리비                                                        */
/* ================================================================== */

function formatWon(val: number): string {
  if (val >= 10000) return `${Math.round(val / 10000)}만`;
  return `${val.toLocaleString()}`;
}

function TabMgmtCost({ mgmtCost }: { mgmtCost?: MgmtCost }) {
  if (!mgmtCost || mgmtCost.months.length === 0) return <EmptyState text="관리비 데이터가 없습니다." />;

  const latest = mgmtCost.months[0];
  const detail = typeof latest.detail === 'string' ? JSON.parse(latest.detail) : latest.detail;
  const regionAvg = mgmtCost.region_avg_per_unit;
  const diff = regionAvg ? latest.cost_per_unit - regionAvg : null;

  // 주요 항목 정렬 (금액 큰 순)
  const detailItems = Object.entries(detail as Record<string, number>)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a);

  const perM2 = mgmtCost.cost_per_m2;
  const regionM2 = mgmtCost.region_avg_per_m2;
  const diffM2 = perM2 && regionM2 ? perM2 - regionM2 : null;

  return (
    <div className="space-y-4">
      {/* 요약 카드 — 세대당 + 단위면적당 통합 */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {/* 이 단지 세대 평균 */}
        <div className="bg-blue-50 rounded-lg p-3 text-center">
          <p className="text-xs text-blue-500">세대 평균 관리비</p>
          <p className="text-base sm:text-lg font-bold text-blue-800 mt-0.5">
            {formatWon(latest.cost_per_unit)}원
          </p>
          {perM2 && (
            <p className="text-[11px] text-blue-600 mt-0.5">
              {perM2.toLocaleString()}<span className="text-[10px] ml-0.5">원/㎡</span>
            </p>
          )}
        </div>
        {/* 지역 평균 */}
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500">지역 평균</p>
          <p className="text-base sm:text-lg font-semibold text-gray-800 mt-0.5">
            {regionAvg ? `${formatWon(regionAvg)}원` : '—'}
          </p>
          {regionM2 && (
            <p className="text-[11px] text-gray-600 mt-0.5">
              {regionM2.toLocaleString()}<span className="text-[10px] ml-0.5">원/㎡</span>
            </p>
          )}
        </div>
        {/* 지역 대비 */}
        <div className={`rounded-lg p-3 text-center ${
          diff !== null ? (diff > 0 ? 'bg-red-50' : 'bg-green-50') : 'bg-gray-50'
        }`}>
          <p className={`text-xs ${
            diff !== null ? (diff > 0 ? 'text-red-500' : 'text-green-500') : 'text-gray-500'
          }`}>지역 대비</p>
          <p className={`text-base sm:text-lg font-semibold mt-0.5 ${
            diff !== null ? (diff > 0 ? 'text-red-700' : 'text-green-700') : 'text-gray-800'
          }`}>
            {diff !== null ? `${diff > 0 ? '+' : ''}${formatWon(diff)}원` : '—'}
          </p>
          {diffM2 !== null && (
            <p className={`text-[11px] mt-0.5 ${diffM2 > 0 ? 'text-red-600' : 'text-green-600'}`}>
              {diffM2 > 0 ? '+' : ''}{diffM2.toLocaleString()}<span className="text-[10px] ml-0.5">원/㎡</span>
            </p>
          )}
        </div>
      </div>
      {perM2 && (
        <p className="text-[11px] text-gray-400 -mt-2">* 원/㎡ 수치는 관리비부과면적 기준</p>
      )}

      {/* 공용/개별/장충금 비율 */}
      <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex justify-between text-xs text-gray-500 mb-2">
          <span>공용관리비</span><span>개별사용료</span><span>장기수선</span>
        </div>
        <div className="flex h-4 rounded-full overflow-hidden">
          {latest.total_cost > 0 && (
            <>
              <div className="bg-blue-400" style={{ width: `${(latest.common_cost / latest.total_cost) * 100}%` }} />
              <div className="bg-amber-400" style={{ width: `${(latest.individual_cost / latest.total_cost) * 100}%` }} />
              <div className="bg-green-400" style={{ width: `${(latest.repair_fund / latest.total_cost) * 100}%` }} />
            </>
          )}
        </div>
        <div className="flex justify-between text-xs text-gray-600 mt-1">
          <span>{formatWon(latest.common_cost)}원</span>
          <span>{formatWon(latest.individual_cost)}원</span>
          <span>{formatWon(latest.repair_fund)}원</span>
        </div>
      </div>

      {/* 면적별 관리비 (K-APT 면적 데이터 있는 경우만) */}
      {mgmtCost.by_area && mgmtCost.by_area.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-700">
              면적별 관리비
              {mgmtCost.latest_year_month && (
                <span className="text-xs text-gray-500 ml-2">
                  ({mgmtCost.latest_year_month.slice(0, 4)}.{mgmtCost.latest_year_month.slice(4)})
                </span>
              )}
            </h3>
            <span className="text-[11px] text-gray-400">전용면적 비례 추정</span>
          </div>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">전용면적</th>
                  <th className="text-right px-3 py-2 font-medium">세대수</th>
                  <th className="text-right px-3 py-2 font-medium">세대당</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {mgmtCost.by_area.map(r => (
                  <tr key={r.exclusive_area} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-gray-800">
                      <span className="font-medium">{r.exclusive_area}㎡</span>
                      {r.subtype_count > 1 && (
                        <span className="ml-2 text-[11px] text-gray-400">
                          {r.area_min.toFixed(2)}~{r.area_max.toFixed(2)} · {r.subtype_count}개 타입
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600">{r.unit_count}</td>
                    <td className="px-3 py-2 text-right font-semibold text-gray-900">
                      {r.per_unit_cost.toLocaleString()}원
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 월별 추이 (여러 달 있을 때) */}
      {mgmtCost.months.length > 1 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">월별 추이</h3>
          <div className="space-y-1">
            {mgmtCost.months.map(m => (
              <div key={m.year_month} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                <span className="text-sm text-gray-600">{m.year_month.slice(0, 4)}.{m.year_month.slice(4)}</span>
                <span className="text-sm font-semibold text-gray-800">{formatWon(m.cost_per_unit)}원/세대</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 항목별 상세 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">항목별 상세 ({latest.year_month.slice(0, 4)}.{latest.year_month.slice(4)})</h3>
        <div className="grid grid-cols-2 gap-2">
          {detailItems.map(([name, val]) => (
            <div key={name} className="flex justify-between bg-gray-50 rounded-lg px-3 py-2">
              <span className="text-xs text-gray-600 truncate">{name}</span>
              <span className="text-xs font-semibold text-gray-800 ml-2">{Math.round(val / 10000).toLocaleString()}만원</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Tab – 학군                                                       */
/* ================================================================== */

function TabSchool({ school }: { school?: SchoolInfo }) {
  if (!school) return <EmptyState text="학군 데이터가 없습니다." />;

  const items = [
    { label: '초등학교', value: school.elementary_school_name ?? '-', sub: school.elementary_school_full_name },
    { label: '초등학교 ID', value: school.elementary_school_id ?? '-' },
    { label: '중학교 학군', value: school.middle_school_zone ?? '-' },
    { label: '고등학교 학군', value: school.high_school_zone ?? '-', sub: school.high_school_zone_type ? `(${school.high_school_zone_type})` : undefined },
    { label: '교육지원청', value: school.edu_district ?? school.edu_office_name ?? '-' },
  ];

  return (
    <div>
      {school.estimated && (
        <div className="mb-3 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
          동일 법정동 기준 예상 학군 정보입니다. 정확한 배정은 해당 교육청에 확인하세요.
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {items.map((item) => (
          <div key={item.label} className="bg-gray-50 rounded-lg p-4">
            <p className="text-xs text-gray-500 mb-1">{item.label}</p>
            <p className="text-base font-semibold text-gray-800">{item.value}</p>
            {item.sub && <p className="text-sm text-gray-500 mt-0.5">{item.sub}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Tab 5 – 인구                                                       */
/* ================================================================== */

interface PopulationData {
  sigungu_name: string;
  total_pop: number;
  male_pop: number;
  female_pop: number;
  age_groups: {
    age_group: string;
    total: number;
    ratio: number;
    male: number;
    female: number;
  }[];
}

function TabPopulation({ population }: { population?: PopulationData }) {
  if (!population) return <EmptyState text="인구 데이터가 없습니다." />;

  const maleRatio = ((population.male_pop / population.total_pop) * 100).toFixed(1);
  const femaleRatio = ((population.female_pop / population.total_pop) * 100).toFixed(1);

  // 연령대 정렬 (숫자 순)
  const sorted = [...population.age_groups].sort((a, b) => {
    const numA = parseInt(a.age_group);
    const numB = parseInt(b.age_group);
    if (isNaN(numA)) return 1;
    if (isNaN(numB)) return -1;
    return numA - numB;
  });

  // 주요 연령대 그룹
  const young = sorted.filter(g => parseInt(g.age_group) < 20).reduce((s, g) => s + g.total, 0);
  const working = sorted.filter(g => { const n = parseInt(g.age_group); return n >= 20 && n < 65; }).reduce((s, g) => s + g.total, 0);
  const senior = sorted.filter(g => parseInt(g.age_group) >= 65).reduce((s, g) => s + g.total, 0);
  const total = population.total_pop || 1;

  return (
    <div className="space-y-6">
      {/* 개요 카드 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          {population.sigungu_name} 인구 현황
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-50 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-500">총 인구</p>
            <p className="text-base font-semibold text-gray-800">{population.total_pop.toLocaleString()}명</p>
          </div>
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="text-xs text-blue-600">남자</p>
            <p className="text-base font-semibold text-blue-700">{maleRatio}%</p>
          </div>
          <div className="bg-pink-50 rounded-lg p-3 text-center">
            <p className="text-xs text-pink-600">여자</p>
            <p className="text-base font-semibold text-pink-700">{femaleRatio}%</p>
          </div>
        </div>
      </div>

      {/* 주요 연령대 비중 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">연령대별 비중</h3>
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <p className="text-xs text-green-600">유소년 (0~19세)</p>
            <p className="text-lg font-bold text-green-700">{((young / total) * 100).toFixed(1)}%</p>
            <p className="text-xs text-gray-500">{young.toLocaleString()}명</p>
          </div>
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="text-xs text-blue-600">생산연령 (20~64세)</p>
            <p className="text-lg font-bold text-blue-700">{((working / total) * 100).toFixed(1)}%</p>
            <p className="text-xs text-gray-500">{working.toLocaleString()}명</p>
          </div>
          <div className="bg-orange-50 rounded-lg p-3 text-center">
            <p className="text-xs text-orange-600">고령 (65세+)</p>
            <p className="text-lg font-bold text-orange-700">{((senior / total) * 100).toFixed(1)}%</p>
            <p className="text-xs text-gray-500">{senior.toLocaleString()}명</p>
          </div>
        </div>
      </div>

      {/* 인구 피라미드 (가로 바) */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">연령대별 인구 분포</h3>
        <div className="space-y-1">
          {sorted.map((g) => {
            const maxRatio = Math.max(...sorted.map(x => x.ratio));
            const barWidth = (g.ratio / maxRatio) * 100;
            const maleW = g.total > 0 ? (g.male / g.total) * barWidth : 0;
            const femaleW = g.total > 0 ? (g.female / g.total) * barWidth : 0;
            return (
              <div key={g.age_group} className="flex items-center gap-2">
                <span className="text-xs text-gray-500 w-14 text-right shrink-0">{g.age_group}세</span>
                <div className="flex-1 flex h-4 rounded overflow-hidden bg-gray-100">
                  <div
                    className="bg-blue-400 h-full"
                    style={{ width: `${maleW}%` }}
                    title={`남 ${g.male.toLocaleString()}`}
                  />
                  <div
                    className="bg-pink-400 h-full"
                    style={{ width: `${femaleW}%` }}
                    title={`여 ${g.female.toLocaleString()}`}
                  />
                </div>
                <span className="text-xs text-gray-500 w-12 shrink-0">{g.ratio}%</span>
              </div>
            );
          })}
        </div>
        <div className="flex justify-center gap-4 mt-2 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-blue-400 rounded-sm inline-block"></span> 남자</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-pink-400 rounded-sm inline-block"></span> 여자</span>
        </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Shared                                                             */
/* ================================================================== */

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
      {text}
    </div>
  );
}

/* ── Safety Tab ── */

interface CrimeDetail {
  murder?: number;
  robbery?: number;
  sexual_assault?: number;
  theft?: number;
  violence?: number;
  total_crime?: number;
  resident_pop?: number;
  effective_pop?: number;
  crime_rate?: number;
  float_pop_ratio?: number;
}

interface V3Scores {
  complex_score?: number;
  complex_cctv_score?: number;
  complex_security_score?: number;
  complex_mgr_score?: number;
  complex_parking_score?: number;
  access_score?: number;
  regional_safety_score?: number;
  crime_adjust_score?: number;
  data_reliability?: number;
  complex_data_source?: string;
  // v2 호환
  micro_score?: number;
  macro_score?: number;
}

interface RegionalGrades {
  traffic: number;
  fire: number;
  crime: number;
  living_safety: number;
  region_name?: string;
}

interface KaptSecurity {
  cctv_cnt?: number;
  parking_cnt?: number;
  mgr_type?: string;
  total_hhld_cnt?: number;
  security_cost_per_unit?: number;
}

interface SafetyData {
  safety_score?: number;
  score_version?: number;
  crime_safety_score?: number;
  crime_detail?: CrimeDetail | null;
  police_nearest_m?: number;
  fire_nearest_m?: number;
  fire_center_nearest_m?: number;
  hospital_nearest_m?: number;
  nudge_safety_score?: number;
  v3?: V3Scores | null;
  regional_grades?: RegionalGrades | null;
  kapt_security?: KaptSecurity | null;
}

function TabSafety({ safety }: { safety?: SafetyData | null }) {
  if (!safety) return <EmptyState text="안전 정보가 없습니다." />;

  const crimeScore = safety.crime_safety_score ?? 0;
  const v3 = safety.v3;
  const isV3 = safety.score_version === 3;
  const isFallback = v3?.complex_data_source && v3.complex_data_source !== 'kapt_actual';

  return (
    <div className="space-y-6">
      {/* v3 3영역 점수 */}
      {v3 && isV3 && (
        <div>
          <h3 className="text-sm font-bold text-gray-700 mb-3">영역별 안전 점수</h3>
          <div className="grid grid-cols-3 gap-3">
            <AreaScoreCard title="단지보안" score={v3.complex_score ?? 0} maxScore={35} desc="CCTV·경비·관리·주차" color="#10b981" />
            <AreaScoreCard title="응급접근" score={v3.access_score ?? 0} maxScore={30} desc="소방·병원·경찰" color="#3b82f6" />
            <AreaScoreCard title="지역안전" score={(v3.regional_safety_score ?? 0) + (v3.crime_adjust_score ?? 0)} maxScore={35} desc="안전지수·범죄율" color="#8b5cf6" />
          </div>
        </div>
      )}

      {/* 단지 보안 현황 */}
      {safety.kapt_security && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-bold text-gray-700">단지 보안 현황</h3>
            {isFallback && (
              <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">시군구 평균 추정</span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">📹</span>
                <span className="text-xs font-semibold text-gray-700">단지 CCTV</span>
              </div>
              <div className="text-xl font-bold text-gray-800">
                {safety.kapt_security.cctv_cnt ?? '-'}
                <span className="text-xs font-normal text-gray-400 ml-1">대</span>
              </div>
              {safety.kapt_security.total_hhld_cnt && safety.kapt_security.cctv_cnt != null && (
                <div className="text-[10px] text-gray-500 mt-1">
                  세대당 {(safety.kapt_security.cctv_cnt / safety.kapt_security.total_hhld_cnt).toFixed(2)}대
                </div>
              )}
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">💰</span>
                <span className="text-xs font-semibold text-gray-700">경비비</span>
              </div>
              <div className="text-xl font-bold text-gray-800">
                {safety.kapt_security.security_cost_per_unit != null
                  ? `${safety.kapt_security.security_cost_per_unit.toLocaleString()}`
                  : '-'}
                <span className="text-xs font-normal text-gray-400 ml-1">원/세대</span>
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">🏗</span>
                <span className="text-xs font-semibold text-gray-700">관리방식</span>
              </div>
              <div className="text-lg font-bold text-gray-800">
                {safety.kapt_security.mgr_type || '-'}
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">🅿</span>
                <span className="text-xs font-semibold text-gray-700">주차</span>
              </div>
              <div className="text-xl font-bold text-gray-800">
                {safety.kapt_security.parking_cnt ?? '-'}
                <span className="text-xs font-normal text-gray-400 ml-1">대</span>
              </div>
              {safety.kapt_security.total_hhld_cnt && safety.kapt_security.parking_cnt != null && (
                <div className="text-[10px] text-gray-500 mt-1">
                  세대당 {(safety.kapt_security.parking_cnt / safety.kapt_security.total_hhld_cnt).toFixed(1)}대
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 응급시설 접근성 */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3">응급시설 접근성</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white border border-gray-200 rounded-xl p-3.5">
            <div className="flex items-center gap-2 mb-2.5">
              <span className="text-lg">🚒</span>
              <span className="text-sm font-bold text-gray-800">소방서/119</span>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">소방서</span>
                <span className="font-medium text-gray-800">{fmtDist(safety.fire_nearest_m)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">119센터</span>
                <span className="font-medium text-gray-800">{fmtDist(safety.fire_center_nearest_m)}</span>
              </div>
            </div>
          </div>
          <div className="bg-white border border-gray-200 rounded-xl p-3.5">
            <div className="flex items-center gap-2 mb-2.5">
              <span className="text-lg">🏥</span>
              <span className="text-sm font-bold text-gray-800">병원</span>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">최근접</span>
                <span className="font-medium text-gray-800">{fmtDist(safety.hospital_nearest_m)}</span>
              </div>
            </div>
          </div>
          {safety.police_nearest_m != null && (
            <div className="bg-white border border-gray-200 rounded-xl p-3.5">
              <div className="flex items-center gap-2 mb-2.5">
                <span className="text-lg">👮</span>
                <span className="text-sm font-bold text-gray-800">경찰서</span>
              </div>
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">최근접</span>
                  <span className="font-medium text-gray-800">{fmtDist(safety.police_nearest_m)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 지역 안전 등급 (행안부) */}
      {safety.regional_grades && (
        <div>
          <h3 className="text-sm font-bold text-gray-700 mb-3">지역 안전 등급 {safety.regional_grades.region_name && <span className="font-normal text-gray-500">({safety.regional_grades.region_name})</span>}</h3>
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="space-y-3">
              {[
                { key: 'living_safety', label: '생활안전', grade: safety.regional_grades.living_safety },
                { key: 'crime', label: '범죄', grade: safety.regional_grades.crime },
                { key: 'fire', label: '화재', grade: safety.regional_grades.fire },
                { key: 'traffic', label: '교통사고', grade: safety.regional_grades.traffic },
              ].map(item => {
                const labels = ['', '우수', '양호', '보통', '주의', '위험'];
                const barColor = item.grade <= 1 ? '#10b981' : item.grade <= 2 ? '#34d399' :
                  item.grade <= 3 ? '#60a5fa' : item.grade <= 4 ? '#f59e0b' : '#ef4444';
                const textColor = item.grade <= 2 ? 'text-emerald-600' : item.grade <= 3 ? 'text-blue-500' : 'text-amber-600';
                return (
                  <div key={item.key} className="flex items-center gap-3">
                    <span className="text-xs text-gray-600 w-16 shrink-0">{item.label}</span>
                    <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${item.grade * 20}%`, backgroundColor: barColor }} />
                    </div>
                    <span className={`text-xs font-bold w-14 text-right shrink-0 ${textColor}`}>
                      {item.grade}등급 {labels[item.grade]}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="text-[10px] text-gray-400 mt-3">
              * 행정안전부 지역안전지수 (1등급=우수, 5등급=위험)
            </p>
          </div>
        </div>
      )}

      {/* 범죄 안전 지수 */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3">지역 범죄 안전 지수</h3>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-4 mb-3">
            <span className="text-2xl">🛡</span>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-600">범죄 안전도</span>
                <span className={`text-lg font-bold ${crimeScore >= 70 ? 'text-teal-600' : crimeScore >= 40 ? 'text-slate-600' : 'text-amber-700'}`}>
                  {crimeScore.toFixed(1)}점
                </span>
              </div>
              <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${Math.min(crimeScore, 100)}%`,
                    backgroundColor: crimeScore >= 70 ? '#5aab9a' : crimeScore >= 40 ? '#7ca8b0' : '#c4a46e',
                  }}
                />
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-500">
            {crimeScore >= 70 ? '이 지역은 범죄 발생률이 낮아 안전한 편입니다.' :
             crimeScore >= 40 ? '이 지역은 평균적인 범죄 발생률을 보입니다.' :
             '이 지역은 범죄 발생률이 다소 높은 편입니다. 야간 이동 시 주의가 필요합니다.'}
          </p>
          <p className="text-[10px] text-gray-400 mt-1">
            * 2024년 경찰청 범죄통계 기반, 인구 10만명당 범죄율 산정
          </p>
        </div>
      </div>

      {/* 범죄 유형 분석 */}
      {safety.crime_detail && (
        <div>
          <h3 className="text-sm font-bold text-gray-700 mb-3">범죄 유형 분석 (2024)</h3>
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="space-y-3">
              {[
                { key: 'violence', label: '폭력', count: safety.crime_detail.violence ?? 0 },
                { key: 'theft', label: '절도', count: safety.crime_detail.theft ?? 0 },
                { key: 'sexual_assault', label: '강간·강제추행', count: safety.crime_detail.sexual_assault ?? 0 },
                { key: 'robbery', label: '강도', count: safety.crime_detail.robbery ?? 0 },
                { key: 'murder', label: '살인', count: safety.crime_detail.murder ?? 0 },
              ].map(crime => {
                const maxCount = Math.max(
                  safety.crime_detail!.violence ?? 0, safety.crime_detail!.theft ?? 0,
                  safety.crime_detail!.sexual_assault ?? 0, 1
                );
                const pct = (crime.count / maxCount) * 100;
                const totalPct = safety.crime_detail!.total_crime
                  ? ((crime.count / safety.crime_detail!.total_crime) * 100).toFixed(1) : '0';
                return (
                  <div key={crime.key}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-600">{crime.label}</span>
                      <span className="text-xs font-bold text-gray-800">
                        {crime.count.toLocaleString()}건
                        <span className="text-gray-400 font-normal ml-1">({totalPct}%)</span>
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${Math.max(pct, 1)}%`, backgroundColor: '#7b8fa8' }} />
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 pt-3 border-t border-gray-100 grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-lg font-bold text-gray-800">{(safety.crime_detail.total_crime ?? 0).toLocaleString()}</div>
                <div className="text-[10px] text-gray-500">5대범죄 합계</div>
              </div>
              <div>
                <div className="text-lg font-bold text-gray-800">{(safety.crime_detail.effective_pop ?? 0).toLocaleString()}</div>
                <div className="text-[10px] text-gray-500">보정 인구</div>
              </div>
              <div>
                <div className="text-lg font-bold text-gray-800">{(safety.crime_detail.crime_rate ?? 0).toFixed(0)}</div>
                <div className="text-[10px] text-gray-500">10만명당 범죄율</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AreaScoreCard({ title, score, maxScore, color, desc }: {
  title: string; score: number; maxScore: number; color: string; desc: string;
}) {
  const pct = Math.min(score / maxScore, 1) * 100;
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-bold text-gray-800">{title}</span>
        <span className="text-sm font-bold" style={{ color }}>
          {score.toFixed(1)}<span className="text-[10px] text-gray-400 font-normal">/{maxScore}</span>
        </span>
      </div>
      <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden mb-1.5">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <div className="text-[10px] text-gray-400">{desc}</div>
    </div>
  );
}

/** 만원 단위 금액을 "12억0,000" 형식으로 변환 */
function fmtManwon(manwon: number): string {
  const eok = Math.floor(manwon / 10000);
  const remainder = manwon % 10000;
  if (eok > 0) {
    const remStr = String(remainder).padStart(4, '0');
    return `${eok}억${remStr.slice(0, 1)},${remStr.slice(1)}`;
  }
  return manwon.toLocaleString();
}

function fmtDist(d?: number | null): string {
  if (d == null) return '-';
  const m = Math.round(d);
  return m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`;
}
