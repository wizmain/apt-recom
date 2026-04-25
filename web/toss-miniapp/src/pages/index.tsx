import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import { apiPaths } from '@apt-recom/shared/api/paths';
import type {
  DashboardSummary,
  DashboardRankingItem,
  DashboardRecentTrade,
} from '@apt-recom/shared/types/dashboard';
import { useApi } from '../hooks/useApi';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { changeRate, formatPrice, timeAgo } from '../lib/format';

export const Route = createRoute('/', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: HomePage,
});

function HomePage() {
  const navigation = Route.useNavigation();
  const goSearch = () => navigation.navigate('/search', {});
  const network = useNetworkStatus();
  const offline = network === 'OFFLINE';

  // 4 카드 동시 페치. v1 은 전국 기준 — 지역 필터는 search 페이지에서 적용.
  const summary = useApi<DashboardSummary>(apiPaths.dashboardSummary());
  const ranking = useApi<DashboardRankingItem[]>(apiPaths.dashboardRanking());
  const recent = useApi<DashboardRecentTrade[]>(apiPaths.dashboardRecent(), {
    limit: 5,
  });

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <Text style={styles.title}>집토리</Text>
      <Text style={styles.subtitle}>실시간 아파트 가격 정보</Text>
      {offline ? (
        <View style={styles.offlineBar}>
          <Text style={styles.offlineText}>
            오프라인 상태예요. 데이터를 불러올 수 없어요.
          </Text>
        </View>
      ) : null}

      <TouchableOpacity style={styles.cta} onPress={goSearch} activeOpacity={0.8}>
        <Text style={styles.ctaText}>지역으로 아파트 찾기</Text>
      </TouchableOpacity>

      <SummaryCard state={summary} />
      <RankingCard state={ranking} />
      <RecentCard state={recent} />

      {summary.data?.data_lag_notice ? (
        <Text style={styles.notice}>{summary.data.data_lag_notice}</Text>
      ) : null}
      {summary.data?.last_updated ? (
        <Text style={styles.notice}>
          마지막 업데이트 · {timeAgo(summary.data.last_updated)}
        </Text>
      ) : null}
    </ScrollView>
  );
}

function SummaryCard({
  state,
}: {
  state: ReturnType<typeof useApi<DashboardSummary>>;
}) {
  return (
    <Card title="이번 달 거래 요약">
      <CardBody state={state}>
        {(d) => (
          <View>
            <Row label="현재 기간" value={d.current_period} />
            <Row label="비교 기간" value={d.prev_period} />
            <Row
              label="매매 건수"
              value={`${d.trade.volume.toLocaleString()}건`}
              delta={changeRate(d.trade.volume, d.trade.prev_volume).text}
              deltaColor={changeRate(d.trade.volume, d.trade.prev_volume).color}
            />
            <Row
              label="매매 ㎡당"
              value={`${formatPrice(d.trade.median_price_m2)}만원`}
              delta={
                changeRate(d.trade.median_price_m2, d.trade.prev_median_price_m2)
                  .text
              }
              deltaColor={
                changeRate(d.trade.median_price_m2, d.trade.prev_median_price_m2)
                  .color
              }
            />
            <Row
              label="전월세 건수"
              value={`${d.rent.volume.toLocaleString()}건`}
              delta={changeRate(d.rent.volume, d.rent.prev_volume).text}
              deltaColor={changeRate(d.rent.volume, d.rent.prev_volume).color}
            />
          </View>
        )}
      </CardBody>
    </Card>
  );
}

function RankingCard({
  state,
}: {
  state: ReturnType<typeof useApi<DashboardRankingItem[]>>;
}) {
  return (
    <Card title="거래량 Top 시·군·구">
      <CardBody state={state}>
        {(d) => (
          <View>
            {d.slice(0, 5).map((row, i) => (
              <Row
                key={row.sigungu_code}
                label={`${i + 1}. ${row.sigungu_name}`}
                value={`${row.volume.toLocaleString()}건`}
              />
            ))}
            {d.length === 0 ? <Empty /> : null}
          </View>
        )}
      </CardBody>
    </Card>
  );
}

function RecentCard({
  state,
}: {
  state: ReturnType<typeof useApi<DashboardRecentTrade[]>>;
}) {
  return (
    <Card title="최근 거래">
      <CardBody state={state}>
        {(d) => (
          <View>
            {d.slice(0, 5).map((t, i) => (
              <View key={`${t.pnu ?? t.apt_nm}-${i}`} style={styles.recentRow}>
                <Text style={styles.recentName} numberOfLines={1}>
                  {t.apt_nm}
                </Text>
                <Text style={styles.recentMeta}>
                  {t.sigungu} · {t.area ? `${t.area.toFixed(0)}㎡` : '-'} ·{' '}
                  {t.price ? `${formatPrice(t.price)}만원` : '-'}
                </Text>
                <Text style={styles.recentDate}>{t.date}</Text>
              </View>
            ))}
            {d.length === 0 ? <Empty /> : null}
          </View>
        )}
      </CardBody>
    </Card>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function CardBody<T>({
  state,
  children,
}: {
  state: { data: T | null; loading: boolean; error: Error | null };
  children: (data: T) => React.ReactNode;
}) {
  if (state.loading) {
    return <ActivityIndicator size="small" color="#3182F6" />;
  }
  if (state.error) {
    return <Text style={styles.error}>불러오기 실패: {state.error.message}</Text>;
  }
  if (!state.data) return null;
  return <>{children(state.data)}</>;
}

function Row({
  label,
  value,
  delta,
  deltaColor,
}: {
  label: string;
  value: string;
  delta?: string;
  deltaColor?: string;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowRight}>
        <Text style={styles.rowValue}>{value}</Text>
        {delta ? (
          <Text style={[styles.rowDelta, { color: deltaColor ?? '#888' }]}>
            {delta}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

function Empty() {
  return <Text style={styles.empty}>표시할 데이터가 없어요.</Text>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F6F8' },
  content: { padding: 16, paddingBottom: 48 },
  title: { fontSize: 28, fontWeight: '800', color: '#202632' },
  subtitle: { fontSize: 14, color: '#6B7684', marginTop: 4, marginBottom: 16 },
  cta: {
    backgroundColor: '#3182F6',
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
    marginBottom: 20,
  },
  ctaText: { color: 'white', fontSize: 16, fontWeight: '700' },
  card: {
    backgroundColor: 'white',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#202632',
    marginBottom: 12,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  rowLabel: { fontSize: 14, color: '#6B7684', flex: 1 },
  rowRight: { flexDirection: 'row', alignItems: 'baseline' },
  rowValue: { fontSize: 14, color: '#202632', fontWeight: '600' },
  rowDelta: { fontSize: 12, marginLeft: 8 },
  recentRow: { paddingVertical: 8 },
  recentName: { fontSize: 14, fontWeight: '600', color: '#202632' },
  recentMeta: { fontSize: 12, color: '#6B7684', marginTop: 2 },
  recentDate: { fontSize: 11, color: '#A2A8B4', marginTop: 2 },
  error: { color: '#E84A4A', fontSize: 13 },
  empty: { color: '#A2A8B4', fontSize: 13 },
  notice: {
    fontSize: 11,
    color: '#A2A8B4',
    textAlign: 'center',
    marginTop: 8,
  },
  offlineBar: {
    backgroundColor: '#FFF6E5',
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
  },
  offlineText: { color: '#B6791C', fontSize: 13 },
});
