import { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { fetchApartmentDetail, type ApartmentDetail } from '../src/services/api';

const NL: Record<string, string> = {
  cost: '가성비', pet: '반려동물', commute: '출퇴근', newlywed: '신혼육아',
  education: '학군', senior: '시니어', investment: '투자', nature: '자연친화', safety: '안전',
};
const FK = ['subway', 'bus', 'hospital', 'park', 'convenience_store', 'school'] as const;
const FL: Record<string, string> = {
  subway: '지하철', bus: '버스', hospital: '병원', park: '공원',
  convenience_store: '편의점', school: '학교',
};

export default function CompareScreen() {
  const { pnu1, pnu2 } = useLocalSearchParams<{ pnu1: string; pnu2: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [a, setA] = useState<ApartmentDetail | null>(null);
  const [b, setB] = useState<ApartmentDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!pnu1 || !pnu2) return;
    setLoading(true);
    Promise.all([fetchApartmentDetail(pnu1), fetchApartmentDetail(pnu2)])
      .then(([d1, d2]) => { setA(d1); setB(d2); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [pnu1, pnu2]);

  if (loading) return <View style={[$.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color={P.blue} /></View>;
  if (!a || !b) return (
    <View style={[$.center, { paddingTop: insets.top }]}>
      <Text style={$.errT}>비교 데이터를 불러올 수 없습니다</Text>
      <TouchableOpacity onPress={() => router.back()} style={$.errBtn}><Text style={$.errBtnT}>돌아가기</Text></TouchableOpacity>
    </View>
  );

  const scoreKeys = Object.keys(a.scores).filter(k => k in b.scores);
  let wA = 0, wB = 0;
  scoreKeys.forEach(k => { if (a.scores[k] > b.scores[k]) wA++; else if (b.scores[k] > a.scores[k]) wB++; });

  return (
    <View style={[$.root, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={$.hdr}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={16}>
          <Text style={$.hdrBack}>‹</Text>
        </TouchableOpacity>
        <Text style={$.hdrTitle}>아파트 비교</Text>
      </View>

      {/* Score summary */}
      <View style={$.winStrip}>
        <View style={[$.winSide, { alignItems: 'flex-end' }]}>
          <Text style={$.winName} numberOfLines={1}>{a.basic.bld_nm}</Text>
          <Text style={[$.winCount, { color: wA >= wB ? P.blue : P.text3 }]}>{wA}승</Text>
        </View>
        <View style={$.winVs}><Text style={$.winVsT}>VS</Text></View>
        <View style={$.winSide}>
          <Text style={$.winName} numberOfLines={1}>{b.basic.bld_nm}</Text>
          <Text style={[$.winCount, { color: wB >= wA ? P.blue : P.text3 }]}>{wB}승</Text>
        </View>
      </View>

      <ScrollView style={$.body} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 48 }}>
        {/* Apartment cards */}
        <View style={$.sec}>
          <View style={$.cardRow}>
            <AptCard d={a.basic} tag="A" color={P.blue} />
            <AptCard d={b.basic} tag="B" color="#7C3AED" />
          </View>
        </View>

        {/* Life scores */}
        <View style={$.sec}>
          <SH title="라이프스타일 점수" />
          {scoreKeys.map(k => {
            const va = a.scores[k] || 0, vb = b.scores[k] || 0;
            const mx = Math.max(va, vb, 1);
            return (
              <View key={k} style={$.vsRow}>
                <Text style={[$.vsVal, va >= vb && $.vsWin]}>{va.toFixed(0)}</Text>
                <View style={$.vsBars}>
                  <View style={$.vsBarL}>
                    <View style={[$.vsBarLF, { width: `${(va / mx) * 100}%` }]} />
                  </View>
                  <Text style={$.vsLabel}>{NL[k] || k}</Text>
                  <View style={$.vsBarR}>
                    <View style={[$.vsBarRF, { width: `${(vb / mx) * 100}%` }]} />
                  </View>
                </View>
                <Text style={[$.vsVal, vb >= va && $.vsWin]}>{vb.toFixed(0)}</Text>
              </View>
            );
          })}
        </View>

        {/* Facilities */}
        <View style={$.sec}>
          <SH title="주변시설 거리" />
          <View style={$.tbl}>
            <View style={$.tblH}>
              <Text style={[$.tblHC, { flex: 1.2 }]}>시설</Text>
              <Text style={[$.tblHC, { color: P.blue }]}>A</Text>
              <Text style={[$.tblHC, { color: '#7C3AED' }]}>B</Text>
            </View>
            {FK.map(k => {
              const da = a.facility_summary[k]?.nearest_distance_m;
              const db = b.facility_summary[k]?.nearest_distance_m;
              const aw = da != null && db != null && da <= db;
              const bw = da != null && db != null && db <= da;
              return (
                <View key={k} style={$.tblR}>
                  <Text style={[$.tblC, { flex: 1.2, fontWeight: '500', color: P.text }]}>{FL[k]}</Text>
                  <Text style={[$.tblC, aw && $.tblCW]}>{fd(da)}</Text>
                  <Text style={[$.tblC, bw && $.tblCW]}>{fd(db)}</Text>
                </View>
              );
            })}
          </View>
        </View>

        {/* School */}
        <View style={$.sec}>
          <SH title="학군" />
          <View style={$.cardRow}>
            <SchoolCard d={a.school} color={P.blue} />
            <SchoolCard d={b.school} color="#7C3AED" />
          </View>
        </View>

        {/* Safety */}
        <View style={$.sec}>
          <SH title="안전" />
          <View style={$.cardRow}>
            <SafetyCard d={a.safety} color={P.blue} />
            <SafetyCard d={b.safety} color="#7C3AED" />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

/* ── Sub components ── */
function AptCard({ d, tag, color }: { d: ApartmentDetail['basic']; tag: string; color: string }) {
  const yr = d.use_apr_day?.slice(0, 4) || '-';
  return (
    <View style={[$.aptCard, { borderTopColor: color }]}>
      <View style={[$.aptTag, { backgroundColor: color }]}><Text style={$.aptTagT}>{tag}</Text></View>
      <Text style={$.aptName} numberOfLines={1}>{d.bld_nm}</Text>
      <Text style={$.aptMeta}>{d.total_hhld_cnt}세대 · {d.max_floor}F · {yr}</Text>
    </View>
  );
}

function SchoolCard({ d, color }: { d: ApartmentDetail['school']; color: string }) {
  if (!d) return <View style={[$.infoCard, { borderTopColor: color }]}><Text style={$.noData}>정보 없음</Text></View>;
  return (
    <View style={[$.infoCard, { borderTopColor: color }]}>
      {d.elementary_school_name && <Text style={$.infoLine}>초 {d.elementary_school_name}</Text>}
      {d.middle_school_zone && <Text style={$.infoLine}>중 {d.middle_school_zone}</Text>}
      {d.high_school_zone && <Text style={$.infoLine}>고 {d.high_school_zone}</Text>}
    </View>
  );
}

function SafetyCard({ d, color }: { d: ApartmentDetail['safety']; color: string }) {
  if (!d) return <View style={[$.infoCard, { borderTopColor: color }]}><Text style={$.noData}>정보 없음</Text></View>;
  const sc = d.nudge_safety_score;
  const c = sc >= 70 ? P.green : sc >= 40 ? P.amber : P.rose;
  return (
    <View style={[$.infoCard, { borderTopColor: color }]}>
      <Text style={[$.sfScore, { color: c }]}>{sc.toFixed(0)}</Text>
      <Text style={$.sfLbl}>종합 안전</Text>
      <Text style={$.infoLine}>CCTV {d.cctv_count_500m}대 (500m)</Text>
    </View>
  );
}

function SH({ title }: { title: string }) {
  return <View style={$.shRow}><View style={$.shDot} /><Text style={$.shT}>{title}</Text></View>;
}

function fd(m: number | undefined) {
  if (m == null) return '-';
  return m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`;
}

/* ── Palette ── */
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
  hdrTitle: { fontSize: 17, fontWeight: '700', color: P.text, flex: 1 },

  // Win strip
  winStrip: { flexDirection: 'row', alignItems: 'center', backgroundColor: P.blueLight, paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#BFDBFE' },
  winSide: { flex: 1 },
  winName: { fontSize: 12, fontWeight: '600', color: P.text },
  winCount: { fontSize: 20, fontWeight: '900', marginTop: 2, letterSpacing: -0.5 },
  winVs: { width: 36, height: 36, borderRadius: 18, backgroundColor: P.blue, justifyContent: 'center', alignItems: 'center', marginHorizontal: 12 },
  winVsT: { fontSize: 11, fontWeight: '800', color: '#FFF', letterSpacing: 1 },

  body: { flex: 1 },
  sec: { paddingHorizontal: 16, paddingTop: 8 },

  shRow: { flexDirection: 'row', alignItems: 'center', marginTop: 16, marginBottom: 12, gap: 8 },
  shDot: { width: 3, height: 12, backgroundColor: P.blue, borderRadius: 1.5 },
  shT: { fontSize: 13, fontWeight: '700', color: P.text },

  // Apt cards
  cardRow: { flexDirection: 'row', gap: 8 },
  aptCard: { flex: 1, backgroundColor: P.card, borderRadius: 10, padding: 12, borderTopWidth: 3, borderWidth: 1, borderColor: P.border },
  aptTag: { position: 'absolute', top: 8, right: 8, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 1 },
  aptTagT: { fontSize: 10, fontWeight: '700', color: '#FFF' },
  aptName: { fontSize: 13, fontWeight: '700', color: P.text, marginBottom: 4, paddingRight: 22 },
  aptMeta: { fontSize: 10, color: P.text3 },

  // VS score bars
  vsRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 4 },
  vsVal: { width: 26, fontSize: 12, textAlign: 'center', color: P.text3 },
  vsWin: { fontWeight: '800', color: P.text },
  vsBars: { flex: 1, flexDirection: 'row', alignItems: 'center' },
  vsBarL: { flex: 1, height: 6, backgroundColor: P.card, borderRadius: 3, overflow: 'hidden', flexDirection: 'row', justifyContent: 'flex-end', borderWidth: 1, borderColor: P.border },
  vsBarLF: { height: '100%', backgroundColor: '#93C5FD', borderRadius: 3 },
  vsLabel: { width: 48, textAlign: 'center', fontSize: 10, color: P.text2, fontWeight: '500' },
  vsBarR: { flex: 1, height: 6, backgroundColor: P.card, borderRadius: 3, overflow: 'hidden', borderWidth: 1, borderColor: P.border },
  vsBarRF: { height: '100%', backgroundColor: '#C4B5FD', borderRadius: 3 },

  // Table
  tbl: { borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: P.border },
  tblH: { flexDirection: 'row', backgroundColor: P.card, paddingVertical: 8 },
  tblHC: { flex: 1, textAlign: 'center', fontSize: 10, fontWeight: '600', color: P.text2 },
  tblR: { flexDirection: 'row', paddingVertical: 9, borderTopWidth: 1, borderTopColor: P.border },
  tblC: { flex: 1, textAlign: 'center', fontSize: 12, color: P.text2 },
  tblCW: { fontWeight: '700', color: P.green },

  // Info cards
  infoCard: { flex: 1, backgroundColor: P.card, borderRadius: 10, padding: 12, borderTopWidth: 3, borderWidth: 1, borderColor: P.border },
  infoLine: { fontSize: 12, color: P.text, marginBottom: 3, fontWeight: '500' },
  noData: { fontSize: 12, color: P.text3, textAlign: 'center' },
  sfScore: { fontSize: 28, fontWeight: '900', textAlign: 'center', letterSpacing: -1 },
  sfLbl: { fontSize: 10, color: P.text3, textAlign: 'center', marginBottom: 4 },
});
