import { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator, Dimensions,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  fetchApartmentDetail, fetchApartmentTrades,
  type ApartmentDetail, type TradeData,
} from '../../src/services/api';

const W = Dimensions.get('window').width;
const TABS = ['기본정보', '시설', '학군', '안전', '시세', '인구'] as const;

const NL: Record<string, string> = {
  cost: '가성비', pet: '반려동물', commute: '출퇴근', newlywed: '신혼육아',
  education: '학군', senior: '시니어', investment: '투자', nature: '자연친화', safety: '안전',
};
const FL: Record<string, string> = {
  subway: '지하철', bus: '버스', bus_stop: '버스', hospital: '병원', park: '공원',
  school: '학교', convenience_store: '편의점', pharmacy: '약국', mart: '마트',
  kindergarten: '유치원', library: '도서관', police: '경찰서', fire_station: '소방서',
  pet_facility: '반려동물', animal_hospital: '동물병원', cctv: 'CCTV',
};

export default function DetailScreen() {
  const { pnu } = useLocalSearchParams<{ pnu: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [detail, setDetail] = useState<ApartmentDetail | null>(null);
  const [trades, setTrades] = useState<TradeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<string>('기본정보');

  useEffect(() => {
    if (!pnu) return;
    setLoading(true);
    Promise.all([fetchApartmentDetail(pnu), fetchApartmentTrades(pnu)])
      .then(([d, t]) => { setDetail(d); setTrades(t); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [pnu]);

  if (loading) return <View style={[$.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color={P.blue} /></View>;
  if (!detail) return (
    <View style={[$.center, { paddingTop: insets.top }]}>
      <Text style={$.errT}>불러올 수 없습니다</Text>
      <TouchableOpacity onPress={() => router.back()} style={$.errBtn}><Text style={$.errBtnT}>돌아가기</Text></TouchableOpacity>
    </View>
  );

  const { basic, scores, facility_summary, school, safety, population } = detail;
  const yr = basic.use_apr_day?.slice(0, 4) || '-';
  const age = yr !== '-' ? new Date().getFullYear() - parseInt(yr) : null;

  return (
    <View style={[$.root, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={$.hdr}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={16}>
          <Text style={$.hdrBack}>‹</Text>
        </TouchableOpacity>
        <View style={$.hdrBody}>
          <Text style={$.hdrName} numberOfLines={1}>{basic.bld_nm}</Text>
          <Text style={$.hdrAddr} numberOfLines={1}>{basic.plat_plc}</Text>
        </View>
      </View>

      {/* KPI strip */}
      <View style={$.kpiStrip}>
        <Kpi val={String(basic.total_hhld_cnt)} unit="세대" />
        <KpiDiv />
        <Kpi val={`${basic.dong_count}`} unit="동" />
        <KpiDiv />
        <Kpi val={`${basic.max_floor}F`} unit="최고층" />
        <KpiDiv />
        <Kpi val={age ? `${age}년` : yr} unit="건축" />
      </View>

      {/* Tabs */}
      <View style={$.tabRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={$.tabScr}>
          {TABS.map(t => (
            <TouchableOpacity key={t} onPress={() => setTab(t)} style={[$.tab, tab === t && $.tabOn]}>
              <Text style={[$.tabT, tab === t && $.tabTOn]}>{t}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Content */}
      <ScrollView style={$.body} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 48 }}>
        {tab === '기본정보' && <OverviewTab scores={scores} />}
        {tab === '시설' && <FacilityTab data={facility_summary} nearby={detail.nearby_facilities} />}
        {tab === '학군' && <SchoolTab data={school} />}
        {tab === '안전' && <SafetyTab data={safety} />}
        {tab === '시세' && <PriceTab data={trades} />}
        {tab === '인구' && <PopTab data={population} />}
      </ScrollView>
    </View>
  );
}

/* ── Helpers ── */
function Kpi({ val, unit }: { val: string; unit: string }) {
  return <View style={$.kpiItem}><Text style={$.kpiVal}>{val}</Text><Text style={$.kpiUnit}>{unit}</Text></View>;
}
function KpiDiv() { return <View style={$.kpiDiv} />; }
function SH({ title }: { title: string }) {
  return <View style={$.shRow}><View style={$.shDot} /><Text style={$.shT}>{title}</Text></View>;
}
function EmptyV() { return <View style={$.emptyV}><Text style={$.emptyT}>정보가 없습니다</Text></View>; }
function fp(v: number) { return v >= 10000 ? `${(v / 10000).toFixed(1)}억` : `${v.toLocaleString()}만`; }
function p2(n: number) { return String(n).padStart(2, '0'); }

/* ── Overview ── */
function OverviewTab({ scores }: { scores: Record<string, number> }) {
  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const best = sorted[0];
  return (
    <View style={$.sec}>
      {best && (
        <View style={$.heroCard}>
          <Text style={$.heroLbl}>최고 적합도</Text>
          <View style={$.heroRow}>
            <Text style={$.heroScore}>{best[1].toFixed(0)}</Text>
            <View style={$.heroRight}>
              <Text style={$.heroName}>{NL[best[0]] || best[0]}</Text>
              <Text style={$.heroSub}>100점 만점</Text>
            </View>
          </View>
        </View>
      )}
      <SH title="라이프스타일 점수" />
      {sorted.map(([k, v]) => {
        const pct = Math.min(v, 100);
        const c = v >= 70 ? P.green : v >= 40 ? P.blue : v >= 20 ? P.amber : P.rose;
        return (
          <View key={k} style={$.sRow}>
            <Text style={$.sLbl}>{NL[k] || k}</Text>
            <View style={$.sBarOut}><View style={[$.sBarIn, { width: `${pct}%`, backgroundColor: c }]} /></View>
            <Text style={[$.sVal, { color: c }]}>{v.toFixed(0)}</Text>
          </View>
        );
      })}
    </View>
  );
}

/* ── Facility ── */
function FacilityTab({ data, nearby }: { data: ApartmentDetail['facility_summary']; nearby: ApartmentDetail['nearby_facilities'] }) {
  const entries = Object.entries(data).sort((a, b) => a[1].nearest_distance_m - b[1].nearest_distance_m);

  // nearby_facilities에서 subtype 기준으로 가장 가까운 시설명 찾기
  const getNearestName = (subtype: string): string | null => {
    for (const items of Object.values(nearby)) {
      for (const item of items) {
        if (item.subtype === subtype) return item.name;
      }
    }
    return null;
  };

  return (
    <View style={$.sec}>
      <SH title="가까운 순" />
      {entries.map(([k, v]) => {
        const d = v.nearest_distance_m;
        const ds = d < 1000 ? `${Math.round(d)}m` : `${(d / 1000).toFixed(1)}km`;
        const near = d < 500;
        const nearestName = getNearestName(k);
        return (
          <View key={k} style={$.fCard}>
            <View style={$.fCardTop}>
              <View style={$.fLeft}>
                <View style={[$.fDot, near && { backgroundColor: P.blue }]} />
                <Text style={$.fName}>{FL[k] || k}</Text>
              </View>
              <Text style={[$.fDist, near && { color: P.blue, fontWeight: '600' }]} numberOfLines={1}>
                {nearestName ? `${nearestName} · ` : ''}{near ? '도보권 ' : ''}{ds}
              </Text>
            </View>
            <View style={$.fCounts}>
              <View style={$.fCountItem}>
                <Text style={$.fCountVal}>{v.count_1km}</Text>
                <Text style={$.fCountLabel}>1km</Text>
              </View>
              <View style={$.fCountDivider} />
              <View style={$.fCountItem}>
                <Text style={$.fCountVal}>{v.count_3km}</Text>
                <Text style={$.fCountLabel}>3km</Text>
              </View>
              <View style={$.fCountDivider} />
              <View style={$.fCountItem}>
                <Text style={$.fCountVal}>{v.count_5km}</Text>
                <Text style={$.fCountLabel}>5km</Text>
              </View>
            </View>
          </View>
        );
      })}
      <Text style={$.fLeg}>반경 내 시설 수</Text>
    </View>
  );
}

/* ── School ── */
function SchoolTab({ data }: { data: ApartmentDetail['school'] }) {
  if (!data) return <EmptyV />;
  const items: { lv: string; name: string; sub?: string }[] = [];
  if (data.elementary_school_name) items.push({ lv: '초등', name: data.elementary_school_full_name || data.elementary_school_name });
  if (data.middle_school_zone) items.push({ lv: '중학', name: data.middle_school_zone });
  if (data.high_school_zone) items.push({ lv: '고교', name: data.high_school_zone, sub: data.high_school_zone_type });
  return (
    <View style={$.sec}>
      {items.map((it, i) => (
        <View key={i} style={$.schRow}>
          <View style={$.schBadge}><Text style={$.schBadgeT}>{it.lv}</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={$.schName}>{it.name}</Text>
            {it.sub && <Text style={$.schSub}>{it.sub}</Text>}
          </View>
        </View>
      ))}
      {data.edu_office_name && <Text style={$.schEdu}>교육청 — {data.edu_office_name}</Text>}
    </View>
  );
}

/* ── Safety ── */
function SafetyTab({ data }: { data: ApartmentDetail['safety'] }) {
  if (!data) return <EmptyV />;
  return (
    <View style={$.sec}>
      <View style={$.sfGauges}>
        <SfG label="CCTV" score={data.safety_score} />
        <SfG label="범죄" score={data.crime_safety_score} />
        <SfG label="종합" score={data.nudge_safety_score} />
      </View>
      <SH title="CCTV" />
      <View style={$.sfGrid}>
        <SfS label="최근접" value={`${Math.round(data.cctv_nearest_m)}m`} />
        <SfS label="500m" value={`${data.cctv_count_500m}대`} />
        <SfS label="1km" value={`${data.cctv_count_1km}대`} />
      </View>
      <SH title="긴급 서비스" />
      <View style={$.sfGrid}>
        <SfS label="경찰서" value={`${(data.police_nearest_m / 1000).toFixed(1)}km`} sub={`${data.police_count_3km}곳 / 3km`} />
        <SfS label="소방서" value={`${(data.fire_nearest_m / 1000).toFixed(1)}km`} sub={`${data.fire_count_3km}곳 / 3km`} />
      </View>
    </View>
  );
}
function SfG({ label, score }: { label: string; score: number }) {
  const c = score >= 70 ? P.green : score >= 40 ? P.amber : P.rose;
  const g = score >= 80 ? '매우 안전' : score >= 60 ? '안전' : score >= 40 ? '보통' : '취약';
  return (
    <View style={$.sfG}>
      <Text style={[$.sfGN, { color: c }]}>{score.toFixed(0)}</Text>
      <View style={$.sfGTrack}><View style={[$.sfGFill, { width: `${Math.min(score, 100)}%`, backgroundColor: c }]} /></View>
      <Text style={[$.sfGGr, { color: c }]}>{g}</Text>
      <Text style={$.sfGL}>{label}</Text>
    </View>
  );
}
function SfS({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <View style={$.sfS}><Text style={$.sfSL}>{label}</Text><Text style={$.sfSV}>{value}</Text>{sub && <Text style={$.sfSSub}>{sub}</Text>}</View>;
}

/* ── Price ── */
function PriceTab({ data }: { data: TradeData | null }) {
  if (!data || data.trades.length === 0) return <EmptyV />;
  const recent = data.trades.slice(0, 12);
  const latest = recent[0];
  const avg = Math.round(recent.reduce((s, t) => s + t.deal_amount, 0) / recent.length);
  const maxP = Math.max(...recent.map(t => t.deal_amount));
  const minP = Math.min(...recent.map(t => t.deal_amount));
  const diff = latest.deal_amount - avg;

  return (
    <View style={$.sec}>
      {/* Hero */}
      <View style={$.prHero}>
        <Text style={$.prHeroLbl}>최근 거래가</Text>
        <Text style={$.prHeroVal}>{fp(latest.deal_amount)}</Text>
        <Text style={$.prHeroMeta}>{latest.deal_year}.{p2(latest.deal_month)} · {latest.exclu_use_ar.toFixed(0)}㎡ · {latest.floor}층</Text>
        <View style={$.prMinis}>
          <View style={$.prMini}><Text style={$.prMiniL}>평균</Text><Text style={$.prMiniV}>{fp(avg)}</Text></View>
          <View style={$.prMini}><Text style={$.prMiniL}>최고</Text><Text style={$.prMiniV}>{fp(maxP)}</Text></View>
          <View style={$.prMini}><Text style={$.prMiniL}>최저</Text><Text style={$.prMiniV}>{fp(minP)}</Text></View>
        </View>
        <View style={[$.prDiff, { backgroundColor: diff >= 0 ? '#DCFCE7' : '#FEE2E2' }]}>
          <Text style={[$.prDiffT, { color: diff >= 0 ? P.green : P.rose }]}>{diff >= 0 ? '+' : ''}{fp(Math.abs(diff))} vs 평균</Text>
        </View>
      </View>

      {/* Chart */}
      <SH title="매매 추이" />
      <View style={$.prChart}>
        {recent.slice().reverse().map((t, i) => {
          const h = maxP > 0 ? Math.max((t.deal_amount / maxP) * 90, 4) : 4;
          const isLast = i === recent.length - 1;
          return (
            <View key={i} style={$.prBar}>
              <Text style={$.prBarP}>{fp(t.deal_amount)}</Text>
              <View style={[$.prBarB, { height: h, backgroundColor: isLast ? P.blue : '#BFDBFE' }]} />
              <Text style={$.prBarD}>{p2(t.deal_month)}/{String(t.deal_year).slice(2)}</Text>
            </View>
          );
        })}
      </View>

      {/* Table */}
      <SH title="거래 내역" />
      <View style={$.tbl}>
        <View style={$.tblH}>{['일자', '층', '면적', '가격'].map(h => <Text key={h} style={$.tblHC}>{h}</Text>)}</View>
        {data.trades.slice(0, 15).map((t, i) => (
          <View key={i} style={[$.tblR, i % 2 === 0 && $.tblRA]}>
            <Text style={$.tblC}>{t.deal_year}.{p2(t.deal_month)}</Text>
            <Text style={$.tblC}>{t.floor}층</Text>
            <Text style={$.tblC}>{t.exclu_use_ar.toFixed(0)}㎡</Text>
            <Text style={[$.tblC, $.tblCB]}>{fp(t.deal_amount)}</Text>
          </View>
        ))}
      </View>
      {data.rents.length > 0 && (
        <>
          <SH title="전월세" />
          <View style={$.tbl}>
            <View style={$.tblH}>{['일자', '면적', '보증금', '월세'].map(h => <Text key={h} style={$.tblHC}>{h}</Text>)}</View>
            {data.rents.slice(0, 10).map((r, i) => (
              <View key={i} style={[$.tblR, i % 2 === 0 && $.tblRA]}>
                <Text style={$.tblC}>{r.deal_year}.{p2(r.deal_month)}</Text>
                <Text style={$.tblC}>{r.exclu_use_ar.toFixed(0)}㎡</Text>
                <Text style={$.tblC}>{fp(r.deposit)}</Text>
                <Text style={$.tblC}>{r.monthly_rent > 0 ? `${r.monthly_rent}만` : '전세'}</Text>
              </View>
            ))}
          </View>
        </>
      )}
    </View>
  );
}

/* ── Population ── */
function PopTab({ data }: { data: ApartmentDetail['population'] }) {
  if (!data) return <EmptyV />;
  const mR = ((data.male_pop / data.total_pop) * 100).toFixed(1);
  const fR = ((data.female_pop / data.total_pop) * 100).toFixed(1);
  const maxRatio = Math.max(...data.age_groups.map(g => g.ratio));
  return (
    <View style={$.sec}>
      <View style={$.popHdr}><Text style={$.popName}>{data.sigungu_name}</Text><Text style={$.popTotal}>{(data.total_pop / 10000).toFixed(1)}만명</Text></View>
      <View style={$.popGender}>
        <View style={[$.popGBar, { flex: parseFloat(mR), backgroundColor: P.blue + '20' }]}><Text style={$.popGT}>남 {mR}%</Text></View>
        <View style={[$.popGBar, { flex: parseFloat(fR), backgroundColor: P.rose + '20' }]}><Text style={$.popGT}>여 {fR}%</Text></View>
      </View>
      <SH title="연령 분포" />
      {data.age_groups.map(g => (
        <View key={g.age_group} style={$.sRow}>
          <Text style={[$.sLbl, { width: 56 }]}>{g.age_group}</Text>
          <View style={$.sBarOut}><View style={[$.sBarIn, { width: `${maxRatio > 0 ? (g.ratio / maxRatio) * 100 : 0}%`, backgroundColor: P.blue + '50' }]} /></View>
          <Text style={[$.sVal, { color: P.text }]}>{g.ratio.toFixed(1)}%</Text>
        </View>
      ))}
    </View>
  );
}

/* ── Palette (앱 기본 톤과 일치) ── */
const P = {
  bg: '#FFFFFF', card: '#F9FAFB', border: '#E5E7EB',
  blue: '#2563EB', blueLight: '#EFF6FF', blueDark: '#1E40AF',
  green: '#059669', amber: '#D97706', rose: '#DC2626',
  text: '#111827', text2: '#6B7280', text3: '#9CA3AF',
};

const $ = StyleSheet.create({
  root: { flex: 1, backgroundColor: P.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: P.bg },
  errT: { fontSize: 15, color: P.rose, fontWeight: '600' },
  errBtn: { marginTop: 14, paddingHorizontal: 22, paddingVertical: 10, backgroundColor: P.blue, borderRadius: 8 },
  errBtnT: { color: '#FFF', fontWeight: '600' },

  hdr: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: P.border },
  hdrBack: { fontSize: 28, color: P.text2, marginRight: 10, lineHeight: 30 },
  hdrBody: { flex: 1 },
  hdrName: { fontSize: 17, fontWeight: '700', color: P.text, letterSpacing: -0.3 },
  hdrAddr: { fontSize: 11, color: P.text3, marginTop: 2 },

  kpiStrip: { flexDirection: 'row', alignItems: 'center', backgroundColor: P.blueLight, paddingVertical: 14, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: P.border },
  kpiItem: { flex: 1, alignItems: 'center' },
  kpiVal: { fontSize: 17, fontWeight: '800', color: P.blueDark, letterSpacing: -0.5 },
  kpiUnit: { fontSize: 9, color: P.blue, marginTop: 2, fontWeight: '500' },
  kpiDiv: { width: 1, height: 22, backgroundColor: '#BFDBFE' },

  tabRow: { borderBottomWidth: 1, borderBottomColor: P.border },
  tabScr: { paddingHorizontal: 14, gap: 4 },
  tab: { paddingHorizontal: 13, paddingVertical: 11 },
  tabOn: { borderBottomWidth: 2, borderBottomColor: P.blue },
  tabT: { fontSize: 13, color: P.text3, fontWeight: '500' },
  tabTOn: { color: P.blue, fontWeight: '700' },

  body: { flex: 1 },
  sec: { paddingHorizontal: 16, paddingTop: 16 },

  shRow: { flexDirection: 'row', alignItems: 'center', marginTop: 18, marginBottom: 12, gap: 8 },
  shDot: { width: 3, height: 12, backgroundColor: P.blue, borderRadius: 1.5 },
  shT: { fontSize: 13, fontWeight: '700', color: P.text, letterSpacing: -0.2 },

  // Overview hero
  heroCard: { backgroundColor: P.blueLight, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: '#BFDBFE', marginBottom: 4 },
  heroLbl: { fontSize: 10, color: P.blue, fontWeight: '500', letterSpacing: 0.5 },
  heroRow: { flexDirection: 'row', alignItems: 'baseline', gap: 12, marginTop: 6 },
  heroScore: { fontSize: 44, fontWeight: '900', color: P.blueDark, letterSpacing: -2 },
  heroRight: { paddingBottom: 4 },
  heroName: { fontSize: 14, fontWeight: '700', color: P.blue },
  heroSub: { fontSize: 10, color: P.text3, marginTop: 2 },

  // Score rows
  sRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 8 },
  sLbl: { width: 52, fontSize: 12, fontWeight: '500', color: P.text2 },
  sBarOut: { flex: 1, height: 8, backgroundColor: P.card, borderRadius: 4, overflow: 'hidden', borderWidth: 1, borderColor: P.border },
  sBarIn: { height: '100%', borderRadius: 4 },
  sVal: { width: 30, fontSize: 13, fontWeight: '800', textAlign: 'right' },

  // Facility
  fCard: { backgroundColor: P.card, borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: P.border },
  fCardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  fLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  fDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: P.border },
  fName: { fontSize: 13, fontWeight: '600', color: P.text },
  fDist: { fontSize: 11, color: P.text3, flexShrink: 1, textAlign: 'right' },
  fCounts: { flexDirection: 'row', alignItems: 'center' },
  fCountItem: { flex: 1, alignItems: 'center' },
  fCountVal: { fontSize: 17, fontWeight: '800', color: P.text, letterSpacing: -0.5 },
  fCountLabel: { fontSize: 9, color: P.text3, marginTop: 2, fontWeight: '500' },
  fCountDivider: { width: 1, height: 24, backgroundColor: P.border },
  fLeg: { fontSize: 10, color: P.text3, marginTop: 4, textAlign: 'right' },

  // School
  schRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: P.border },
  schBadge: { backgroundColor: P.blue, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, marginTop: 1 },
  schBadgeT: { fontSize: 10, fontWeight: '700', color: '#FFF' },
  schName: { fontSize: 15, fontWeight: '600', color: P.text },
  schSub: { fontSize: 11, color: P.text3, marginTop: 2 },
  schEdu: { fontSize: 11, color: P.text3, marginTop: 16 },

  // Safety
  sfGauges: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  sfG: { flex: 1, backgroundColor: P.card, borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: P.border },
  sfGN: { fontSize: 26, fontWeight: '900', letterSpacing: -1 },
  sfGTrack: { width: '70%', height: 4, backgroundColor: P.border, borderRadius: 2, overflow: 'hidden', marginTop: 8 },
  sfGFill: { height: '100%', borderRadius: 2 },
  sfGGr: { fontSize: 10, fontWeight: '600', marginTop: 6 },
  sfGL: { fontSize: 9, color: P.text3, marginTop: 2 },
  sfGrid: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  sfS: { flex: 1, backgroundColor: P.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: P.border },
  sfSL: { fontSize: 10, color: P.text3 },
  sfSV: { fontSize: 18, fontWeight: '800', color: P.text, marginTop: 4, letterSpacing: -0.5 },
  sfSSub: { fontSize: 10, color: P.text3, marginTop: 3 },

  // Price
  prHero: { backgroundColor: P.blueLight, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: '#BFDBFE', marginBottom: 4 },
  prHeroLbl: { fontSize: 10, color: P.blue, fontWeight: '500', letterSpacing: 0.5 },
  prHeroVal: { fontSize: 28, fontWeight: '900', color: P.blueDark, marginTop: 4, letterSpacing: -1 },
  prHeroMeta: { fontSize: 10, color: P.text3, marginTop: 4 },
  prMinis: { flexDirection: 'row', gap: 12, marginTop: 12 },
  prMini: { flex: 1 },
  prMiniL: { fontSize: 10, color: P.text3 },
  prMiniV: { fontSize: 14, fontWeight: '700', color: P.blueDark, marginTop: 2 },
  prDiff: { alignSelf: 'flex-start', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4, marginTop: 10 },
  prDiffT: { fontSize: 11, fontWeight: '600' },
  prChart: { flexDirection: 'row', alignItems: 'flex-end', height: 140, backgroundColor: P.card, borderRadius: 12, paddingHorizontal: 6, paddingTop: 20, paddingBottom: 20, borderWidth: 1, borderColor: P.border, marginBottom: 4 },
  prBar: { flex: 1, alignItems: 'center', justifyContent: 'flex-end' },
  prBarP: { fontSize: 7, color: P.text3, marginBottom: 3 },
  prBarB: { width: '55%', borderRadius: 2, minHeight: 3 },
  prBarD: { fontSize: 7, color: P.text3, marginTop: 4, position: 'absolute', bottom: -14 },

  // Table
  tbl: { borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: P.border, marginBottom: 4 },
  tblH: { flexDirection: 'row', backgroundColor: P.card, paddingVertical: 8 },
  tblHC: { flex: 1, textAlign: 'center', fontSize: 10, fontWeight: '600', color: P.text2 },
  tblR: { flexDirection: 'row', paddingVertical: 9, borderTopWidth: 1, borderTopColor: P.border },
  tblRA: { backgroundColor: P.card },
  tblC: { flex: 1, textAlign: 'center', fontSize: 12, color: P.text2 },
  tblCB: { color: P.blue, fontWeight: '600' },

  // Population
  popHdr: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 },
  popName: { fontSize: 18, fontWeight: '800', color: P.text },
  popTotal: { fontSize: 14, fontWeight: '600', color: P.blue },
  popGender: { flexDirection: 'row', height: 28, borderRadius: 6, overflow: 'hidden', marginBottom: 4 },
  popGBar: { justifyContent: 'center', alignItems: 'center' },
  popGT: { fontSize: 10, fontWeight: '600', color: P.text2 },

  emptyV: { paddingVertical: 48, alignItems: 'center' },
  emptyT: { fontSize: 13, color: P.text3 },
});
