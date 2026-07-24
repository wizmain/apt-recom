import React from 'react';
import {
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import appIcon from '../../assets/jiptori-app-icon-192.png';

export const Route = createRoute('/intro', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: IntroPage,
});

const highlights = [
  {
    label: '실거래 흐름',
    value: '최근 거래',
    description: '지역별 매매와 전월세 변화를 한 화면에서 확인해요.',
  },
  {
    label: '단지 탐색',
    value: '지역 검색',
    description: '시·군·구를 고르고 관심 단지 정보를 빠르게 찾아요.',
  },
  {
    label: '생활 판단',
    value: '추천 점수',
    description: '가격, 생활 편의, 안전 데이터를 함께 비교해요.',
  },
];

const steps = [
  '궁금한 지역을 선택해요',
  '최근 거래와 단지 목록을 확인해요',
  '조건에 맞는 아파트를 비교해요',
];

function IntroPage() {
  const navigation = Route.useNavigation();

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <View style={styles.hero}>
        <View style={styles.brandRow}>
          <Image
            source={appIcon}
            style={styles.appIcon}
          />
          <View>
            <Text style={styles.brand}>집토리</Text>
            <Text style={styles.brandMeta}>apt-recom for Toss Mini App</Text>
          </View>
        </View>

        <Text style={styles.title}>
          내 조건에 맞는 아파트를 더 빠르게 고르는 방법
        </Text>
        <Text style={styles.subtitle}>
          실거래가, 지역 흐름, 생활 점수를 연결해 복잡한 아파트 탐색을
          토스 안에서 간단하게 시작할 수 있어요.
        </Text>

        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.actionButton, styles.primaryButton]}
            onPress={() => navigation.navigate('/search', {})}
            activeOpacity={0.84}
          >
            <Text style={styles.primaryButtonText}>아파트 찾기</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionButton, styles.secondaryButton]}
            onPress={() => navigation.navigate('/trades', {})}
            activeOpacity={0.84}
          >
            <Text style={styles.secondaryButtonText}>거래 보기</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.previewWrap}>
        <View style={styles.phoneFrame}>
          <View style={styles.phoneHeader}>
            <View style={styles.homeIndicator} />
            <Text style={styles.phoneTitle}>추천 단지 리포트</Text>
          </View>
          <View style={styles.scorePanel}>
            <Text style={styles.scoreLabel}>생활 적합도</Text>
            <Text style={styles.scoreValue}>87</Text>
            <Text style={styles.scoreUnit}>점</Text>
          </View>
          <View style={styles.metricGrid}>
            <Metric label="교통" value="92" tone="blue" />
            <Metric label="학군" value="84" tone="green" />
            <Metric label="안전" value="89" tone="navy" />
          </View>
          <View style={styles.tradeCard}>
            <View>
              <Text style={styles.tradeLabel}>최근 실거래</Text>
              <Text style={styles.tradeName}>관심 지역 단지</Text>
            </View>
            <Text style={styles.tradePrice}>12.4억</Text>
          </View>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>집토리가 도와주는 것</Text>
        {highlights.map((item) => (
          <View key={item.label} style={styles.featureRow}>
            <View style={styles.featureBadge}>
              <Text style={styles.featureBadgeText}>{item.label}</Text>
            </View>
            <View style={styles.featureBody}>
              <Text style={styles.featureTitle}>{item.value}</Text>
              <Text style={styles.featureDescription}>{item.description}</Text>
            </View>
          </View>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>이렇게 사용해요</Text>
        <View style={styles.stepCard}>
          {steps.map((step, index) => (
            <View key={step} style={styles.stepRow}>
              <View style={styles.stepIndex}>
                <Text style={styles.stepIndexText}>{index + 1}</Text>
              </View>
              <Text style={styles.stepText}>{step}</Text>
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'blue' | 'green' | 'navy';
}) {
  return (
    <View style={[styles.metric, styles[`metric_${tone}`]]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F6F8FB' },
  content: { padding: 18, paddingBottom: 44 },
  hero: {
    backgroundColor: '#FFFFFF',
    borderRadius: 28,
    padding: 22,
    overflow: 'hidden',
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 24,
  },
  appIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
  },
  brand: {
    color: '#191F28',
    fontSize: 18,
    fontWeight: '800',
  },
  brandMeta: {
    color: '#6B7684',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 2,
  },
  title: {
    color: '#191F28',
    fontSize: 31,
    lineHeight: 39,
    fontWeight: '900',
  },
  subtitle: {
    color: '#4E5968',
    fontSize: 15,
    lineHeight: 23,
    marginTop: 14,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 24,
  },
  actionButton: {
    flex: 1,
    minHeight: 52,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButton: { backgroundColor: '#3182F6' },
  secondaryButton: {
    backgroundColor: '#EEF4FF',
    borderWidth: 1,
    borderColor: '#D7E6FF',
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
  },
  secondaryButtonText: {
    color: '#1B64DA',
    fontSize: 16,
    fontWeight: '800',
  },
  previewWrap: {
    alignItems: 'center',
    paddingVertical: 28,
  },
  phoneFrame: {
    width: '86%',
    maxWidth: 340,
    backgroundColor: '#111827',
    borderRadius: 34,
    padding: 14,
    shadowColor: '#1B64DA',
    shadowOpacity: 0.22,
    shadowRadius: 26,
    shadowOffset: { width: 0, height: 18 },
  },
  phoneHeader: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 16,
    alignItems: 'center',
  },
  homeIndicator: {
    width: 54,
    height: 5,
    borderRadius: 3,
    backgroundColor: '#D1D6DB',
    marginBottom: 14,
  },
  phoneTitle: {
    color: '#191F28',
    fontSize: 17,
    fontWeight: '800',
  },
  scorePanel: {
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    paddingVertical: 24,
    borderTopWidth: 1,
    borderColor: '#EEF1F5',
  },
  scoreLabel: {
    color: '#6B7684',
    fontSize: 12,
    fontWeight: '700',
  },
  scoreValue: {
    color: '#3182F6',
    fontSize: 52,
    fontWeight: '900',
    marginTop: 2,
  },
  scoreUnit: {
    color: '#4E5968',
    fontSize: 13,
    fontWeight: '700',
    marginTop: -4,
  },
  metricGrid: {
    flexDirection: 'row',
    gap: 8,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingBottom: 14,
  },
  metric: {
    flex: 1,
    borderRadius: 16,
    paddingVertical: 12,
    alignItems: 'center',
  },
  metric_blue: { backgroundColor: '#E8F3FF' },
  metric_green: { backgroundColor: '#EAF8F1' },
  metric_navy: { backgroundColor: '#EEF2F7' },
  metricLabel: {
    color: '#6B7684',
    fontSize: 11,
    fontWeight: '700',
  },
  metricValue: {
    color: '#191F28',
    fontSize: 19,
    fontWeight: '900',
    marginTop: 4,
  },
  tradeCard: {
    backgroundColor: '#FFFFFF',
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderColor: '#EEF1F5',
  },
  tradeLabel: {
    color: '#8B95A1',
    fontSize: 11,
    fontWeight: '700',
  },
  tradeName: {
    color: '#191F28',
    fontSize: 15,
    fontWeight: '800',
    marginTop: 4,
  },
  tradePrice: {
    color: '#3182F6',
    fontSize: 20,
    fontWeight: '900',
  },
  section: {
    marginTop: 8,
    marginBottom: 18,
  },
  sectionTitle: {
    color: '#191F28',
    fontSize: 20,
    fontWeight: '900',
    marginBottom: 12,
  },
  featureRow: {
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginBottom: 10,
  },
  featureBadge: {
    width: 74,
    minHeight: 48,
    borderRadius: 14,
    backgroundColor: '#F2F4F6',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  featureBadgeText: {
    color: '#4E5968',
    fontSize: 12,
    fontWeight: '800',
    textAlign: 'center',
  },
  featureBody: { flex: 1 },
  featureTitle: {
    color: '#191F28',
    fontSize: 16,
    fontWeight: '900',
  },
  featureDescription: {
    color: '#6B7684',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 4,
  },
  stepCard: {
    backgroundColor: '#191F28',
    borderRadius: 22,
    padding: 18,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 9,
  },
  stepIndex: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: '#3182F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  stepIndexText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '900',
  },
  stepText: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
});
