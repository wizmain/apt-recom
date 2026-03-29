import { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, Modal,
  StyleSheet, Pressable,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { ApartmentFilters } from '../types/apartment';

interface FilterSheetProps {
  visible: boolean;
  filters: ApartmentFilters;
  onApply: (filters: ApartmentFilters) => void;
  onClear: () => void;
  onClose: () => void;
}

const AREA_OPTIONS = [
  { label: '전체', min: undefined, max: undefined },
  { label: '~40㎡', min: undefined, max: 40 },
  { label: '40~60㎡', min: 40, max: 60 },
  { label: '60~85㎡', min: 60, max: 85 },
  { label: '85~115㎡', min: 85, max: 115 },
  { label: '115㎡~', min: 115, max: undefined },
] as const;

const PRICE_OPTIONS = [
  { label: '전체', min: undefined, max: undefined },
  { label: '~3억', min: undefined, max: 30000 },
  { label: '3~5억', min: 30000, max: 50000 },
  { label: '5~7억', min: 50000, max: 70000 },
  { label: '7~10억', min: 70000, max: 100000 },
  { label: '10~15억', min: 100000, max: 150000 },
  { label: '15억~', min: 150000, max: undefined },
] as const;

const FLOOR_OPTIONS = [
  { label: '전체', value: undefined },
  { label: '5층+', value: 5 },
  { label: '10층+', value: 10 },
  { label: '15층+', value: 15 },
  { label: '20층+', value: 20 },
  { label: '30층+', value: 30 },
] as const;

const HHLD_OPTIONS = [
  { label: '전체', min: undefined, max: undefined },
  { label: '~100', min: undefined, max: 100 },
  { label: '100~300', min: 100, max: 300 },
  { label: '300~500', min: 300, max: 500 },
  { label: '500~1000', min: 500, max: 1000 },
  { label: '1000~', min: 1000, max: undefined },
] as const;

const YEAR_OPTIONS = [
  { label: '전체', after: undefined, before: undefined },
  { label: '5년 이내', after: 2021, before: undefined },
  { label: '10년 이내', after: 2016, before: undefined },
  { label: '15년 이내', after: 2011, before: undefined },
  { label: '20년+', after: undefined, before: 2006 },
] as const;

export default function FilterSheet({ visible, filters, onApply, onClear, onClose }: FilterSheetProps) {
  const insets = useSafeAreaInsets();
  const [local, setLocal] = useState<ApartmentFilters>({});

  useEffect(() => {
    if (visible) setLocal(filters);
  }, [visible, filters]);

  const activeCount = Object.values(local).filter(v => v !== undefined).length;

  const handleApply = () => {
    onApply(local);
    onClose();
  };

  const handleClear = () => {
    setLocal({});
    onClear();
    onClose();
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      {/* Backdrop */}
      <Pressable style={s.backdrop} onPress={onClose} />

      {/* Sheet */}
      <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        {/* Handle */}
        <View style={s.handleRow}>
          <View style={s.handle} />
        </View>

        {/* Header */}
        <View style={s.header}>
          <View style={s.headerLeft}>
            <Text style={s.headerTitle}>필터</Text>
            {activeCount > 0 && (
              <View style={s.badge}>
                <Text style={s.badgeText}>{activeCount}</Text>
              </View>
            )}
          </View>
          <TouchableOpacity onPress={onClose} hitSlop={12}>
            <Text style={s.closeBtn}>닫기</Text>
          </TouchableOpacity>
        </View>

        {/* Filters */}
        <ScrollView style={s.body} showsVerticalScrollIndicator={false}>
          <Section title="면적">
            <ChipRow
              options={AREA_OPTIONS.map(o => o.label)}
              selected={AREA_OPTIONS.findIndex(o => o.min === local.minArea && o.max === local.maxArea)}
              onChange={i => {
                const o = AREA_OPTIONS[i];
                setLocal(p => ({ ...p, minArea: o.min, maxArea: o.max }));
              }}
            />
          </Section>

          <Section title="매매가">
            <ChipRow
              options={PRICE_OPTIONS.map(o => o.label)}
              selected={PRICE_OPTIONS.findIndex(o => o.min === local.minPrice && o.max === local.maxPrice)}
              onChange={i => {
                const o = PRICE_OPTIONS[i];
                setLocal(p => ({ ...p, minPrice: o.min, maxPrice: o.max }));
              }}
            />
          </Section>

          <Section title="최고층">
            <ChipRow
              options={FLOOR_OPTIONS.map(o => o.label)}
              selected={FLOOR_OPTIONS.findIndex(o => o.value === local.minFloor)}
              onChange={i => setLocal(p => ({ ...p, minFloor: FLOOR_OPTIONS[i].value }))}
            />
          </Section>

          <Section title="세대수">
            <ChipRow
              options={HHLD_OPTIONS.map(o => o.label)}
              selected={HHLD_OPTIONS.findIndex(o => o.min === local.minHhld && o.max === local.maxHhld)}
              onChange={i => {
                const o = HHLD_OPTIONS[i];
                setLocal(p => ({ ...p, minHhld: o.min, maxHhld: o.max }));
              }}
            />
          </Section>

          <Section title="준공연도">
            <ChipRow
              options={YEAR_OPTIONS.map(o => o.label)}
              selected={YEAR_OPTIONS.findIndex(o => o.after === local.builtAfter && o.before === local.builtBefore)}
              onChange={i => {
                const o = YEAR_OPTIONS[i];
                setLocal(p => ({ ...p, builtAfter: o.after, builtBefore: o.before }));
              }}
            />
          </Section>

          <View style={{ height: 8 }} />
        </ScrollView>

        {/* Footer */}
        <View style={s.footer}>
          <TouchableOpacity style={s.clearBtn} onPress={handleClear}>
            <Text style={s.clearBtnText}>초기화</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.applyBtn} onPress={handleApply}>
            <Text style={s.applyBtnText}>적용하기</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={s.section}>
      <Text style={s.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function ChipRow({ options, selected, onChange }: { options: string[]; selected: number; onChange: (i: number) => void }) {
  return (
    <View style={s.chipRow}>
      {options.map((label, i) => {
        const active = i === selected;
        return (
          <TouchableOpacity
            key={label}
            style={[s.chip, active && s.chipActive]}
            onPress={() => onChange(i)}
            activeOpacity={0.7}
          >
            <Text style={[s.chipText, active && s.chipTextActive]}>{label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const C = { accent: '#2563EB', bg: '#FFFFFF', border: '#ECEEF1', text1: '#111827', text2: '#6B7280', text3: '#9CA3AF' };

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.25)' },
  sheet: { backgroundColor: C.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '75%' },
  handleRow: { alignItems: 'center', paddingTop: 10, paddingBottom: 4 },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: '#D1D5DB' },

  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { fontSize: 16, fontWeight: '700', color: C.text1 },
  badge: { backgroundColor: C.accent, borderRadius: 10, paddingHorizontal: 7, paddingVertical: 1 },
  badgeText: { fontSize: 11, fontWeight: '700', color: '#FFF' },
  closeBtn: { fontSize: 14, color: C.text3, fontWeight: '500' },

  body: { paddingHorizontal: 20 },

  section: { marginTop: 18 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: C.text1, marginBottom: 10, letterSpacing: -0.2 },

  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: '#F3F4F6', borderWidth: 1, borderColor: C.border },
  chipActive: { backgroundColor: '#EFF6FF', borderColor: C.accent },
  chipText: { fontSize: 13, color: C.text2, fontWeight: '500' },
  chipTextActive: { color: C.accent, fontWeight: '700' },

  footer: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.border },
  clearBtn: { flex: 1, paddingVertical: 13, borderRadius: 10, borderWidth: 1, borderColor: '#D1D5DB', alignItems: 'center' },
  clearBtnText: { fontSize: 14, color: C.text2, fontWeight: '600' },
  applyBtn: { flex: 2, paddingVertical: 13, borderRadius: 10, backgroundColor: C.accent, alignItems: 'center' },
  applyBtnText: { fontSize: 14, color: '#FFF', fontWeight: '700' },
});
