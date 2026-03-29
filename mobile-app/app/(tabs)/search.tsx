import { useState, useCallback } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import type { Apartment } from '../../src/types/apartment';
import { api } from '../../src/services/api';

export default function SearchScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Apartment[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    try {
      setLoading(true);
      setSearched(true);
      const res = await api.get<Apartment[]>('/api/apartments/search', { params: { q } });
      setResults(res.data);
    } catch (err) {
      console.error('검색 실패:', err);
    } finally {
      setLoading(false);
    }
  }, [query]);

  const renderItem = useCallback(({ item }: { item: Apartment }) => (
    <TouchableOpacity style={styles.card} activeOpacity={0.7} onPress={() => router.push(`/detail/${item.pnu}`)}>
      <Text style={styles.name}>{item.bld_nm}</Text>
      <View style={styles.infoRow}>
        <Text style={styles.info}>{item.total_hhld_cnt}세대</Text>
      </View>
    </TouchableOpacity>
  ), [router]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <Text style={styles.title}>아파트 검색</Text>
      <View style={styles.searchRow}>
        <TextInput
          style={styles.input}
          value={query}
          onChangeText={setQuery}
          placeholder="지역명, 단지명으로 검색"
          placeholderTextColor="#9CA3AF"
          returnKeyType="search"
          onSubmitEditing={handleSearch}
        />
        <TouchableOpacity style={styles.btn} onPress={handleSearch}>
          <Text style={styles.btnText}>검색</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#3B82F6" />
        </View>
      ) : results.length > 0 ? (
        <FlatList
          data={results}
          keyExtractor={item => item.pnu}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
        />
      ) : searched ? (
        <View style={styles.center}>
          <Text style={styles.empty}>검색 결과가 없습니다</Text>
        </View>
      ) : (
        <View style={styles.center}>
          <Text style={styles.hint}>지역명 또는 단지명을 입력하세요</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF', paddingHorizontal: 16 },
  title: { fontSize: 22, fontWeight: '800', color: '#111827', marginBottom: 12 },
  searchRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  input: {
    flex: 1, height: 44, backgroundColor: '#F9FAFB', borderRadius: 10,
    paddingHorizontal: 14, fontSize: 14, borderWidth: 1, borderColor: '#E5E7EB', color: '#111827',
  },
  btn: { backgroundColor: '#3B82F6', borderRadius: 10, paddingHorizontal: 18, justifyContent: 'center' },
  btnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '600' },
  list: { paddingBottom: 20 },
  card: {
    backgroundColor: '#F9FAFB', borderRadius: 12, padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: '#E5E7EB',
  },
  name: { fontSize: 15, fontWeight: '600', color: '#111827', marginBottom: 4 },
  infoRow: { flexDirection: 'row', gap: 12 },
  info: { fontSize: 12, color: '#6B7280' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  empty: { fontSize: 14, color: '#9CA3AF' },
  hint: { fontSize: 14, color: '#D1D5DB' },
});
