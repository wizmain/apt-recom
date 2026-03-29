import { useState, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, Modal,
  Pressable, StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Slider from '../../src/components/Slider';

interface WeightSheetProps {
  visible: boolean;
  defaultWeights: Record<string, Record<string, number>>;
  selectedNudges: string[];
  customWeights: Record<string, number> | null;
  onApply: (weights: Record<string, number>) => void;
  onClose: () => void;
}

const FACILITY_LABELS: Record<string, string> = {
  subway: '지하철역', bus: '버스정류장', bus_stop: '버스정류장',
  school: '학교', kindergarten: '유치원', hospital: '병원',
  park: '공원', mart: '대형마트', convenience_store: '편의점',
  library: '도서관', pharmacy: '약국', pet_facility: '반려동물시설',
  animal_hospital: '동물병원', police: '경찰서', fire_station: '소방서',
  cctv: 'CCTV', _price: '가격 경쟁력', _jeonse: '전세가율',
  _safety: '안전점수', _crime: '범죄안전',
};

const NUDGE_LABELS: Record<string, string> = {
  cost: '가성비', pet: '반려동물', commute: '출퇴근', newlywed: '신혼육아',
  education: '학군', senior: '시니어', investment: '투자', nature: '자연친화', safety: '안전',
};

export default function WeightSheet({ visible, defaultWeights, selectedNudges, customWeights, onApply, onClose }: WeightSheetProps) {
  const insets = useSafeAreaInsets();

  // 선택된 넛지들의 가중치를 병합 (같은 키는 max)
  const mergedDefaults = useMemo(() => {
    const merged: Record<string, number> = {};
    for (const nid of selectedNudges) {
      const ws = defaultWeights[nid];
      if (!ws) continue;
      for (const [k, v] of Object.entries(ws)) {
        merged[k] = Math.max(merged[k] ?? 0, v);
      }
    }
    return merged;
  }, [defaultWeights, selectedNudges]);

  const [weights, setWeights] = useState<Record<string, number>>({});

  useEffect(() => {
    if (visible) {
      setWeights(customWeights ?? { ...mergedDefaults });
    }
  }, [visible, mergedDefaults, customWeights]);

  const totalWeight = Object.values(weights).reduce((s, v) => s + v, 0);
  const entries = Object.entries(weights);

  const handleChange = (key: string, value: number) => {
    setWeights(prev => ({ ...prev, [key]: value * 0.01 }));
  };

  const handleReset = () => {
    setWeights({ ...mergedDefaults });
  };

  const handleApply = () => {
    onApply(weights);
    onClose();
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <Pressable style={s.backdrop} onPress={onClose} />
      <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        {/* Handle */}
        <View style={s.handleRow}><View style={s.handle} /></View>

        {/* Header */}
        <View style={s.header}>
          <View>
            <Text style={s.headerTitle}>세부 가중치 설정</Text>
            {selectedNudges.length > 0 && (
              <View style={s.nudgeTags}>
                {selectedNudges.map(nid => (
                  <View key={nid} style={s.nudgeTag}>
                    <Text style={s.nudgeTagText}>{NUDGE_LABELS[nid] || nid}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
          <TouchableOpacity onPress={onClose} hitSlop={12}>
            <Text style={s.closeBtn}>닫기</Text>
          </TouchableOpacity>
        </View>

        {/* Sliders */}
        <ScrollView style={s.body} showsVerticalScrollIndicator={false}>
          {entries.length > 0 ? (
            entries.map(([key, value]) => {
              const pct = totalWeight > 0 ? ((value / totalWeight) * 100).toFixed(0) : '0';
              const sliderVal = Math.round(value * 100);
              return (
                <View key={key} style={s.sliderRow}>
                  <View style={s.sliderHeader}>
                    <Text style={s.sliderLabel}>{FACILITY_LABELS[key] || key}</Text>
                    <Text style={s.sliderPct}>{pct}%</Text>
                  </View>
                  <Slider
                    value={sliderVal}
                    min={0}
                    max={100}
                    onChange={(v) => handleChange(key, v)}
                  />
                </View>
              );
            })
          ) : (
            <Text style={s.emptyText}>라이프 항목을 선택하면 가중치가 표시됩니다.</Text>
          )}
          <View style={{ height: 8 }} />
        </ScrollView>

        {/* Footer */}
        <View style={s.footer}>
          <TouchableOpacity style={s.resetBtn} onPress={handleReset}>
            <Text style={s.resetBtnText}>초기화</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.applyBtn} onPress={handleApply}>
            <Text style={s.applyBtnText}>적용</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const C = { accent: '#2563EB', border: '#ECEEF1' };

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.25)' },
  sheet: { backgroundColor: '#FFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '70%' },
  handleRow: { alignItems: 'center', paddingTop: 10, paddingBottom: 4 },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: '#D1D5DB' },

  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border },
  headerTitle: { fontSize: 16, fontWeight: '700', color: '#111827' },
  nudgeTags: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 },
  nudgeTag: { backgroundColor: '#EFF6FF', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  nudgeTagText: { fontSize: 10, fontWeight: '600', color: C.accent },
  closeBtn: { fontSize: 14, color: '#9CA3AF', fontWeight: '500' },

  body: { paddingHorizontal: 20, paddingTop: 12 },

  sliderRow: { marginBottom: 16 },
  sliderHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  sliderLabel: { fontSize: 13, color: '#374151', fontWeight: '500' },
  sliderPct: { fontSize: 12, fontWeight: '700', color: C.accent },

  emptyText: { fontSize: 13, color: '#9CA3AF', textAlign: 'center', paddingVertical: 40 },

  footer: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.border },
  resetBtn: { flex: 1, paddingVertical: 13, borderRadius: 10, borderWidth: 1, borderColor: '#D1D5DB', alignItems: 'center' },
  resetBtnText: { fontSize: 14, color: '#6B7280', fontWeight: '600' },
  applyBtn: { flex: 2, paddingVertical: 13, borderRadius: 10, backgroundColor: C.accent, alignItems: 'center' },
  applyBtnText: { fontSize: 14, color: '#FFF', fontWeight: '700' },
});
