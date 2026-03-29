import { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, StyleSheet, ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useChat, type ChatMessage, type ApartmentCard } from '../../src/hooks/useChat';
import MarkdownText from '../../src/components/MarkdownText';
import { emit } from '../../src/services/events';

const FEEDBACK_TAGS: { id: string; label: string }[] = [
  { id: 'inaccurate', label: '정보 부정확' },
  { id: 'too_long', label: '너무 길어요' },
  { id: 'not_relevant', label: '원하는 답이 아님' },
  { id: 'score_wrong', label: '점수가 이상해요' },
  { id: 'missing_info', label: '정보가 부족해요' },
  { id: 'formatting', label: '읽기 어려워요' },
];

/* ── 피드백 바 ── */
function FeedbackBar({ onSubmit }: { onSubmit: (rating: 1 | -1, tags: string[], comment: string) => void }) {
  const [state, setState] = useState<'none' | 'liked' | 'tagging' | 'disliked'>('none');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [comment, setComment] = useState('');

  if (state === 'liked') {
    return <Text style={s.fbConfirm}>감사합니다!</Text>;
  }
  if (state === 'disliked') {
    return <Text style={s.fbConfirm}>피드백 감사합니다</Text>;
  }
  if (state === 'tagging') {
    return (
      <View style={s.fbTagging}>
        <Text style={s.fbTagTitle}>어떤 점이 아쉬웠나요?</Text>
        <View style={s.fbTagRow}>
          {FEEDBACK_TAGS.map(tag => {
            const on = selectedTags.includes(tag.id);
            return (
              <TouchableOpacity
                key={tag.id}
                style={[s.fbTag, on && s.fbTagOn]}
                onPress={() => setSelectedTags(prev => on ? prev.filter(t => t !== tag.id) : [...prev, tag.id])}
              >
                <Text style={[s.fbTagT, on && s.fbTagTOn]}>{tag.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
        <TextInput
          style={s.fbComment}
          value={comment}
          onChangeText={setComment}
          placeholder="추가 의견 (선택)"
          placeholderTextColor="#9CA3AF"
          maxLength={200}
        />
        <View style={s.fbActions}>
          <TouchableOpacity onPress={() => { setState('none'); setSelectedTags([]); setComment(''); }}>
            <Text style={s.fbCancel}>취소</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.fbSubmitBtn, selectedTags.length === 0 && { opacity: 0.4 }]}
            disabled={selectedTags.length === 0}
            onPress={() => { onSubmit(-1, selectedTags, comment); setState('disliked'); }}
          >
            <Text style={s.fbSubmitT}>제출</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // none 상태 — 좋아요/싫어요 버튼 (톤 다운)
  return (
    <View style={s.fbRow}>
      <TouchableOpacity style={s.fbBtn} onPress={() => { onSubmit(1, [], ''); setState('liked'); }}>
        <Text style={s.fbBtnT}>↑</Text>
        <Text style={s.fbBtnLabel}>도움됨</Text>
      </TouchableOpacity>
      <TouchableOpacity style={s.fbBtn} onPress={() => setState('tagging')}>
        <Text style={s.fbBtnT}>↓</Text>
        <Text style={s.fbBtnLabel}>아쉬움</Text>
      </TouchableOpacity>
    </View>
  );
}

/* ── 아파트 추천 카드 ── */
function AptRecommendCard({ apt, onPress }: { apt: ApartmentCard; onPress: () => void }) {
  const scoreColor = (apt.score ?? 0) >= 70 ? '#059669' : (apt.score ?? 0) >= 40 ? '#2563EB' : '#D97706';
  return (
    <TouchableOpacity style={s.recCard} onPress={onPress} activeOpacity={0.7}>
      <View style={s.recLeft}>
        <Text style={s.recName} numberOfLines={1}>{apt.name}</Text>
        {apt.address && <Text style={s.recAddr} numberOfLines={1}>{apt.address}</Text>}
        {apt.summary && <Text style={s.recSummary} numberOfLines={2}>{apt.summary}</Text>}
      </View>
      <View style={s.recRight}>
        {apt.score != null && (
          <View style={s.recScoreWrap}>
            <Text style={[s.recScore, { color: scoreColor }]}>{apt.score.toFixed(0)}</Text>
            <Text style={s.recScoreUnit}>점</Text>
          </View>
        )}
        <View style={s.recMapBtn}>
          <Text style={s.recMapBtnT}>지도</Text>
        </View>
      </View>
    </TouchableOpacity>
  );
}

/* ── 메시지 버블 ── */
function MessageBubble({ msg, msgIndex, onAptMapPress, onFeedback }: {
  msg: ChatMessage;
  msgIndex: number;
  onAptMapPress?: (apt: ApartmentCard) => void;
  onFeedback?: (msgIndex: number, rating: 1 | -1, tags: string[], comment: string) => void;
}) {
  const isUser = msg.role === 'user';
  const showFeedback = !isUser && !msg.isStreaming && msg.content.length > 0;

  return (
    <View style={[s.bubbleRow, isUser && s.bubbleRowUser]}>
      {!isUser && <Text style={s.avatar}>🐿️</Text>}
      <View style={[s.bubble, isUser ? s.bubbleUser : s.bubbleAst]}>
        {msg.toolStatus && msg.toolStatus.length > 0 && (
          <View style={s.toolRow}>
            {msg.toolStatus.map((t, i) => (
              <View key={i} style={[s.toolBadge, t.status === 'done' && s.toolDone]}>
                <Text style={s.toolT}>{t.status === 'running' ? '분석 중' : '완료'} · {t.name}</Text>
              </View>
            ))}
          </View>
        )}

        {isUser ? (
          <Text style={[s.bubbleT, s.bubbleTUser]}>{msg.content}</Text>
        ) : (
          <MarkdownText>{msg.content || (msg.isStreaming ? '...' : '')}</MarkdownText>
        )}
        {msg.isStreaming && <ActivityIndicator size="small" color="#2563EB" style={{ marginTop: 4 }} />}

        {msg.apartments && msg.apartments.length > 0 && (
          <View style={s.recContainer}>
            <View style={s.recHeader}>
              <View style={s.recHeaderDot} />
              <Text style={s.recHeaderT}>추천 아파트 {msg.apartments.length}건</Text>
            </View>
            {msg.apartments.map((apt, i) => (
              <AptRecommendCard key={i} apt={apt} onPress={() => onAptMapPress?.(apt)} />
            ))}
          </View>
        )}

        {/* 피드백 */}
        {showFeedback && onFeedback && (
          <FeedbackBar onSubmit={(rating, tags, comment) => onFeedback(msgIndex, rating, tags, comment)} />
        )}
      </View>
    </View>
  );
}

/* ── 메인 화면 ── */
export default function ChatScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { messages, loading, sendMessage, submitFeedback } = useChat();
  const [text, setText] = useState('');
  const flatListRef = useRef<FlatList>(null);
  const inputRef = useRef<TextInput>(null);
  const lastMapAptsRef = useRef<{ pnu: string; bld_nm: string; lat: number; lng: number; score: number }[]>([]);

  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages]);

  const prevLoading = useRef(loading);
  useEffect(() => {
    if (prevLoading.current && !loading) {
      setTimeout(() => inputRef.current?.focus(), 200);
    }
    prevLoading.current = loading;
  }, [loading]);

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setText('');
    const mapActions = await sendMessage(trimmed);
    if (mapActions && mapActions.length > 0) {
      const apts = mapActions.flatMap(a => a.apartments || []);
      if (apts.length > 0) {
        lastMapAptsRef.current = apts;
        emit('chatHighlight', { apartments: apts });
      }
    }
  }, [text, loading, sendMessage]);

  const handleAptMapPress = useCallback((apt: ApartmentCard) => {
    if (!apt.pnu) return;
    const mapApt = lastMapAptsRef.current.find(a => a.pnu === apt.pnu);
    if (mapApt && mapApt.lat !== 0) {
      emit('chatHighlight', { apartments: [mapApt] });
    } else {
      emit('chatHighlight', {
        apartments: [{ pnu: apt.pnu, bld_nm: apt.name, lat: 0, lng: 0, score: apt.score ?? 0 }],
      });
    }
    router.navigate('/(tabs)');
  }, [router]);

  const handleFeedback = useCallback((msgIndex: number, rating: 1 | -1, tags: string[], comment: string) => {
    submitFeedback(msgIndex, rating, tags, comment);
  }, [submitFeedback]);

  return (
    <KeyboardAvoidingView
      style={[s.container, { paddingTop: insets.top }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}
    >
      <View style={s.header}>
        <Text style={s.headerIcon}>🐿️</Text>
        <View>
          <Text style={s.headerTitle}>집토리</Text>
          <Text style={s.headerSub}>아파트 추천 AI</Text>
        </View>
      </View>

      {messages.length === 0 ? (
        <View style={s.empty}>
          <Text style={s.emptyIcon}>🐿️</Text>
          <Text style={s.emptyTitle}>안녕하세요! 집토리예요</Text>
          <Text style={s.emptyDesc}>
            아파트에 대해 궁금한 점을 물어보세요.{'\n'}
            추천, 비교, 분석까지 도와드릴게요!
          </Text>
          <View style={s.suggestRow}>
            {['강남 가성비 좋은 아파트', '학군 좋은 동네 추천', '3억 이하 신축'].map(q => (
              <TouchableOpacity key={q} style={s.suggestBtn} onPress={() => setText(q)}>
                <Text style={s.suggestT}>{q}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ) : (
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(_, i) => String(i)}
          renderItem={({ item, index }) => (
            <MessageBubble
              msg={item}
              msgIndex={index}
              onAptMapPress={handleAptMapPress}
              onFeedback={handleFeedback}
            />
          )}
          contentContainerStyle={s.msgList}
          showsVerticalScrollIndicator={false}
        />
      )}

      <View style={[s.inputRow, { paddingBottom: Math.max(insets.bottom, 8) }]}>
        <TextInput
          ref={inputRef}
          style={s.input}
          value={text}
          onChangeText={setText}
          placeholder="메시지를 입력하세요..."
          placeholderTextColor="#9CA3AF"
          multiline
          maxLength={1000}
          editable={!loading}
        />
        <TouchableOpacity
          style={[s.sendBtn, (!text.trim() || loading) && s.sendBtnOff]}
          onPress={handleSend}
          disabled={!text.trim() || loading}
        >
          <Text style={s.sendBtnT}>전송</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

/* ── Palette ── */
const P = {
  blue: '#2563EB', blueLight: '#EFF6FF', blueDark: '#1E40AF',
  green: '#059669', amber: '#D97706',
  bg: '#FFFFFF', card: '#F9FAFB', border: '#E5E7EB',
  text: '#111827', text2: '#6B7280', text3: '#9CA3AF',
};

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: P.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: P.border, gap: 10 },
  headerIcon: { fontSize: 26 },
  headerTitle: { fontSize: 17, fontWeight: '700', color: P.text },
  headerSub: { fontSize: 10, color: P.text3, marginTop: 1 },

  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: P.text, marginBottom: 8 },
  emptyDesc: { fontSize: 14, color: P.text2, textAlign: 'center', lineHeight: 22 },
  suggestRow: { marginTop: 20, gap: 8, width: '100%' },
  suggestBtn: { backgroundColor: P.blueLight, borderRadius: 10, paddingVertical: 10, paddingHorizontal: 16, borderWidth: 1, borderColor: '#BFDBFE' },
  suggestT: { fontSize: 13, color: P.blue, fontWeight: '500', textAlign: 'center' },

  msgList: { padding: 16, paddingBottom: 8 },
  bubbleRow: { flexDirection: 'row', marginBottom: 12, alignItems: 'flex-start' },
  bubbleRowUser: { justifyContent: 'flex-end' },
  avatar: { fontSize: 20, marginRight: 8, marginTop: 2 },
  bubble: { maxWidth: '82%', borderRadius: 16, padding: 12 },
  bubbleUser: { backgroundColor: P.blue, borderBottomRightRadius: 4 },
  bubbleAst: { backgroundColor: P.card, borderBottomLeftRadius: 4, borderWidth: 1, borderColor: P.border },
  bubbleT: { fontSize: 14, lineHeight: 21, color: P.text },
  bubbleTUser: { color: '#FFF' },

  toolRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 6 },
  toolBadge: { backgroundColor: '#FEF3C7', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  toolDone: { backgroundColor: '#D1FAE5' },
  toolT: { fontSize: 10, color: P.text2, fontWeight: '500' },

  recContainer: { marginTop: 10 },
  recHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  recHeaderDot: { width: 3, height: 10, backgroundColor: P.blue, borderRadius: 1.5 },
  recHeaderT: { fontSize: 11, fontWeight: '700', color: P.blue },
  recCard: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: '#FFF', borderRadius: 12, padding: 12, marginBottom: 6,
    borderWidth: 1, borderColor: P.border,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 3, elevation: 1,
  },
  recLeft: { flex: 1, marginRight: 10 },
  recName: { fontSize: 14, fontWeight: '700', color: P.text },
  recAddr: { fontSize: 11, color: P.text3, marginTop: 2 },
  recSummary: { fontSize: 11, color: P.text2, marginTop: 3, lineHeight: 16 },
  recRight: { alignItems: 'center', gap: 6 },
  recScoreWrap: { flexDirection: 'row', alignItems: 'baseline' },
  recScore: { fontSize: 22, fontWeight: '900', letterSpacing: -1 },
  recScoreUnit: { fontSize: 10, color: P.text3, marginLeft: 1 },
  recMapBtn: { backgroundColor: P.blueLight, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: '#BFDBFE' },
  recMapBtnT: { fontSize: 10, fontWeight: '600', color: P.blue },

  // Feedback
  fbRow: { flexDirection: 'row', gap: 10, marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: P.border },
  fbBtn: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: P.card, borderWidth: 1, borderColor: P.border },
  fbBtnT: { fontSize: 12, color: P.text3, fontWeight: '500' },
  fbBtnLabel: { fontSize: 11, color: P.text3 },
  fbConfirm: { fontSize: 11, color: P.text3, marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: P.border },

  fbTagging: { marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: P.border },
  fbTagTitle: { fontSize: 11, fontWeight: '600', color: P.text2, marginBottom: 8 },
  fbTagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  fbTag: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: P.card, borderWidth: 1, borderColor: P.border },
  fbTagOn: { backgroundColor: '#FEE2E2', borderColor: '#FCA5A5' },
  fbTagT: { fontSize: 11, color: P.text2, fontWeight: '500' },
  fbTagTOn: { color: '#DC2626', fontWeight: '600' },
  fbComment: {
    backgroundColor: P.bg, borderWidth: 1, borderColor: P.border, borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 6, fontSize: 12, color: P.text, marginBottom: 8,
  },
  fbActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 12, alignItems: 'center' },
  fbCancel: { fontSize: 12, color: P.text3 },
  fbSubmitBtn: { backgroundColor: P.blue, borderRadius: 6, paddingHorizontal: 14, paddingVertical: 6 },
  fbSubmitT: { fontSize: 12, fontWeight: '600', color: '#FFF' },

  // Input
  inputRow: { flexDirection: 'row', paddingHorizontal: 12, paddingTop: 8, borderTopWidth: 1, borderTopColor: P.border, gap: 8, alignItems: 'flex-end' },
  input: {
    flex: 1, minHeight: 42, maxHeight: 100, backgroundColor: P.card,
    borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10,
    fontSize: 14, borderWidth: 1, borderColor: P.border, color: P.text,
  },
  sendBtn: { backgroundColor: P.blue, borderRadius: 20, paddingHorizontal: 16, height: 42, justifyContent: 'center' },
  sendBtnOff: { opacity: 0.4 },
  sendBtnT: { color: '#FFF', fontSize: 14, fontWeight: '600' },
});
