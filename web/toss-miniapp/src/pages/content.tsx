import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import { apiPaths } from '../shared/api/paths';
import type { ContentListItem } from '../types/content';
import { useApi } from '../hooks/useApi';
import ContentCard from '../components/ContentCard';

export const Route = createRoute('/content', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: ContentListPage,
});

function ContentListPage() {
  const navigation = Route.useNavigation();
  const list = useApi<ContentListItem[]>(apiPaths.content());

  const goArticle = (slug: string) =>
    navigation.navigate('/content-article', { slug });

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <Text style={styles.title}>숫자로 보는 집 이야기</Text>
      <Text style={styles.subtitle}>
        카드뉴스의 순위·가격이 어떻게 나왔는지 데이터 근거를 공개해요.
      </Text>
      {list.loading ? (
        <View style={styles.status}>
          <ActivityIndicator color="#3182F6" />
        </View>
      ) : list.error ? (
        <Text style={styles.empty}>콘텐츠를 불러오지 못했어요.</Text>
      ) : !list.data || list.data.length === 0 ? (
        <Text style={styles.empty}>아직 발행된 콘텐츠가 없어요.</Text>
      ) : (
        <View style={styles.listGap}>
          {list.data.map((item) => (
            <ContentCard
              key={item.slug}
              item={item}
              onPress={() => goArticle(item.slug)}
            />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F6F8FB' },
  content: { padding: 18, paddingBottom: 44 },
  title: { color: '#191F28', fontSize: 22, fontWeight: '900' },
  subtitle: { color: '#6B7684', fontSize: 14, marginTop: 4, marginBottom: 16 },
  status: { paddingVertical: 40, alignItems: 'center' },
  empty: {
    color: '#A2A8B4',
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 40,
  },
  listGap: { gap: 12 },
});
