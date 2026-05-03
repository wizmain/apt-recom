/**
 * 단일 거래 행 카드. trades / recent-trades / index 의 최근 거래 등에서 공유.
 *
 * pnu 매핑이 있으면 TouchableOpacity 로 감싸 onPress 노출.
 * pnu 없으면 정적 View — 단지 상세로 이동할 수 없는 거래(rent 또는 미매핑).
 */

import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { DashboardRecentTrade } from '../shared/types/dashboard';
import { formatPrice } from '../lib/format';

interface Props {
  item: DashboardRecentTrade;
  onPress?: (pnu: string, name: string) => void;
  /** 시군구 라벨을 메타에 표시 (홈 등 다지역 목록). 단일 지역 화면에선 false. */
  showSigungu?: boolean;
}

export default function TradeCard({ item, onPress, showSigungu = true }: Props) {
  const Wrap = item.pnu && onPress ? TouchableOpacity : View;
  const tappable = !!(item.pnu && onPress);
  const priceLabel = priceText(item);
  const meta = [
    showSigungu ? item.sigungu : null,
    item.area ? `${item.area.toFixed(0)}㎡` : null,
    item.floor != null ? `${item.floor}층` : null,
    item.date,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Wrap
      style={styles.card}
      {...(tappable
        ? {
            onPress: () => onPress!(item.pnu as string, item.apt_nm),
            activeOpacity: 0.7,
          }
        : {})}
    >
      <View style={styles.top}>
        <Text style={styles.name} numberOfLines={1}>
          {item.apt_nm}
        </Text>
        <Text style={styles.price}>{priceLabel}</Text>
      </View>
      <Text style={styles.meta}>{meta}</Text>
    </Wrap>
  );
}

function priceText(item: DashboardRecentTrade): string {
  if (item.price) return `${formatPrice(item.price)}만원`;
  if (item.deposit) {
    const monthly = item.monthly_rent ?? 0;
    return monthly
      ? `${formatPrice(item.deposit)}/${monthly.toLocaleString()}`
      : `${formatPrice(item.deposit)}만원`;
  }
  return '-';
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
  },
  top: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  name: {
    fontSize: 15,
    fontWeight: '700',
    color: '#202632',
    flex: 1,
    marginRight: 12,
  },
  price: {
    fontSize: 16,
    color: '#3182F6',
    fontWeight: '800',
  },
  meta: { fontSize: 12, color: '#6B7684', marginTop: 4 },
});
