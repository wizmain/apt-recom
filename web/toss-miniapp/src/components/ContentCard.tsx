import React from 'react';
import {
  Image,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type { ContentListItem } from '../types/content';

interface Props {
  item: ContentListItem;
  onPress: () => void;
}

/** 콘텐츠 카드 — 홈 미리보기와 목록 화면 공용. */
export default function ContentCard({ item, onPress }: Props) {
  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.8}>
      <Image
        source={{ uri: item.cover_image_url }}
        style={styles.cover}
        accessibilityLabel={item.cover_alt}
      />
      <View style={styles.body}>
        <Text style={styles.eyebrow}>{item.eyebrow}</Text>
        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.summary} numberOfLines={2}>
          {item.summary}
        </Text>
        <Text style={styles.meta}>기준일 {item.data_as_of}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    gap: 12,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: '#EEF1F4',
  },
  cover: {
    width: 84,
    height: 84,
    borderRadius: 12,
    backgroundColor: '#EEF1F4',
  },
  body: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#12B886', fontSize: 12, fontWeight: '700' },
  title: { color: '#191F28', fontSize: 15, fontWeight: '800', marginTop: 2 },
  summary: { color: '#6B7684', fontSize: 13, marginTop: 4 },
  meta: { color: '#A2A8B4', fontSize: 11, marginTop: 6 },
});
