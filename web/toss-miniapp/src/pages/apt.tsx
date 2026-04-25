import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import { apiPaths } from '@apt-recom/shared/api/paths';
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
  // params 는 navigation.navigate('/apt', { pnu }) 로 전달.
  validateParams: (params: Readonly<object | undefined>) => {
    const pnu = (params as { pnu?: unknown } | undefined)?.pnu;
    if (typeof pnu !== 'string' || !pnu) {
      throw new Error('pnu 파라미터가 필요합니다');
    }
    return { pnu };
  },
  component: AptDetailPage,
});

function AptDetailPage() {
  const { pnu } = Route.useParams();
  const detail = useApi<ApartmentDetail>(apiPaths.apartmentDetail(pnu));
  const trades = useApi<TradesResponse>(apiPaths.apartmentTrades(pnu), {
    limit: 10,
  });

  if (detail.loading) {
    return <Centered><ActivityIndicator color="#3182F6" /></Centered>;
  }
  if (detail.error || !detail.data) {
    return (
      <Centered>
        <Text style={styles.error}>
          상세 정보 불러오기 실패{detail.error ? `: ${detail.error.message}` : ''}
        </Text>
      </Centered>
    );
  }

  const b = detail.data.basic;
  const school = detail.data.school;
  const builtYear =
    b.use_apr_day && /^\d{4}/.test(b.use_apr_day)
      ? b.use_apr_day.slice(0, 4)
      : null;

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <Text style={styles.name}>{b.bld_nm}</Text>
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

function Centered({ children }: { children: React.ReactNode }) {
  return <View style={styles.centered}>{children}</View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F6F8' },
  content: { padding: 16, paddingBottom: 48 },
  name: { fontSize: 22, fontWeight: '800', color: '#202632' },
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
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: '#E84A4A', fontSize: 13 },
  empty: { color: '#A2A8B4', fontSize: 13 },
});
