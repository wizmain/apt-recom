import { View, Text, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <Text style={styles.title}>설정</Text>
      <View style={styles.section}>
        <Text style={styles.label}>앱 버전</Text>
        <Text style={styles.value}>1.0.0</Text>
      </View>
      <View style={styles.section}>
        <Text style={styles.label}>서비스</Text>
        <Text style={styles.value}>집토리 - 라이프스타일 기반 아파트 추천</Text>
      </View>
      <View style={styles.section}>
        <Text style={styles.label}>지역</Text>
        <Text style={styles.value}>서울 · 경기 · 인천</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF', paddingHorizontal: 16 },
  title: { fontSize: 22, fontWeight: '800', color: '#111827', marginBottom: 20 },
  section: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#F3F4F6',
  },
  label: { fontSize: 15, color: '#374151', fontWeight: '500' },
  value: { fontSize: 14, color: '#9CA3AF' },
});
