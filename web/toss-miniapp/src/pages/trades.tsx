import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import { apiPaths } from '../shared/api/paths';
import type { CommonCodeRow } from '../shared/types/apartment-list';
import type { DashboardRecentTrade } from '../shared/types/dashboard';
import { useApi } from '../hooks/useApi';
import { formatPrice } from '../lib/format';

export const Route = createRoute('/trades', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: TradesPage,
});

function TradesPage() {
  const navigation = Route.useNavigation();
  const [keyword, setKeyword] = useState('');
  const [selected, setSelected] = useState<{
    code: string;
    label: string;
  } | null>(null);

  const sigunguList = useApi<CommonCodeRow[]>(apiPaths.codeGroup('sigungu'));

  const filtered = useMemo(() => {
    const rows = sigunguList.data ?? [];
    if (!keyword.trim()) return rows.slice(0, 30);
    const k = keyword.trim();
    return rows
      .filter(
        (r) => r.name.includes(k) || (r.extra ? r.extra.includes(k) : false)
      )
      .slice(0, 50);
  }, [sigunguList.data, keyword]);

  const trades = useApi<DashboardRecentTrade[]>(
    selected ? apiPaths.dashboardRecent() : null,
    selected ? { sigungu: selected.code, limit: 50 } : undefined
  );

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>지역별 거래내역</Text>
        {!selected ? (
          <TextInput
            style={styles.search}
            placeholder="시·도 또는 시·군·구 (예: 강남, 서울)"
            placeholderTextColor="#A2A8B4"
            value={keyword}
            onChangeText={setKeyword}
            autoCorrect={false}
            autoCapitalize="none"
          />
        ) : (
          <TouchableOpacity
            style={styles.selectedChip}
            onPress={() => setSelected(null)}
            activeOpacity={0.8}
          >
            <Text style={styles.selectedChipText}>
              {selected.label} · 다른 지역 선택
            </Text>
          </TouchableOpacity>
        )}
      </View>

      {selected ? (
        <TradeList
          state={trades}
          regionLabel={selected.label}
          onTap={(pnu, name) => navigation.navigate('/apt', { pnu, name })}
        />
      ) : (
        <RegionList
          state={sigunguList}
          rows={filtered}
          onSelect={(row) =>
            setSelected({
              code: row.code,
              label: `${row.extra ?? ''} ${row.name}`.trim(),
            })
          }
        />
      )}
    </View>
  );
}

function RegionList({
  state,
  rows,
  onSelect,
}: {
  state: ReturnType<typeof useApi<CommonCodeRow[]>>;
  rows: CommonCodeRow[];
  onSelect: (row: CommonCodeRow) => void;
}) {
  if (state.loading) {
    return (
      <Centered>
        <ActivityIndicator color="#3182F6" />
      </Centered>
    );
  }
  if (state.error) {
    return (
      <Centered>
        <Text style={styles.error}>지역 목록 불러오기 실패</Text>
      </Centered>
    );
  }
  if (rows.length === 0) {
    return (
      <Centered>
        <Text style={styles.empty}>일치하는 지역이 없어요.</Text>
      </Centered>
    );
  }
  return (
    <ScrollView contentContainerStyle={styles.listPad}>
      {rows.map((r) => (
        <TouchableOpacity
          key={r.code}
          style={styles.regionRow}
          onPress={() => onSelect(r)}
          activeOpacity={0.7}
        >
          <Text style={styles.regionExtra}>{r.extra ?? ''}</Text>
          <Text style={styles.regionName}>{r.name}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

function TradeList({
  state,
  regionLabel,
  onTap,
}: {
  state: ReturnType<typeof useApi<DashboardRecentTrade[]>>;
  regionLabel: string;
  onTap: (pnu: string, name: string) => void;
}) {
  if (state.loading) {
    return (
      <Centered>
        <ActivityIndicator color="#3182F6" />
      </Centered>
    );
  }
  if (state.error) {
    return (
      <Centered>
        <Text style={styles.error}>
          거래내역 불러오기 실패: {state.error.message}
        </Text>
      </Centered>
    );
  }
  const rows = state.data ?? [];
  if (rows.length === 0) {
    return (
      <Centered>
        <Text style={styles.empty}>{regionLabel}에 최근 거래가 없어요.</Text>
      </Centered>
    );
  }
  return (
    <ScrollView contentContainerStyle={styles.listPad}>
      <Text style={styles.subheader}>
        {regionLabel} · 최근 거래 {rows.length.toLocaleString()}건
      </Text>
      {rows.map((t, i) => {
        const Card = t.pnu ? TouchableOpacity : View;
        return (
          <Card
            key={`${t.pnu ?? t.apt_nm}-${i}`}
            style={styles.tradeCard}
            {...(t.pnu
              ? {
                  onPress: () => onTap(t.pnu as string, t.apt_nm),
                  activeOpacity: 0.7,
                }
              : {})}
          >
            <View style={styles.tradeTop}>
              <Text style={styles.tradeName} numberOfLines={1}>
                {t.apt_nm}
              </Text>
              <Text style={styles.tradePrice}>
                {t.price ? `${formatPrice(t.price)}만원` : '-'}
              </Text>
            </View>
            <Text style={styles.tradeMeta}>
              {t.area ? `${t.area.toFixed(0)}㎡` : '-'}
              {t.floor != null ? ` · ${t.floor}층` : ''}
              {' · '}
              {t.date}
            </Text>
          </Card>
        );
      })}
    </ScrollView>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <View style={styles.centered}>{children}</View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F6F8' },
  header: {
    backgroundColor: 'white',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#EEF0F4',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: '#202632',
    marginBottom: 8,
  },
  search: {
    backgroundColor: '#F1F3F5',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#202632',
  },
  selectedChip: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#E8F0FE',
    borderRadius: 8,
  },
  selectedChipText: { fontSize: 12, color: '#3182F6', fontWeight: '600' },
  listPad: { padding: 16 },
  subheader: { fontSize: 13, color: '#6B7684', marginBottom: 12 },
  regionRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    paddingVertical: 12,
    paddingHorizontal: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#EEF0F4',
  },
  regionExtra: { fontSize: 12, color: '#A2A8B4', width: 56 },
  regionName: { fontSize: 16, color: '#202632', fontWeight: '600' },
  tradeCard: {
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
  },
  tradeTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  tradeName: {
    fontSize: 15,
    fontWeight: '700',
    color: '#202632',
    flex: 1,
    marginRight: 12,
  },
  tradePrice: {
    fontSize: 16,
    color: '#3182F6',
    fontWeight: '800',
  },
  tradeMeta: { fontSize: 12, color: '#6B7684', marginTop: 4 },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: '#E84A4A', fontSize: 13, textAlign: 'center', padding: 16 },
  empty: { color: '#A2A8B4', fontSize: 13 },
});
