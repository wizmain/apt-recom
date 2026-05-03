/**
 * 최근 거래내역 — 기간(프리셋/직접) + 선택적 시군구로 거래를 둘러보는 화면.
 *
 * URL params (parserParams identity 로 raw string 유지 — apt.tsx 동일 패턴):
 *   preset:      '1w' | '1m' | '3m' | '6m' | 'all' | 'custom'   기본 '1m'
 *   from, to:    YYYYMMDD                                       (custom 일 때 사용)
 *   sigungu:     5자리 코드                                     (빈 값 = 전국)
 *   sigunguName: 표시용 라벨                                    (재조회 회피)
 *
 * 페이지 내부 상태 변경 시 navigation.replace 로 history 누적 방지.
 */

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
import type { DashboardRecentTrade } from '../shared/types/dashboard';
import { useApi } from '../hooks/useApi';
import TradeCard from '../components/TradeCard';
import RegionPicker from '../components/RegionPicker';
import {
  PRESET_LIST,
  parseYmdInput,
  presetToRange,
  formatYmdHuman,
  daysBetween,
  type PeriodPreset,
} from '../lib/period';

const PRESET_VALUES: ReadonlyArray<PeriodPreset> = [
  '1w',
  '1m',
  '3m',
  '6m',
  'all',
  'custom',
];

interface RouteParams {
  preset: PeriodPreset;
  from: string;
  to: string;
  sigungu: string;
  sigunguName: string;
}

export const Route = createRoute('/recent-trades', {
  // YYYYMMDD 문자열이 JSON.parse 로 Number 변환되며 손상되는 것 방지.
  parserParams: (params) => params,
  validateParams: (params: Readonly<object | undefined>): RouteParams => {
    const p = (params ?? {}) as Record<string, unknown>;
    const preset = PRESET_VALUES.includes(p.preset as PeriodPreset)
      ? (p.preset as PeriodPreset)
      : '1m';
    const isYmd = (v: unknown): v is string =>
      typeof v === 'string' && /^\d{8}$/.test(v);
    return {
      preset,
      from: isYmd(p.from) ? p.from : '',
      to: isYmd(p.to) ? p.to : '',
      sigungu: typeof p.sigungu === 'string' ? p.sigungu : '',
      sigunguName: typeof p.sigunguName === 'string' ? p.sigunguName : '',
    };
  },
  component: RecentTradesPage,
});

