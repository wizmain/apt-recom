import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import { apiPaths } from '../shared/api/paths';
import { useApi } from '../hooks/useApi';
import { formatPrice } from '../lib/format';

interface ApartmentDetail {
  basic: {
    pnu: string;
    bld_nm: string;
    new_plat_plc: string | null;
    plat_plc: string | null;
    use_apr_day: string | null;
    total_hhld_cnt: number | null;
    max_floor: number | null;
    min_area: number | null;
    max_area: number | null;
    avg_area: number | null;
    price_per_m2: number | null;
  };
  school?: {
    elementary_school_full_name?: string | null;
    middle_school_zone?: string | null;
    high_school_zone?: string | null;
    estimated?: boolean;
  } | null;
  facility_summary?: Record<
    string,
    {
      nearest_distance_m: number | null;
      count_1km: number | null;
    }
  >;
  mgmt_cost?: MgmtCost | null;
}

interface MgmtCost {
  latest_year_month: string | null;
  cost_per_m2: number | null;
  region_avg_per_m2: number | null;
  region_avg_per_unit: number | null;
  by_area: MgmtCostByArea[] | null;
}

interface MgmtCostByArea {
  exclusive_area: number;
  unit_count: number;
  per_unit_cost: number;
  area_min: number | null;
  area_max: number | null;
  subtype_count: number | null;
}

interface TradeRow {
  id: number;
  deal_amount: number;
  exclu_use_ar: number | null;
  floor: number | null;
  deal_year: number;
  deal_month: number;
  deal_day: number;
}

interface TradesResponse {
  trades: TradeRow[];
  rents: unknown[];
}

export const Route = createRoute('/apt', {
  // Granite 의 defaultParserParams 는 모든 값에 JSON.parse 를 시도한다.
  // PNU 는 19자리 숫자 문자열이라 JSON.parse 시 Number 로 변환되며 정밀도 손실까지 발생.
  // → 모든 param 을 raw 문자열로 유지하도록 identity parser 사용.
  parserParams: (params) => params,
  validateParams: (params: Readonly<object | undefined>) => {
    const p = params as { pnu?: unknown; name?: unknown } | undefined;
    return {
      pnu: typeof p?.pnu === 'string' ? p.pnu : '',
      // 거래내역 / 검색 결과에서 사용자가 탭한 시점의 명칭 (선택).
      // 건축물대장 bld_nm 과 다를 때 사용자 친숙도가 높은 표기.
      name: typeof p?.name === 'string' ? p.name : '',
    };
  },
  component: AptDetailPage,
});

