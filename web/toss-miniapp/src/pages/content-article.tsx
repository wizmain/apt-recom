import React, { useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from '@granite-js/native/react-native-webview';
import { createRoute } from '@granite-js/react-native';
import { buildSiteUrl } from '../api/client';

// 원본(lib/instagramContent SLUG_PATTERN)과 동일 규칙으로 검증.
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
// 임베드 상세만 허용 — 그 외 origin/경로로의 이동은 차단(웹 이탈 방지).
const ALLOWED_PREFIX = 'https://apt-recom.kr/content/';

export const Route = createRoute('/content-article', {
  // slug 를 raw 문자열로 유지 (Granite 기본 JSON.parse 회피 — apt.tsx 패턴).
  parserParams: (params) => params,
  validateParams: (params: Readonly<object | undefined>) => {
    const p = params as { slug?: unknown } | undefined;
    const slug =
      typeof p?.slug === 'string' && SLUG_PATTERN.test(p.slug) ? p.slug : '';
    return { slug };
  },
  component: ContentArticlePage,
});

function ContentArticlePage() {
  const { slug } = Route.useParams();
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [reloadKey, setReloadKey] = useState(0);

  if (!slug) {
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>콘텐츠를 찾을 수 없어요.</Text>
      </View>
    );
  }

  const uri = buildSiteUrl(`/content/${slug}/embed`);
  const retry = () => {
    setStatus('loading');
    setReloadKey((k) => k + 1);
  };

  return (
    <View style={styles.root}>
      <WebView
        key={reloadKey}
        source={{ uri }}
        style={styles.webview}
        originWhitelist={['https://*']}
        onLoadStart={() => setStatus('loading')}
        onLoadEnd={() => setStatus((s) => (s === 'error' ? s : 'ok'))}
        onError={() => setStatus('error')}
        onHttpError={() => setStatus('error')}
        onShouldStartLoadWithRequest={(req) =>
          req.url.startsWith(ALLOWED_PREFIX)
        }
      />
      {status === 'loading' && (
        <View style={styles.overlay} pointerEvents="none">
          <ActivityIndicator color="#3182F6" />
        </View>
      )}
      {status === 'error' && (
        <View style={styles.overlay}>
          <Text style={styles.empty}>불러오지 못했어요.</Text>
          <TouchableOpacity style={styles.retry} onPress={retry}>
            <Text style={styles.retryText}>다시 시도</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  webview: { flex: 1, backgroundColor: 'transparent' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
    gap: 12,
  },
  empty: { color: '#A2A8B4', fontSize: 14 },
  retry: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: '#3182F6',
  },
  retryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
});
