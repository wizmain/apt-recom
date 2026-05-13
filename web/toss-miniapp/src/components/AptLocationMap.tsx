/**
 * 단지 위치 미니맵.
 *
 * apps-in-toss(Granite) 환경에서는 Kakao Maps JS SDK 를 직접 쓸 수 없으므로,
 * 백엔드가 서빙하는 카카오맵 HTML(GET /api/map)을 WebView 로 임베드한다.
 * 단일 핀 모드는 URL 쿼리(lat,lng,label,level,interactive)만으로 자체 렌더링되므로
 * RN ↔ WebView 메시지 브릿지가 필요 없다.
 *
 * 비드래그(interactive=0)로 띄워 부모 ScrollView 와의 제스처 충돌을 피한다.
 */

import React from 'react';
import { StyleSheet, View } from 'react-native';
import { WebView } from '@granite-js/native/react-native-webview';
import { buildApiUrl } from '../api/client';

interface Props {
  lat: number;
  lng: number;
  /** 핀에 표시할 단지명 (InfoWindow). */
  name?: string;
  /** 지도 높이(px). 기본 200. */
  height?: number;
}

const DEFAULT_HEIGHT = 200;
const DEFAULT_LEVEL = 4;

export default function AptLocationMap({
  lat,
  lng,
  name,
  height = DEFAULT_HEIGHT,
}: Props) {
  const uri = buildApiUrl('/api/map', {
    lat,
    lng,
    label: name,
    level: DEFAULT_LEVEL,
    interactive: 0,
  });

  return (
    <View style={[styles.container, { height }]}>
      <WebView
        source={{ uri }}
        style={styles.webview}
        // 정적 미니맵 — 페이지 스크롤만 살리고 지도 자체 스크롤은 막는다.
        scrollEnabled={false}
        nestedScrollEnabled={false}
        // iOS: 인라인으로 두지 않으면 전체화면 전환 시도가 발생할 수 있음.
        originWhitelist={['https://*']}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#EEF1F4',
  },
  webview: {
    flex: 1,
    backgroundColor: 'transparent',
  },
});