function AptDetailPage() {
  const { pnu, name } = Route.useParams();
  // pnu 가 없으면 API 호출 자체를 건너뛴다 (useApi 의 path=null → no-op).
  const detail = useApi<ApartmentDetail>(
    pnu ? apiPaths.apartmentDetail(pnu) : null
  );
  const trades = useApi<TradesResponse>(
    pnu ? apiPaths.apartmentTrades(pnu) : null,
    { limit: 10 }
  );

  if (!pnu) {
    return (
      <Status>
        <Text style={styles.empty}>
          단지를 선택해 주세요.{'\n'}홈에서 지역을 선택하면 단지 목록이 보여요.
        </Text>
      </Status>
    );
  }
  if (detail.loading) {
    return (
      <Status>
        <ActivityIndicator color="#3182F6" />
        <Text style={styles.empty}>불러오는 중…</Text>
      </Status>
    );
  }
  if (detail.error || !detail.data) {
    return (
      <Status>
        <Text style={styles.error}>
          상세 정보 불러오기 실패
        </Text>
        {detail.error ? (
          <Text style={styles.errorDetail}>{detail.error.message}</Text>
        ) : null}
      </Status>
    );
  }

  const b = detail.data.basic;
  const school = detail.data.school;
  const builtYear =
    b.use_apr_day && /^\d{4}/.test(b.use_apr_day)
      ? b.use_apr_day.slice(0, 4)
      : null;
  // 사용자가 탭한 명칭(거래내역/검색 표기) 우선. 건축물대장명과 다르면 보조 라벨.
  const primaryName = name || b.bld_nm;
  const showAlias = name && name !== b.bld_nm ? b.bld_nm : null;

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <Text style={styles.name}>{primaryName}</Text>
      {showAlias ? (
        <Text style={styles.nameAlias}>건축물대장 · {showAlias}</Text>
      ) : null}
      <Text style={styles.addr}>{b.new_plat_plc ?? b.plat_plc ?? ''}</Text>

      <Section title="기본 정보">
        <Row label="세대수" value={b.total_hhld_cnt ? `${b.total_hhld_cnt.toLocaleString()}세대` : '-'} />
        <Row label="최고층" value={b.max_floor ? `${b.max_floor}층` : '-'} />
        <Row label="준공" value={builtYear ? `${builtYear}년` : '-'} />
      </Section>

      <Section title="면적 / 시세">
        <Row
          label="면적"
          value={
            b.min_area && b.max_area
              ? `${b.min_area.toFixed(0)}~${b.max_area.toFixed(0)}㎡`
              : '-'
          }
        />
        <Row
          label="㎡당 가격"
          value={
            b.price_per_m2
              ? `${formatPrice(Math.round(b.price_per_m2 / 10000))}만원`
              : '-'
          }
        />
        {b.avg_area && b.price_per_m2 ? (
          <Row
            label={`평균 ${b.avg_area.toFixed(0)}㎡ 추정가`}
            value={`${formatPrice(
              Math.round((b.price_per_m2 * b.avg_area) / 10000)
            )}만원`}
          />
        ) : null}
      </Section>

      {detail.data.mgmt_cost ? (
        <MgmtCostSection mgmt={detail.data.mgmt_cost} />
      ) : null}

      {school ? (
        <Section title={`학군${school.estimated ? ' (추정)' : ''}`}>
          <Row label="초등학교" value={school.elementary_school_full_name ?? '-'} />
          <Row label="중학교 학군" value={school.middle_school_zone ?? '-'} />
          <Row label="고등학교 학군" value={school.high_school_zone ?? '-'} />
        </Section>
      ) : null}

      <Section title="최근 매매 거래">
        <TradeBody state={trades} />
      </Section>
    </ScrollView>
  );
}