function RecentTradesPage() {
  const initial = Route.useParams();
  const navigation = Route.useNavigation();

  const [preset, setPreset] = useState<PeriodPreset>(initial.preset);
  const [customFrom, setCustomFrom] = useState(initial.from);
  const [customTo, setCustomTo] = useState(initial.to);
  const [fromInput, setFromInput] = useState(
    initial.from ? formatYmdHuman(initial.from) : '',
  );
  const [toInput, setToInput] = useState(
    initial.to ? formatYmdHuman(initial.to) : '',
  );
  const [sigungu, setSigungu] = useState(
    initial.sigungu
      ? { code: initial.sigungu, name: initial.sigunguName || initial.sigungu }
      : null,
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);

  const range = useMemo(
    () => presetToRange(preset, customFrom, customTo),
    [preset, customFrom, customTo],
  );

  const trades = useApi<DashboardRecentTrade[]>(apiPaths.dashboardRecent(), {
    type: 'trade',
    limit: 100,
    sigungu: sigungu?.code || undefined,
    from_date: range.from,
    to_date: range.to,
  });

  const syncUrl = (next: Partial<RouteParams>) => {
    const params: RouteParams = {
      preset,
      from: customFrom,
      to: customTo,
      sigungu: sigungu?.code ?? '',
      sigunguName: sigungu?.name ?? '',
      ...next,
    };
    navigation.replace('/recent-trades', params);
  };

  const onPickPreset = (next: PeriodPreset) => {
    setPreset(next);
    setCustomError(null);
    syncUrl({ preset: next });
  };

  const onApplyCustom = () => {
    const f = parseYmdInput(fromInput);
    const t = parseYmdInput(toInput);
    if (!f || !t) {
      setCustomError('날짜를 YYYY-MM-DD 형식으로 정확히 입력해 주세요.');
      return;
    }
    if (daysBetween(f, t) < 0) {
      setCustomError('시작일이 종료일보다 늦을 수 없어요.');
      return;
    }
    if (daysBetween(f, t) > 366) {
      setCustomError('한 번에 조회할 수 있는 기간은 최대 366일이에요.');
      return;
    }
    setCustomError(null);
    setCustomFrom(f);
    setCustomTo(t);
    syncUrl({ preset: 'custom', from: f, to: t });
  };

  const onChangeRegion = (next: { code: string; name: string } | null) => {
    setSigungu(next);
    setPickerOpen(false);
    syncUrl({ sigungu: next?.code ?? '', sigunguName: next?.name ?? '' });
  };

  const goApt = (pnu: string, name: string) =>
    navigation.navigate('/apt', { pnu, name });

  const regionLabel = sigungu?.name ?? '전국';
  const totalLabel =
    trades.data && !trades.loading && !trades.error
      ? `총 ${trades.data.length.toLocaleString()}건`
      : '';

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>최근 거래내역</Text>

        <View style={styles.regionRow}>
          <View style={styles.regionChip}>
            <Text style={styles.regionChipText}>{regionLabel}</Text>
            {sigungu ? (
              <TouchableOpacity
                onPress={() => onChangeRegion(null)}
                style={styles.regionClear}
                activeOpacity={0.7}
              >
                <Text style={styles.regionClearText}>×</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          <TouchableOpacity
            onPress={() => setPickerOpen((v) => !v)}
            style={styles.regionToggle}
            activeOpacity={0.7}
          >
            <Text style={styles.regionToggleText}>
              {pickerOpen ? '닫기' : '지역 선택'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.bodyPad}
        keyboardShouldPersistTaps="handled"
      >
        {pickerOpen ? (
          <RegionPicker value={sigungu} onChange={onChangeRegion} />
        ) : null}

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipsRow}
        >
          {PRESET_LIST.map((p) => {
            const active = p.value === preset;
            return (
              <TouchableOpacity
                key={p.value}
                style={[styles.chip, active ? styles.chipActive : null]}
                onPress={() => onPickPreset(p.value)}
                activeOpacity={0.7}
              >
                <Text
                  style={[
                    styles.chipText,
                    active ? styles.chipTextActive : null,
                  ]}
                >
                  {p.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {preset === 'custom' ? (
          <View style={styles.customCard}>
            <Text style={styles.customTitle}>직접 기간 선택</Text>
            <View style={styles.customRow}>
              <TextInput
                style={styles.customInput}
                placeholder="시작 YYYY-MM-DD"
                placeholderTextColor="#A2A8B4"
                value={fromInput}
                onChangeText={setFromInput}
                keyboardType="number-pad"
                maxLength={10}
              />
              <Text style={styles.customSep}>~</Text>
              <TextInput
                style={styles.customInput}
                placeholder="종료 YYYY-MM-DD"
                placeholderTextColor="#A2A8B4"
                value={toInput}
                onChangeText={setToInput}
                keyboardType="number-pad"
                maxLength={10}
              />
            </View>
            {customError ? (
              <Text style={styles.customError}>{customError}</Text>
            ) : null}
            <TouchableOpacity
              style={styles.customApply}
              onPress={onApplyCustom}
              activeOpacity={0.8}
            >
              <Text style={styles.customApplyText}>적용</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <Text style={styles.subheader}>
          {regionLabel} · {range.label}
          {totalLabel ? ` · ${totalLabel}` : ''}
        </Text>

        <Body state={trades} onPress={goApt} />
      </ScrollView>
    </View>
  );
}

function Body({
  state,
  onPress,
}: {
  state: ReturnType<typeof useApi<DashboardRecentTrade[]>>;
  onPress: (pnu: string, name: string) => void;
}) {
  if (state.loading) {
    return (
      <View style={styles.statePad}>
        <ActivityIndicator color="#3182F6" />
      </View>
    );
  }
  if (state.error) {
    return (
      <View style={styles.statePad}>
        <Text style={styles.errorText}>
          거래내역 불러오기 실패: {state.error.message}
        </Text>
      </View>
    );
  }
  const rows = state.data ?? [];
  if (rows.length === 0) {
    return (
      <View style={styles.statePad}>
        <Text style={styles.emptyText}>선택한 기간에 거래가 없어요.</Text>
      </View>
    );
  }
  return (
    <View>
      {rows.map((t, i) => (
        <TradeCard
          key={`${t.pnu ?? t.apt_nm}-${i}`}
          item={t}
          onPress={onPress}
        />
      ))}
    </View>
  );
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
    marginBottom: 10,
  },
  regionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  regionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E8F0FE',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },
  regionChipText: {
    fontSize: 13,
    color: '#3182F6',
    fontWeight: '700',
  },
  regionClear: {
    marginLeft: 6,
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3182F6',
  },
  regionClearText: { color: 'white', fontSize: 12, lineHeight: 14 },
  regionToggle: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D1D6DB',
  },
  regionToggleText: { fontSize: 12, color: '#202632', fontWeight: '600' },
  body: { flex: 1 },
  bodyPad: { padding: 16 },
  chipsRow: {
    flexDirection: 'row',
    gap: 8,
    paddingVertical: 4,
    paddingRight: 8,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#F1F3F5',
    borderRadius: 999,
  },
  chipActive: {
    backgroundColor: '#3182F6',
  },
  chipText: { fontSize: 13, color: '#6B7684', fontWeight: '600' },
  chipTextActive: { color: 'white' },
  customCard: {
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 14,
    marginTop: 10,
  },
  customTitle: {
    fontSize: 13,
    color: '#202632',
    fontWeight: '700',
    marginBottom: 10,
  },
  customRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  customInput: {
    flex: 1,
    backgroundColor: '#F1F3F5',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#202632',
  },
  customSep: { fontSize: 14, color: '#A2A8B4' },
  customError: {
    marginTop: 8,
    fontSize: 12,
    color: '#E84A4A',
  },
  customApply: {
    marginTop: 10,
    backgroundColor: '#3182F6',
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: 'center',
  },
  customApplyText: { color: 'white', fontSize: 14, fontWeight: '700' },
  subheader: {
    fontSize: 13,
    color: '#6B7684',
    marginTop: 16,
    marginBottom: 12,
  },
  statePad: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  errorText: {
    color: '#E84A4A',
    fontSize: 13,
    textAlign: 'center',
    paddingHorizontal: 16,
  },
  emptyText: { color: '#A2A8B4', fontSize: 13 },
});
