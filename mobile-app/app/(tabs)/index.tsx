import { useState, useEffect, useCallback } from 'react';
import { View, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import KakaoMap, { type HighlightApt } from '../../src/components/KakaoMap';
import { on } from '../../src/services/events';
import SearchBar from '../../src/components/SearchBar';
import NudgeChips from '../../src/components/NudgeChips';
import ResultCards from '../../src/components/ResultCards';
import FilterSheet from '../../src/components/FilterSheet';
import WeightSheet from '../../src/components/WeightSheet';
import { useApartments } from '../../src/hooks/useApartments';
import { useNudge } from '../../src/hooks/useNudge';
import type { ApartmentFilters } from '../../src/types/apartment';

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { apartments, keywords, filters, addKeyword, removeKeyword, onBoundsChange, applyFilters, clearFilters } = useApartments();
  const { results, loading: nudgeLoading, scoreApartments, fetchWeights, defaultWeights } = useNudge();
  const [selectedNudges, setSelectedNudges] = useState<string[]>([]);
  const [shouldFocus, setShouldFocus] = useState(false);
  const [filterVisible, setFilterVisible] = useState(false);
  const [weightVisible, setWeightVisible] = useState(false);
  const [customWeights, setCustomWeights] = useState<Record<string, number> | null>(null);
  const [compareList, setCompareList] = useState<string[]>([]);
  const [chatHighlights, setChatHighlights] = useState<HighlightApt[]>([]);

  const activeFilterCount = Object.values(filters).filter(v => v !== undefined).length;
  const hasCustomWeights = customWeights !== null;

  useEffect(() => {
    fetchWeights();
  }, [fetchWeights]);

  // 챗봇에서 추천 아파트를 지도에 표시
  useEffect(() => {
    const unsub = on('chatHighlight', (data) => {
      const apts = data.apartments as HighlightApt[];
      setChatHighlights(apts);
    });
    return unsub;
  }, []);

  useEffect(() => {
    if (selectedNudges.length > 0 && keywords.length > 0) {
      // customWeights가 있으면 모든 넛지에 동일 적용, 없으면 기본 가중치
      let w: Record<string, Record<string, number>> | null = null;
      if (customWeights) {
        // 커스텀 가중치를 각 넛지에 동일하게 적용
        w = {};
        for (const nid of selectedNudges) {
          w[nid] = customWeights;
        }
      } else if (Object.keys(defaultWeights).length > 0) {
        w = defaultWeights;
      }
      scoreApartments(selectedNudges, w, 10, undefined, keywords, filters);
    } else if (selectedNudges.length === 0) {
      scoreApartments([], null, 10);
    }
  }, [selectedNudges, keywords, scoreApartments, defaultWeights, filters, customWeights]);

  const handleAddKeyword = useCallback((kw: string) => {
    addKeyword(kw);
    setChatHighlights([]); // 기존 챗봇 하이라이트 마커 제거
    setShouldFocus(true);
    setTimeout(() => setShouldFocus(false), 1000);
  }, [addKeyword]);

  const toggleNudge = useCallback((nudgeId: string) => {
    setSelectedNudges(prev =>
      prev.includes(nudgeId) ? prev.filter(n => n !== nudgeId) : [...prev, nudgeId]
    );
  }, []);

  const handleApartmentPress = useCallback((pnu: string) => {
    router.push(`/detail/${pnu}`);
  }, [router]);

  const handleApplyFilters = useCallback((f: ApartmentFilters) => {
    applyFilters(f);
  }, [applyFilters]);

  const handleApplyWeights = useCallback((w: Record<string, number>) => {
    setCustomWeights(w);
  }, []);

  const handleCompareLongPress = useCallback((pnu: string) => {
    setCompareList(prev => {
      if (prev.includes(pnu)) return prev.filter(p => p !== pnu);
      if (prev.length >= 2) return prev;
      return [...prev, pnu];
    });
  }, []);

  const handleCompare = useCallback(() => {
    if (compareList.length === 2) {
      router.push(`/compare?pnu1=${compareList[0]}&pnu2=${compareList[1]}`);
      setCompareList([]);
    }
  }, [compareList, router]);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <SearchBar
        keywords={keywords}
        onAddKeyword={handleAddKeyword}
        onRemoveKeyword={removeKeyword}
      />

      {/* 넛지 + 가중치 + 필터 버튼 */}
      <View style={styles.controlRow}>
        <View style={styles.nudgeArea}>
          <NudgeChips
            selected={selectedNudges}
            onToggle={toggleNudge}
            disabled={keywords.length === 0}
          />
        </View>
        <View style={styles.btnGroup}>
          {/* 가중치 버튼 — 넛지 선택 시에만 표시 */}
          {selectedNudges.length > 0 && (
            <TouchableOpacity
              style={[styles.ctrlBtn, hasCustomWeights && styles.ctrlBtnActive]}
              onPress={() => setWeightVisible(true)}
            >
              <Text style={[styles.ctrlBtnText, hasCustomWeights && styles.ctrlBtnTextActive]}>
                가중치
              </Text>
            </TouchableOpacity>
          )}
          {/* 필터 버튼 */}
          <TouchableOpacity
            style={[styles.ctrlBtn, activeFilterCount > 0 && styles.ctrlBtnActive]}
            onPress={() => setFilterVisible(true)}
          >
            <Text style={[styles.ctrlBtnText, activeFilterCount > 0 && styles.ctrlBtnTextActive]}>
              필터
            </Text>
            {activeFilterCount > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{activeFilterCount}</Text>
              </View>
            )}
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.mapContainer}>
        <KakaoMap
          apartments={apartments}
          scoredApartments={results}
          highlightApts={chatHighlights}
          focusOnApartments={shouldFocus}
          onApartmentPress={handleApartmentPress}
          onBoundsChange={onBoundsChange}
        />
      </View>

      <ResultCards
        results={results}
        loading={nudgeLoading}
        compareList={compareList}
        onPress={(apt) => handleApartmentPress(apt.pnu)}
        onLongPress={handleCompareLongPress}
        onCompare={handleCompare}
      />

      <FilterSheet
        visible={filterVisible}
        filters={filters}
        onApply={handleApplyFilters}
        onClear={clearFilters}
        onClose={() => setFilterVisible(false)}
      />

      <WeightSheet
        visible={weightVisible}
        defaultWeights={defaultWeights}
        selectedNudges={selectedNudges}
        customWeights={customWeights}
        onApply={handleApplyWeights}
        onClose={() => setWeightVisible(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  controlRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  nudgeArea: {
    flex: 1,
  },
  btnGroup: {
    flexDirection: 'row',
    gap: 6,
    marginRight: 12,
  },
  ctrlBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E5E7EB',
    backgroundColor: '#F9FAFB',
  },
  ctrlBtnActive: {
    backgroundColor: '#EFF6FF',
    borderColor: '#2563EB',
  },
  ctrlBtnText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#6B7280',
  },
  ctrlBtnTextActive: {
    color: '#2563EB',
  },
  badge: {
    backgroundColor: '#2563EB',
    borderRadius: 8,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  mapContainer: {
    flex: 1,
    minHeight: 300,
  },
});