function MgmtCostSection({ mgmt }: { mgmt: MgmtCost }) {
  // 기준 월 포맷: "202602" → "2026.02"
  const month =
    mgmt.latest_year_month && /^\d{6}$/.test(mgmt.latest_year_month)
      ? `${mgmt.latest_year_month.slice(0, 4)}.${mgmt.latest_year_month.slice(4)}`
      : null;

  const regionDelta =
    mgmt.cost_per_m2 != null && mgmt.region_avg_per_m2
      ? Math.round(
          ((mgmt.cost_per_m2 - mgmt.region_avg_per_m2) /
            mgmt.region_avg_per_m2) *
            100
        )
      : null;

  return (
    <Section title={`관리비${month ? ` (${month} 기준)` : ''}`}>
      <Row
        label="㎡당 월 관리비"
        value={
          mgmt.cost_per_m2 != null
            ? `${mgmt.cost_per_m2.toLocaleString()}원`
            : '-'
        }
      />
      <Row
        label="지역 평균 ㎡당"
        value={
          mgmt.region_avg_per_m2 != null
            ? `${mgmt.region_avg_per_m2.toLocaleString()}원${
                regionDelta != null
                  ? ` (${regionDelta >= 0 ? '+' : ''}${regionDelta}%)`
                  : ''
              }`
            : '-'
        }
      />
      {mgmt.by_area && mgmt.by_area.length > 0 ? (
        <View style={styles.mgmtAreaWrap}>
          <Text style={styles.mgmtAreaTitle}>면적별 세대당 월 관리비</Text>
          {mgmt.by_area.slice(0, 6).map((row) => (
            <View key={row.exclusive_area} style={styles.mgmtAreaRow}>
              <Text style={styles.mgmtAreaLabel}>
                {row.area_min != null && row.area_max != null
                  ? `${row.area_min.toFixed(0)}~${row.area_max.toFixed(0)}㎡`
                  : `${row.exclusive_area}㎡`}
                {row.unit_count
                  ? ` · ${row.unit_count.toLocaleString()}세대`
                  : ''}
              </Text>
              <Text style={styles.mgmtAreaValue}>
                {row.per_unit_cost.toLocaleString()}원
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </Section>
  );
}

function TradeBody({ state }: { state: ReturnType<typeof useApi<TradesResponse>> }) {
  if (state.loading) {
    return <ActivityIndicator size="small" color="#3182F6" />;
  }
  if (state.error || !state.data) {
    return <Text style={styles.error}>거래 이력 불러오기 실패</Text>;
  }
  const list = state.data.trades.slice(0, 10);
  if (list.length === 0) {
    return <Text style={styles.empty}>거래 이력이 없어요.</Text>;
  }
  return (
    <View>
      {list.map((t) => (
        <View key={t.id} style={styles.tradeRow}>
          <Text style={styles.tradeDate}>
            {t.deal_year}.{String(t.deal_month).padStart(2, '0')}.
            {String(t.deal_day).padStart(2, '0')}
          </Text>
          <Text style={styles.tradeMeta}>
            {t.exclu_use_ar ? `${t.exclu_use_ar.toFixed(0)}㎡` : '-'}
            {t.floor != null ? ` · ${t.floor}층` : ''}
          </Text>
          <Text style={styles.tradePrice}>{formatPrice(t.deal_amount)}만원</Text>
        </View>
      ))}
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

// 로딩/오류/안내 상태 화면 — root 와 동일한 배경/풀스크린 레이아웃 보장.
function Status({ children }: { children: React.ReactNode }) {
  return <View style={styles.status}>{children}</View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F6F8' },
  content: { padding: 16, paddingBottom: 48 },
  name: { fontSize: 22, fontWeight: '800', color: '#202632' },
  nameAlias: { fontSize: 12, color: '#A2A8B4', marginTop: 4 },
  addr: { fontSize: 13, color: '#6B7684', marginTop: 4, marginBottom: 16 },
  section: {
    backgroundColor: 'white',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#202632',
    marginBottom: 12,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: 6,
  },
  rowLabel: { fontSize: 14, color: '#6B7684', flex: 1 },
  rowValue: {
    fontSize: 14,
    color: '#202632',
    fontWeight: '600',
    flex: 1.4,
    textAlign: 'right',
  },
  tradeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F3F5',
  },
  tradeDate: { fontSize: 12, color: '#6B7684', width: 92 },
  tradeMeta: { fontSize: 12, color: '#A2A8B4', flex: 1 },
  tradePrice: { fontSize: 14, color: '#3182F6', fontWeight: '700' },
  mgmtAreaWrap: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#F1F3F5',
  },
  mgmtAreaTitle: {
    fontSize: 13,
    color: '#6B7684',
    fontWeight: '600',
    marginBottom: 8,
  },
  mgmtAreaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  mgmtAreaLabel: { fontSize: 13, color: '#6B7684', flex: 1 },
  mgmtAreaValue: { fontSize: 13, color: '#202632', fontWeight: '600' },
  status: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5F6F8',
    padding: 24,
    minHeight: 320,
  },
  error: { color: '#E84A4A', fontSize: 14, fontWeight: '600' },
  errorDetail: {
    color: '#6B7684',
    fontSize: 12,
    marginTop: 8,
    textAlign: 'center',
  },
  empty: { color: '#6B7684', fontSize: 14, marginTop: 12, textAlign: 'center' },
});
