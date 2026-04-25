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
import { apiPaths } from '@apt-recom/shared/api/paths';
import type { CommonCodeRow, ApartmentListItem } from '@apt-recom/shared/types/apartment-list';
import { useApi } from '../hooks/useApi';
import { formatPrice } from '../lib/format';

export const Route = createRoute('/search', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: SearchPage,
});

function SearchPage() {
  const navigation = Route.useNavigation();
  const [keyword, setKeyword] = useState('');
  const [selected, setSelected] = useState<{
    code: string;
    label: string;
  } | null>(null);

  const sigunguList = useApi<CommonCodeRow[]>(apiPaths.codeGroup('sigungu'));

  // 키워드 필터: 시·도(extra) 또는 시·군·구 이름에 매칭.
  const filtered = useMemo(() => {
    const rows = sigunguList.data ?? [];
    if (!keyword.trim()) return rows.slice(0, 30);
    const k = keyword.trim();
    return rows
      .filter(
        (r) =>
          r.name.includes(k) || (r.extra ? r.extra.includes(k) : false)
      )
      .slice(0, 50);
  }, [sigunguList.data, keyword]);

  // 지역 선택 시에만 아파트 목록 페치.
  const apts = useApi<ApartmentListItem[]>(
    selected ? apiPaths.apartmentsList() : null,
    selected ? { sigungu_code: selected.code } : undefined
  );

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>지역 검색</Text>
        <TextInput
          style={styles.search}
          placeholder="시·도 또는 시·군·구 (예: 강남, 서울)"
          placeholderTextColor="#A2A8B4"
          value={keyword}
          onChangeText={setKeyword}
          autoCorrect={false}
          autoCapitalize="none"
        />
        {selected ? (
          <TouchableOpacity
            style={styles.selectedChip}
            onPress={() => setSelected(null)}
            activeOpacity={0.8}
          >
            <Text style={styles.selectedChipText}>
              {selected.label} · 해제
            </Text>
          </TouchableOpacity>
        ) : null}
      </View>

      {selected ? (
        <AptList
          state={apts}
          regionLabel={selected.label}
          onTap={(pnu) => navigation.navigate('/apt', { pnu })}
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
    return <Centered><ActivityIndicator color="#3182F6" /></Centered>;
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

function AptList({
  state,
  regionLabel,
  onTap,
}: {
  state: ReturnType<typeof useApi<ApartmentListItem[]>>;
  regionLabel: string;
  onTap: (pnu: string) => void;
}) {
  if (state.loading) {
    return <Centered><ActivityIndicator color="#3182F6" /></Centered>;
  }
  if (state.error) {
    return (
      <Centered>
        <Text style={styles.error}>
          아파트 목록 불러오기 실패: {state.error.message}
        </Text>
      </Centered>
    );
  }
  const rows = state.data ?? [];
  if (rows.length === 0) {
    return (
      <Centered>
        <Text style={styles.empty}>{regionLabel}에 표시할 아파트가 없어요.</Text>
      </Centered>
    );
  }
  return (
    <ScrollView contentContainerStyle={styles.listPad}>
      <Text style={styles.subheader}>
        {regionLabel} · {rows.length.toLocaleString()}개
      </Text>
      {rows.map((a) => (
        <TouchableOpacity
          key={a.pnu}
          style={styles.aptRow}
          onPress={() => onTap(a.pnu)}
          activeOpacity={0.7}
        >
          <Text style={styles.aptName} numberOfLines={1}>
            {a.bld_nm}
          </Text>
          <Text style={styles.aptMeta}>
            {a.area_min && a.area_max
              ? `${a.area_min.toFixed(0)}~${a.area_max.toFixed(0)}㎡`
              : '면적 미상'}
            {' · '}
            {a.total_hhld_cnt ? `${a.total_hhld_cnt.toLocaleString()}세대` : ''}
            {a.max_floor ? ` · ${a.max_floor}F` : ''}
          </Text>
          {a.price_per_m2 ? (
            <Text style={styles.aptPrice}>
              ㎡당 {formatPrice(Math.round(a.price_per_m2))}만원
            </Text>
          ) : null}
        </TouchableOpacity>
      ))}
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
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#E8F0FE',
    borderRadius: 8,
  },
  selectedChipText: { fontSize: 12, color: '#3182F6', fontWeight: '600' },
  listPad: { padding: 16 },
  subheader: {
    fontSize: 13,
    color: '#6B7684',
    marginBottom: 12,
  },
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
  aptRow: {
    backgroundColor: 'white',
    padding: 14,
    borderRadius: 12,
    marginBottom: 8,
  },
  aptName: { fontSize: 15, fontWeight: '700', color: '#202632' },
  aptMeta: { fontSize: 12, color: '#6B7684', marginTop: 4 },
  aptPrice: { fontSize: 13, color: '#3182F6', marginTop: 6, fontWeight: '600' },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: '#E84A4A', fontSize: 13 },
  empty: { color: '#A2A8B4', fontSize: 13 },
});
