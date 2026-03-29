import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';
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
}

interface ApartmentDetail {
  basic: BasicInfo;
  scores: Record<string, number>;
  facility_summary: Record<string, { nearest_distance_m: number; count_1km: number; count_3km: number; count_5km: number }>;
  nearby_facilities: Record<string, { name: string; distance_m: number; lat: number; lng: number }[]>;
  school: SchoolInfo | null;
  safety?: SafetyData | null;
  population?: PopulationData;
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

const nudgeLabels: Record<string, string> = {
  cost: '가성비', pet: '반려동물', commute: '출퇴근',
  newlywed: '신혼육아', education: '학군', senior: '시니어',
  investment: '투자', nature: '자연친화', safety: '안전',
};

const facilityLabels: Record<string, string> = {
  // 소분류 (facility_subtype)
  subway: '지하철역', bus: '버스정류장', mart: '대형마트',
  school: '학교', kindergarten: '유치원', police: '경찰서',
  fire_station: '소방서', library: '도서관', park: '공원',
  convenience_store: '편의점', pharmacy: '약국',
  hospital: '병원', animal_hospital: '동물병원',
  pet_facility: '반려동물시설', cctv: 'CCTV',
  // 대분류 (facility_type)
  transport: '교통', commerce: '상업', education: '교육',
  safety: '안전', culture: '문화', living: '생활편의',
  medical: '의료', pet: '반려동물',
};

const TABS = ['기본정보', '가격분석', '주변시설', '학군', '안전', '인구'] as const;
type TabName = (typeof TABS)[number];

const BLUE = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd'];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

interface DetailModalProps {
  pnu: string;
  onClose: () => void;
}

export default function DetailModal({ pnu, onClose }: DetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabName>('기본정보');
  const [detail, setDetail] = useState<ApartmentDetail | null>(null);
  const [tradesData, setTradesData] = useState<TradesResponse>({ trades: [], rents: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading must reset when pnu changes
    setLoading(true);

    Promise.all([
      axios.get<ApartmentDetail>(`${API_BASE}/api/apartment/${pnu}`),
      axios.get<TradesResponse>(`${API_BASE}/api/apartment/${pnu}/trades`),
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
      <div className="relative w-full max-w-4xl h-[85vh] mx-4 bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-3 border-b border-gray-100">
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
        <div className="flex border-b border-gray-200 px-6">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors relative
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
        <div className="flex-1 overflow-y-auto p-6">
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
              {activeTab === '기본정보' && <TabBasicInfo detail={detail} />}
              {activeTab === '가격분석' && <TabPriceAnalysis trades={tradesData.trades} rents={tradesData.rents} />}
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

function TabBasicInfo({ detail }: { detail: ApartmentDetail | null }) {
  if (!detail) return <EmptyState text="기본 정보를 불러올 수 없습니다." />;

  const b = detail.basic;
  const infoItems = [
    { label: '세대수', value: b.total_hhld_cnt != null ? `${b.total_hhld_cnt}세대` : '-' },
    { label: '동수', value: b.dong_count != null ? `${b.dong_count}동` : '-' },
    { label: '최고층', value: b.max_floor != null ? `${b.max_floor}층` : '-' },
    { label: '사용승인일', value: b.use_apr_day ?? '-' },
  ];

  const radarData = detail.scores
    ? Object.entries(detail.scores).map(([key, value]) => ({
        subject: nudgeLabels[key] ?? key,
        score: value,
        fullMark: 100,
      }))
    : [];

  return (
    <div className="space-y-6">
      {/* Info cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {infoItems.map((item) => (
          <div key={item.label} className="bg-gray-50 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-500">{item.label}</p>
            <p className="text-base font-semibold text-gray-800 mt-1">{item.value}</p>
          </div>
        ))}
      </div>

      {/* Radar chart */}
      {radarData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">라이프 점수</h3>
          <div className="bg-gray-50 rounded-lg p-4">
            <ResponsiveContainer width="100%" height={320}>
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                <PolarGrid stroke="#e5e7eb" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: '#6b7280' }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Radar name="점수" dataKey="score" stroke={BLUE[0]} fill={BLUE[0]} fillOpacity={0.25} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
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
      {/* Price trend by area */}
      {trendData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">월별 매매가 추이 (면적별)</h3>
          <div className="bg-gray-50 rounded-lg p-4">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} angle={-45} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: '만원', position: 'insideTopLeft', offset: -5, fontSize: 11 }} />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- recharts Formatter type is complex
                  formatter={(val: any, name: any) => {
                    const at = areaTypes.find((t: { key: string }) => t.key === name);
                    return [`${Number(val).toLocaleString()}만원`, at?.label ?? name];
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
          </div>
        </div>
      )}

      {/* Price by area */}
      {areaData.some((d) => d.count > 0) && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">면적별 평균가</h3>
          <div className="bg-gray-50 rounded-lg p-4">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={areaData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="range" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: '억원', position: 'insideTopLeft', offset: -5, fontSize: 11 }} />
                <Tooltip formatter={(val) => [`${val}억원`, '평균가']} />
                <Bar dataKey="avg" fill={BLUE[1]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Jeonse ratio by area */}
      {jeonseData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">전세가율 추이 (면적별)</h3>
          <div className="bg-gray-50 rounded-lg p-4">
            <ResponsiveContainer width="100%" height={300}>
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
          </div>
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
                      {t.deal_amount != null ? t.deal_amount.toLocaleString() : '-'}
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
              최근접 {Math.round(data.nearest_distance_m)}m
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
          <div className="bg-gray-50 rounded-lg p-4">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barData} layout="vertical" margin={{ left: 80 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="type" tick={{ fontSize: 11 }} width={75} />
                <Tooltip formatter={(val) => [`${val}개`, '시설 수']} />
                <Bar dataKey="count" fill={BLUE[1]} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
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
/*  Tab 4 – 학군                                                       */
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
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {items.map((item) => (
        <div key={item.label} className="bg-gray-50 rounded-lg p-4">
          <p className="text-xs text-gray-500 mb-1">{item.label}</p>
          <p className="text-base font-semibold text-gray-800">{item.value}</p>
          {item.sub && <p className="text-sm text-gray-500 mt-0.5">{item.sub}</p>}
        </div>
      ))}
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

interface SafetyData {
  safety_score?: number;
  crime_safety_score?: number;
  crime_detail?: CrimeDetail | null;
  cctv_nearest_m?: number;
  cctv_count_500m?: number;
  cctv_count_1km?: number;
  police_nearest_m?: number;
  police_count_3km?: number;
  fire_nearest_m?: number;
  fire_count_3km?: number;
  nudge_safety_score?: number;
}

function TabSafety({ safety }: { safety?: SafetyData | null }) {
  if (!safety) return <EmptyState text="안전 정보가 없습니다." />;

  const safetyScore = safety.safety_score ?? 0;
  const crimeScore = safety.crime_safety_score ?? 0;
  const totalScore = safety.nudge_safety_score ?? 0;

  return (
    <div className="space-y-6">
      {/* 종합 안전 점수 */}
      <div className="bg-gradient-to-r from-blue-50 to-emerald-50 rounded-xl p-5">
        <h3 className="text-sm font-bold text-gray-700 mb-4">종합 안전 점수</h3>
        <div className="flex items-center justify-center gap-8">
          <ScoreRing score={totalScore} label="종합" size={100} color="#2563eb" />
          <ScoreRing score={safetyScore} label="CCTV 안전" size={80} color="#10b981" />
          <ScoreRing score={crimeScore} label="범죄 안전" size={80} color="#8b5cf6" />
        </div>
      </div>

      {/* 안전 시설 카드 */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3">안전 시설 현황</h3>
        <div className="grid grid-cols-3 gap-3">
          <FacilityCard
            icon="📹"
            title="CCTV"
            items={[
              { label: '최근접', value: fmtDist(safety.cctv_nearest_m) },
              { label: '500m 이내', value: `${safety.cctv_count_500m ?? 0}대`, highlight: (safety.cctv_count_500m ?? 0) >= 20 },
              { label: '1km 이내', value: `${safety.cctv_count_1km ?? 0}대` },
            ]}
            score={safetyScore}
          />
          <FacilityCard
            icon="👮"
            title="경찰서"
            items={[
              { label: '최근접', value: fmtDist(safety.police_nearest_m) },
              { label: '3km 이내', value: `${safety.police_count_3km ?? 0}곳` },
            ]}
            score={safety.police_nearest_m != null ? Math.max(0, 100 - (safety.police_nearest_m / 30)) : 0}
          />
          <FacilityCard
            icon="🚒"
            title="소방서"
            items={[
              { label: '최근접', value: fmtDist(safety.fire_nearest_m) },
              { label: '3km 이내', value: `${safety.fire_count_3km ?? 0}곳` },
            ]}
            score={safety.fire_nearest_m != null ? Math.max(0, 100 - (safety.fire_nearest_m / 50)) : 0}
          />
        </div>
      </div>

      {/* 범죄 안전 지수 */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3">지역 범죄 안전 지수</h3>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-4 mb-3">
            <span className="text-2xl">🛡</span>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-600">범죄 안전도</span>
                <span className={`text-lg font-bold ${crimeScore >= 70 ? 'text-emerald-600' : crimeScore >= 40 ? 'text-blue-600' : 'text-amber-600'}`}>
                  {crimeScore.toFixed(1)}점
                </span>
              </div>
              <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${Math.min(crimeScore, 100)}%`,
                    background: crimeScore >= 70 ? 'linear-gradient(90deg, #10b981, #34d399)' :
                      crimeScore >= 40 ? 'linear-gradient(90deg, #3b82f6, #60a5fa)' :
                      'linear-gradient(90deg, #f59e0b, #fbbf24)',
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
            * 2024년 경찰청 범죄통계 기반
            {safety.crime_detail?.float_pop_ratio && safety.crime_detail.float_pop_ratio > 1.0
              ? `, 유동인구 보정 적용 (×${safety.crime_detail.float_pop_ratio.toFixed(1)})`
              : ', 인구 10만명당 범죄율 산정'}
          </p>
        </div>
      </div>

      {/* 범죄 유형 분석 */}
      {safety.crime_detail && (
        <div>
          <h3 className="text-sm font-bold text-gray-700 mb-3">범죄 유형 분석 (2024)</h3>
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            {/* 범죄 유형별 바 차트 */}
            <div className="space-y-3">
              {[
                { key: 'violence', label: '폭력', icon: '👊', color: '#ef4444', count: safety.crime_detail.violence ?? 0 },
                { key: 'theft', label: '절도', icon: '🔓', color: '#f59e0b', count: safety.crime_detail.theft ?? 0 },
                { key: 'sexual_assault', label: '강간·강제추행', icon: '⚠', color: '#8b5cf6', count: safety.crime_detail.sexual_assault ?? 0 },
                { key: 'robbery', label: '강도', icon: '🔪', color: '#dc2626', count: safety.crime_detail.robbery ?? 0 },
                { key: 'murder', label: '살인', icon: '💀', color: '#1e293b', count: safety.crime_detail.murder ?? 0 },
              ].map(crime => {
                const maxCount = Math.max(
                  safety.crime_detail!.violence ?? 0,
                  safety.crime_detail!.theft ?? 0,
                  safety.crime_detail!.sexual_assault ?? 0,
                  1
                );
                const pct = (crime.count / maxCount) * 100;
                const totalPct = safety.crime_detail!.total_crime
                  ? ((crime.count / safety.crime_detail!.total_crime) * 100).toFixed(1)
                  : '0';
                return (
                  <div key={crime.key}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-600">{crime.icon} {crime.label}</span>
                      <span className="text-xs font-bold text-gray-800">
                        {crime.count.toLocaleString()}건
                        <span className="text-gray-400 font-normal ml-1">({totalPct}%)</span>
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${Math.max(pct, 1)}%`, backgroundColor: crime.color }} />
                    </div>
                  </div>
                );
              })}
            </div>
            {/* 요약 정보 */}
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

      {/* CCTV 밀도 시각화 */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3">CCTV 밀도</h3>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="grid grid-cols-2 gap-4">
            <DensityMeter
              label="500m 이내"
              count={safety.cctv_count_500m ?? 0}
              max={60}
              icon="📹"
              description={
                (safety.cctv_count_500m ?? 0) >= 30 ? '매우 높음' :
                (safety.cctv_count_500m ?? 0) >= 15 ? '양호' :
                (safety.cctv_count_500m ?? 0) >= 5 ? '보통' : '부족'
              }
            />
            <DensityMeter
              label="1km 이내"
              count={safety.cctv_count_1km ?? 0}
              max={200}
              icon="📹"
              description={
                (safety.cctv_count_1km ?? 0) >= 100 ? '매우 높음' :
                (safety.cctv_count_1km ?? 0) >= 50 ? '양호' :
                (safety.cctv_count_1km ?? 0) >= 20 ? '보통' : '부족'
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function ScoreRing({ score, label, size, color }: { score: number; label: string; size: number; color: string }) {
  const r = size * 0.38;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(score, 100) / 100;
  const strokeW = size * 0.07;
  const fontSize = size * 0.22;
  const labelSize = size * 0.12;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#e5e7eb" strokeWidth={strokeW} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={strokeW}
          strokeDasharray={`${pct * circ} ${circ}`}
          strokeLinecap="round" transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: 'stroke-dasharray 0.8s ease' }} />
        <text x={size/2} y={size/2 + fontSize * 0.35} textAnchor="middle"
          fontSize={fontSize} fontWeight="bold" fill={color}>
          {score.toFixed(0)}
        </text>
      </svg>
      <span className="text-xs text-gray-500" style={{ fontSize: labelSize }}>{label}</span>
    </div>
  );
}

function FacilityCard({ icon, title, items, score }: {
  icon: string; title: string;
  items: { label: string; value: string; highlight?: boolean }[];
  score: number;
}) {
  const bg = score >= 70 ? 'border-emerald-200 bg-emerald-50' :
    score >= 40 ? 'border-blue-200 bg-blue-50' : 'border-gray-200 bg-white';
  return (
    <div className={`border rounded-xl p-3.5 ${bg}`}>
      <div className="flex items-center gap-2 mb-2.5">
        <span className="text-lg">{icon}</span>
        <span className="text-sm font-bold text-gray-800">{title}</span>
      </div>
      <div className="space-y-1.5">
        {items.map((item, i) => (
          <div key={i} className="flex justify-between text-xs">
            <span className="text-gray-500">{item.label}</span>
            <span className={`font-medium ${item.highlight ? 'text-emerald-600' : 'text-gray-800'}`}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DensityMeter({ label, count, max, icon, description }: {
  label: string; count: number; max: number; icon: string; description: string;
}) {
  const pct = Math.min(count / max, 1) * 100;
  const color = pct >= 70 ? '#10b981' : pct >= 40 ? '#3b82f6' : pct >= 15 ? '#f59e0b' : '#ef4444';
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-600">{icon} {label}</span>
        <span className="text-xs font-bold" style={{ color }}>{count}대 · {description}</span>
      </div>
      <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function fmtDist(d?: number | null): string {
  if (d == null) return '-';
  const m = Math.round(d);
  return m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`;
}
