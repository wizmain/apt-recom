import { ScrollView, TouchableOpacity, Text, StyleSheet } from 'react-native';

const NUDGES = [
  { id: 'cost', label: '가성비', emoji: '💰' },
  { id: 'pet', label: '반려동물', emoji: '🐾' },
  { id: 'commute', label: '출퇴근', emoji: '🚇' },
  { id: 'newlywed', label: '신혼육아', emoji: '👶' },
  { id: 'education', label: '학군', emoji: '📚' },
  { id: 'senior', label: '시니어', emoji: '🏥' },
  { id: 'invest', label: '투자', emoji: '📈' },
  { id: 'nature', label: '자연친화', emoji: '🌿' },
  { id: 'safety', label: '안전', emoji: '🛡️' },
];

interface NudgeChipsProps {
  selected: string[];
  onToggle: (nudgeId: string) => void;
  disabled?: boolean;
}

export default function NudgeChips({ selected, onToggle, disabled }: NudgeChipsProps) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.container}
      style={styles.scrollView}
    >
      {NUDGES.map(nudge => {
        const active = selected.includes(nudge.id);
        return (
          <TouchableOpacity
            key={nudge.id}
            style={[styles.chip, active && styles.chipActive, disabled && styles.chipDisabled]}
            onPress={() => !disabled && onToggle(nudge.id)}
            activeOpacity={0.7}
          >
            <Text style={styles.emoji}>{nudge.emoji}</Text>
            <Text style={[styles.label, active && styles.labelActive]}>
              {nudge.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flexGrow: 0,
  },
  container: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
    alignItems: 'center',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#F3F4F6',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    gap: 4,
  },
  chipActive: {
    backgroundColor: '#EFF6FF',
    borderColor: '#3B82F6',
  },
  chipDisabled: {
    opacity: 0.5,
  },
  emoji: {
    fontSize: 14,
  },
  label: {
    fontSize: 13,
    color: '#6B7280',
    fontWeight: '500',
  },
  labelActive: {
    color: '#3B82F6',
    fontWeight: '700',
  },
});
