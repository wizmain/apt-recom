import { ScrollView, View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import type { ScoredApartment } from '../types/apartment';

interface ResultCardsProps {
  results: ScoredApartment[];
  loading: boolean;
  compareList: string[];
  onPress: (apt: ScoredApartment) => void;
  onLongPress: (pnu: string) => void;
  onCompare: () => void;
}

function getRankBadge(rank: number): string {
  if (rank === 1) return '🏆';
  if (rank === 2) return '🥈';
  if (rank === 3) return '🥉';
  return `${rank}`;
}

export default function ResultCards({ results, loading, compareList, onPress, onLongPress, onCompare }: ResultCardsProps) {
  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="small" color="#3B82F6" />
        <Text style={styles.loadingText}>추천 아파트 분석 중...</Text>
      </View>
    );
  }

  if (results.length === 0) return null;

  return (
    <View style={styles.wrapper}>
      {/* 비교 바 */}
      {compareList.length > 0 && (
        <View style={styles.compareBar}>
          <Text style={styles.compareText}>
            비교 {compareList.length}/2 선택됨
          </Text>
          {compareList.length === 2 ? (
            <TouchableOpacity style={styles.compareBtn} onPress={onCompare}>
              <Text style={styles.compareBtnText}>비교하기</Text>
            </TouchableOpacity>
          ) : (
            <Text style={styles.compareHint}>카드를 길게 눌러 추가</Text>
          )}
        </View>
      )}

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.container}
        style={styles.scrollView}
      >
        {results.map((apt, i) => {
          const selected = compareList.includes(apt.pnu);
          return (
            <TouchableOpacity
              key={apt.pnu}
              style={[styles.card, selected && styles.cardSelected]}
              onPress={() => onPress(apt)}
              onLongPress={() => onLongPress(apt.pnu)}
              activeOpacity={0.8}
              delayLongPress={400}
            >
              {selected && (
                <View style={styles.checkMark}>
                  <Text style={styles.checkText}>✓</Text>
                </View>
              )}
              <View style={styles.rankRow}>
                <Text style={styles.rank}>{getRankBadge(i + 1)}</Text>
                <Text style={styles.score}>{apt.score.toFixed(1)}</Text>
              </View>
              <Text style={styles.name} numberOfLines={1}>{apt.bld_nm}</Text>
              <Text style={styles.hhld}>{apt.total_hhld_cnt}세대</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {},
  scrollView: { flexGrow: 0 },
  container: { paddingHorizontal: 12, paddingVertical: 8, gap: 8 },
  loadingContainer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, gap: 8 },
  loadingText: { fontSize: 13, color: '#6B7280' },
  card: {
    width: 130, backgroundColor: '#FFFFFF', borderRadius: 10, padding: 10,
    borderWidth: 1, borderColor: '#E5E7EB',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, shadowRadius: 3, elevation: 2,
  },
  cardSelected: { borderColor: '#2563EB', borderWidth: 2, backgroundColor: '#F0F7FF' },
  checkMark: {
    position: 'absolute', top: -6, right: -6, width: 18, height: 18,
    borderRadius: 9, backgroundColor: '#2563EB', alignItems: 'center', justifyContent: 'center',
    zIndex: 1,
  },
  checkText: { fontSize: 10, color: '#FFF', fontWeight: '700' },
  rankRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  rank: { fontSize: 16 },
  score: { fontSize: 15, fontWeight: '800', color: '#3B82F6' },
  name: { fontSize: 12, fontWeight: '600', color: '#111827', marginBottom: 1 },
  hhld: { fontSize: 10, color: '#9CA3AF' },

  // Compare bar
  compareBar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 8,
    backgroundColor: '#EFF6FF', borderTopWidth: 1, borderTopColor: '#BFDBFE',
  },
  compareText: { fontSize: 12, fontWeight: '600', color: '#2563EB' },
  compareHint: { fontSize: 11, color: '#93C5FD' },
  compareBtn: { backgroundColor: '#2563EB', borderRadius: 6, paddingHorizontal: 14, paddingVertical: 6 },
  compareBtnText: { fontSize: 12, fontWeight: '700', color: '#FFF' },
});
