import { useRef, useCallback, useState, useEffect } from 'react';
import { StyleSheet, View, Text, ActivityIndicator } from 'react-native';
import { WebView } from 'react-native-webview';
import type { Apartment, ScoredApartment } from '../types/apartment';
import { API_BASE } from '../services/api';

export interface HighlightApt {
  pnu: string; bld_nm: string; lat: number; lng: number; score: number;
}

interface KakaoMapProps {
  apartments?: Apartment[];
  scoredApartments?: ScoredApartment[];
  highlightApts?: HighlightApt[];
  focusOnApartments?: boolean;
  onApartmentPress?: (pnu: string) => void;
  onBoundsChange?: (bounds: { sw: { lat: number; lng: number }; ne: { lat: number; lng: number } }) => void;
}

export default function KakaoMap({ apartments, scoredApartments, highlightApts, focusOnApartments, onApartmentPress, onBoundsChange }: KakaoMapProps) {
  const webViewRef = useRef<WebView>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onMessage = useCallback((event: { nativeEvent: { data: string } }) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.type === 'mapReady') setMapLoaded(true);
      if (data.type === 'error') setError(data.message);
      if (data.type === 'aptClick' && onApartmentPress) onApartmentPress(data.pnu);
      if (data.type === 'boundsChanged' && onBoundsChange) onBoundsChange({ sw: data.sw, ne: data.ne });
    } catch {}
  }, [onApartmentPress, onBoundsChange]);

  // 일반 아파트 마커
  const basicMarkers = (apartments || []).map(apt => ({
    pnu: apt.pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm,
  }));
  const basicJson = JSON.stringify(basicMarkers);
  const prevBasicJson = useRef('');
  const prevFocus = useRef(false);
  useEffect(() => {
    if (mapLoaded && (basicJson !== prevBasicJson.current || focusOnApartments !== prevFocus.current)) {
      prevBasicJson.current = basicJson;
      prevFocus.current = !!focusOnApartments;
      webViewRef.current?.postMessage(JSON.stringify({
        type: 'updateBasicMarkers',
        markers: basicMarkers,
        focus: !!focusOnApartments,
      }));
    }
  }, [mapLoaded, basicJson, basicMarkers, focusOnApartments]);

  // 스코어링 마커
  const scoredMarkers = (scoredApartments || []).map((apt, i) => ({
    pnu: apt.pnu, lat: apt.lat, lng: apt.lng,
    name: apt.bld_nm, score: apt.score, rank: i + 1,
  }));
  const scoredJson = JSON.stringify(scoredMarkers);
  const prevScoredJson = useRef('');
  useEffect(() => {
    if (mapLoaded && scoredJson !== prevScoredJson.current) {
      prevScoredJson.current = scoredJson;
      if (scoredMarkers.length > 0) {
        webViewRef.current?.postMessage(JSON.stringify({ type: 'updateScoredMarkers', markers: scoredMarkers }));
      } else {
        webViewRef.current?.postMessage(JSON.stringify({ type: 'clearScoredMarkers' }));
      }
    }
  }, [mapLoaded, scoredJson, scoredMarkers]);

  // 챗봇 하이라이트 마커
  const hlMarkers = (highlightApts || []).map(apt => ({
    pnu: apt.pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm, score: apt.score,
  }));
  const hlJson = JSON.stringify(hlMarkers);
  const prevHlJson = useRef('');
  useEffect(() => {
    if (mapLoaded && hlJson !== prevHlJson.current) {
      prevHlJson.current = hlJson;
      if (hlMarkers.length > 0) {
        webViewRef.current?.postMessage(JSON.stringify({ type: 'updateHighlightMarkers', markers: hlMarkers }));
      } else {
        webViewRef.current?.postMessage(JSON.stringify({ type: 'clearHighlightMarkers' }));
      }
    }
  }, [mapLoaded, hlJson, hlMarkers]);

  return (
    <View style={styles.container}>
      <WebView
        ref={webViewRef}
        source={{ uri: `${API_BASE}/api/map` }}
        style={styles.map}
        onMessage={onMessage}
        javaScriptEnabled
        domStorageEnabled
        originWhitelist={['*']}
        onError={(e) => setError(e.nativeEvent.description)}
      />
      {!mapLoaded && !error && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#3B82F6" />
          <Text style={styles.loadingText}>지도 로딩 중...</Text>
        </View>
      )}
      {error && (
        <View style={styles.loadingOverlay}>
          <Text style={styles.errorText}>지도 로딩 실패</Text>
          <Text style={styles.errorDetail}>{error}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  map: { flex: 1 },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F9FAFB',
  },
  loadingText: { marginTop: 8, fontSize: 14, color: '#6B7280' },
  errorText: { fontSize: 16, fontWeight: '600', color: '#EF4444' },
  errorDetail: { fontSize: 12, color: '#9CA3AF', marginTop: 4, textAlign: 'center', paddingHorizontal: 20 },
});
