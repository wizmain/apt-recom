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
import { apiPaths } from '../shared/api/paths';
import type {
  DashboardSummary,
  DashboardRankingItem,
  DashboardRecentTrade,
} from '../shared/types/dashboard';
import type { ContentListItem } from '../types/content';
import ContentCard from '../components/ContentCard';
import { useApi } from '../hooks/useApi';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { formatPrice } from '../lib/format';

export const Route = createRoute('/', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: HomePage,
});

function HomePage() {
  const navigation = Route.useNavigation();
  const goSearch = () => navigation.navigate('/search', {});
  const goTrades = () => navigation.navigate('/trades', {});
  const goRecent = () =>
    navigation.navigate('/recent-trades', {
      preset: '1m',
      from: '',
      to: '',
      sigungu: '',
      sigunguName: '',
    });
  const goApt = (pnu: string, name: string) =>
    navigation.navigate('/apt', { pnu, name });
  const network = useNetworkStatus();
  const offline = network === 'OFFLINE';

  const summary = useApi<DashboardSummary>(apiPaths.dashboardSummary(), {
    // 신고 지연 보정한 30~60일 전 윈도우(기본) 대신 오늘 기준 직전 30일 데이터 사용.
    // 단점: 최근 며칠은 신고 지연으로 과소집계될 수 있음.
    recent: true,
  });
  const ranking = useApi<DashboardRankingItem[]>(apiPaths.dashboardRanking());
  const recent = useApi<DashboardRecentTrade[]>(apiPaths.dashboardRecent(), {
    limit: 5,
  });
  const content = useApi<ContentListItem[]>(apiPaths.content());
  const goContent = () => navigation.navigate('/content', {});
  const goArticle = (slug: string) =>
    navigation.navigate('/content-article', { slug });

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

      <View style={styles.ctaRow}>
        <TouchableOpacity
          style={[styles.cta, styles.ctaPrimary, styles.ctaHalf]}
          onPress={goTrades}
          activeOpacity={0.8}
        >
          <Text style={styles.ctaText}>지역별 거래내역</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.cta, styles.ctaSecondary, styles.ctaHalf]}
          onPress={goSearch}
          activeOpacity={0.8}
        >
          <Text style={styles.ctaTextSecondary}>지역별 아파트 검색</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        style={styles.ctaWide}
        onPress={goRecent}
        activeOpacity={0.8}
      >
        <Text style={styles.ctaTextSecondary}>기간별 최근 거래내역</Text>
      </TouchableOpacity>

      <RecentCard state={recent} onTap={goApt} />
      <SummaryCard state={summary} />
      <RankingCard state={ranking} />
      {content.data && content.data.length > 0 && (
        <View style={styles.contentSection}>
          <View style={styles.contentHead}>
            <Text style={styles.contentTitle}>숫자로 보는 집 이야기</Text>
            <TouchableOpacity onPress={goContent} activeOpacity={0.8}>
              <Text style={styles.contentMore}>전체 보기</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.contentGap}>
            {content.data.slice(0, 2).map((item) => (
              <ContentCard
                key={item.slug}
                item={item}
                onPress={() => goArticle(item.slug)}
              />
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}

function RecentCard({
  state,
  onTap,
}: {
  state: ReturnType<typeof useApi<DashboardRecentTrade[]>>;
  onTap: (pnu: string, name: string) => void;
}) {
  return (
    <Card title="최근 거래">
      <CardBody state={state}>
        {(d) => (
          <View>
            {d.slice(0, 5).map((t, i) => {
              // pnu 매핑이 있는 거래만 단지 상세로 이동 가능. 없으면 정적 표시.
              const Wrap = t.pnu ? TouchableOpacity : View;
              return (
                <Wrap
                  key={`${t.pnu ?? t.apt_nm}-${i}`}
                  style={styles.recentRow}
                  {...(t.pnu
                    ? {
                        onPress: () => onTap(t.pnu as string, t.apt_nm),
                        activeOpacity: 0.7,
                      }
                    : {})}
                >
                  <View style={styles.recentTop}>
                    <Text style={styles.recentName} numberOfLines={1}>
                      {t.apt_nm}
                    </Text>
                    <Text style={styles.recentPrice}>
                      {t.price ? `${formatPrice(t.price)}만원` : '-'}
                    </Text>
                  </View>
                  <Text style={styles.recentMeta}>
                    {t.sigungu}
                    {t.area ? ` · ${t.area.toFixed(0)}㎡` : ''}
                    {t.floor != null ? ` · ${t.floor}층` : ''}
                    {' · '}
                    {t.date}
                  </Text>
                </Wrap>
              );
            })}
            {d.length === 0 ? <Empty /> : null}
          </View>
        )}
      </CardBody>
    </Card>
  );
}

function SummaryCard({
  state,
}: {
  state: ReturnType<typeof useApi<DashboardSummary>>;
}) {
  return (
    <Card title="최근 30일 거래 요약">
      <CardBody state={state}>
        {(d) => (
          <View>
            <Row label="기간" value={d.current_period} />
            <Row
              label="매매 건수"
              value={`${d.trade.volume.toLocaleString()}건`}
            />
            <Row
              label="매매 ㎡당"
              value={`${formatPrice(d.trade.median_price_m2)}만원`}
            />
            <Row
              label="전월세 건수"
              value={`${d.rent.volume.toLocaleString()}건`}
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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
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
  ctaRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 20,
  },
  cta: {
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
  },
  ctaHalf: { flex: 1 },
  ctaPrimary: { backgroundColor: '#3182F6' },
  ctaSecondary: {
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: '#D1D6DB',
  },
  ctaText: { color: 'white', fontSize: 15, fontWeight: '700' },
  ctaTextSecondary: { color: '#202632', fontSize: 15, fontWeight: '700' },
  ctaWide: {
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: '#D1D6DB',
    marginBottom: 20,
  },
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
  rowValue: { fontSize: 14, color: '#202632', fontWeight: '600' },
  recentRow: { paddingVertical: 10 },
  recentTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  recentName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#202632',
    flex: 1,
    marginRight: 12,
  },
  recentPrice: {
    fontSize: 16,
    color: '#3182F6',
    fontWeight: '800',
  },
  recentMeta: { fontSize: 12, color: '#6B7684', marginTop: 4 },
  error: { color: '#E84A4A', fontSize: 13 },
  empty: { color: '#A2A8B4', fontSize: 13 },
  offlineBar: {
    backgroundColor: '#FFF6E5',
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
  },
  offlineText: { color: '#B6791C', fontSize: 13 },
  contentSection: { marginTop: 20 },
  contentHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  contentTitle: { color: '#191F28', fontSize: 18, fontWeight: '900' },
  contentMore: { color: '#3182F6', fontSize: 13, fontWeight: '700' },
  contentGap: { gap: 12 },
});
