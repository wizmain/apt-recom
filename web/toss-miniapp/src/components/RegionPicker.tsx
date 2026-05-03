/**
 * 시군구 선택 위젯 — 키워드 검색 + 시군구 리스트.
 *
 * 호출 측에서 open/close 상태를 관리하고, 선택 시 onChange 로 값을 받는다.
 * 사용처: recent-trades 페이지의 인라인 지역 선택. trades.tsx 는 자체 구현 유지.
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
import { apiPaths } from '../shared/api/paths';
import type { CommonCodeRow } from '../shared/types/apartment-list';
import { useApi } from '../hooks/useApi';

export interface SigunguValue {
  code: string;
  name: string;
}

interface Props {
  value: SigunguValue | null;
  onChange: (next: SigunguValue | null) => void;
}

export default function RegionPicker({ value, onChange }: Props) {
  const [keyword, setKeyword] = useState('');
  const sigunguList = useApi<CommonCodeRow[]>(apiPaths.codeGroup('sigungu'));

  const filtered = useMemo(() => {
    const rows = sigunguList.data ?? [];
    if (!keyword.trim()) return rows.slice(0, 30);
    const k = keyword.trim();
    return rows
      .filter(
        (r) => r.name.includes(k) || (r.extra ? r.extra.includes(k) : false),
      )
      .slice(0, 50);
  }, [sigunguList.data, keyword]);

  return (
    <View style={styles.root}>
      <TextInput
        style={styles.search}
        placeholder="시·도 또는 시·군·구 (예: 강남, 서울)"
        placeholderTextColor="#A2A8B4"
        value={keyword}
        onChangeText={setKeyword}
        autoCorrect={false}
        autoCapitalize="none"
      />
      {value ? (
        <TouchableOpacity
          style={styles.clearBtn}
          onPress={() => onChange(null)}
          activeOpacity={0.8}
        >
          <Text style={styles.clearText}>전국으로 보기</Text>
        </TouchableOpacity>
      ) : null}

      {sigunguList.loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color="#3182F6" />
        </View>
      ) : sigunguList.error ? (
        <Text style={styles.error}>지역 목록 불러오기 실패</Text>
      ) : filtered.length === 0 ? (
        <Text style={styles.empty}>일치하는 지역이 없어요.</Text>
      ) : (
        <ScrollView
          style={styles.list}
          contentContainerStyle={styles.listPad}
          keyboardShouldPersistTaps="handled"
        >
          {filtered.map((r) => (
            <TouchableOpacity
              key={r.code}
              style={styles.row}
              onPress={() =>
                onChange({
                  code: r.code,
                  name: `${r.extra ?? ''} ${r.name}`.trim(),
                })
              }
              activeOpacity={0.7}
            >
              <Text style={styles.extra}>{r.extra ?? ''}</Text>
              <Text style={styles.name}>{r.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  search: {
    backgroundColor: '#F1F3F5',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#202632',
  },
  clearBtn: {
    alignSelf: 'flex-start',
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#F1F3F5',
    borderRadius: 8,
  },
  clearText: { fontSize: 12, color: '#6B7684', fontWeight: '600' },
  list: { maxHeight: 280, marginTop: 8 },
  listPad: { paddingBottom: 8 },
  row: {
    flexDirection: 'row',
    alignItems: 'baseline',
    paddingVertical: 10,
    paddingHorizontal: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#EEF0F4',
  },
  extra: { fontSize: 12, color: '#A2A8B4', width: 56 },
  name: { fontSize: 15, color: '#202632', fontWeight: '600' },
  centered: { paddingVertical: 24, alignItems: 'center' },
  error: { color: '#E84A4A', fontSize: 13, padding: 12, textAlign: 'center' },
  empty: { color: '#A2A8B4', fontSize: 13, padding: 16, textAlign: 'center' },
});
