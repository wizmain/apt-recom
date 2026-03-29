import { useState, useCallback, useRef } from 'react';
import EventSource from 'react-native-sse';
import { API_BASE } from '../services/api';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  tool_calls?: unknown[];
  map_actions?: MapAction[];
  apartments?: ApartmentCard[];
  isStreaming?: boolean;
  isGenerating?: boolean;
  toolStatus?: { name: string; status: 'running' | 'done'; preview?: string }[];
}

export interface ApartmentCard {
  name: string;
  pnu?: string;
  score?: number;
  address?: string;
  summary?: string;
}

export interface MapAction {
  action?: string;
  type?: string;
  pnus?: string[];
  apartments?: { pnu: string; bld_nm: string; lat: number; lng: number; score: number }[];
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const sendMessage = useCallback((
    message: string,
    context?: Record<string, string>,
  ): Promise<MapAction[] | undefined> => {
    const userMsg: ChatMessage = { role: 'user', content: message };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    const conversation = [...messages, userMsg]
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }));

    // 이전 연결 종료
    esRef.current?.close();

    // 어시스턴트 플레이스홀더
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: '',
      isStreaming: true,
      toolStatus: [],
    }]);

    let collectedContent = '';
    let toolCalls: unknown[] = [];
    let mapActions: MapAction[] = [];
    let toolStatuses: { name: string; status: 'running' | 'done'; preview?: string }[] = [];

    return new Promise<MapAction[] | undefined>((resolve) => {
      type SSEEvents = 'delta' | 'generating' | 'tool_start' | 'tool_done' | 'map_action' | 'done';
      const es = new EventSource<SSEEvents>(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, conversation, context: context || {} }),
      });
      esRef.current = es;

      // 텍스트 스트리밍
      es.addEventListener('delta', (event) => {
        if (!event.data) return;
        try {
          const data = JSON.parse(event.data);
          if (data.content) {
            collectedContent += data.content;
            const content = collectedContent;
            const ts = [...toolStatuses];
            setMessages(prev => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last?.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content, isStreaming: true, toolStatus: ts };
              }
              return updated;
            });
          }
        } catch {}
      });

      // LLM 생성 중
      es.addEventListener('generating', () => {
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant') {
            updated[updated.length - 1] = { ...last, isGenerating: true };
          }
          return updated;
        });
      });

      // 도구 실행 시작
      es.addEventListener('tool_start', (event) => {
        if (!event.data) return;
        try {
          const data = JSON.parse(event.data);
          toolStatuses = [...toolStatuses, { name: data.name, status: 'running' }];
          const ts = [...toolStatuses];
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.role === 'assistant') {
              updated[updated.length - 1] = { ...last, toolStatus: ts };
            }
            return updated;
          });
        } catch {}
      });

      // 도구 실행 완료
      es.addEventListener('tool_done', (event) => {
        if (!event.data) return;
        try {
          const data = JSON.parse(event.data);
          toolStatuses = toolStatuses.map(t =>
            t.name === data.name ? { ...t, status: 'done' as const, preview: data.result_preview } : t
          );
          const ts = [...toolStatuses];
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.role === 'assistant') {
              updated[updated.length - 1] = { ...last, toolStatus: ts };
            }
            return updated;
          });
        } catch {}
      });

      // 지도 액션
      es.addEventListener('map_action', (event) => {
        if (!event.data) return;
        try {
          mapActions.push(JSON.parse(event.data));
        } catch {}
      });

      // 완료
      es.addEventListener('done', (event) => {
        if (event.data) {
          try {
            const data = JSON.parse(event.data);
            toolCalls = data.tool_calls || [];
            if (data.map_actions) mapActions.push(...data.map_actions);
          } catch {}
        }

        es.close();
        esRef.current = null;

        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant') {
            updated[updated.length - 1] = {
              ...last,
              content: collectedContent,
              tool_calls: toolCalls,
              map_actions: mapActions.length > 0 ? mapActions : undefined,
              isStreaming: false,
              toolStatus: toolStatuses,
            };
          }
          return updated;
        });
        setLoading(false);
        resolve(mapActions.length > 0 ? mapActions : undefined);
      });

      // 에러 또는 연결 종료 (서버가 스트림을 닫으면 error로 올 수 있음)
      es.addEventListener('error', () => {
        es.close();
        esRef.current = null;

        // collectedContent가 있으면 정상 완료로 처리
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant') {
            updated[updated.length - 1] = {
              ...last,
              content: collectedContent || '죄송합니다. 오류가 발생했습니다.',
              tool_calls: toolCalls.length > 0 ? toolCalls : undefined,
              map_actions: mapActions.length > 0 ? mapActions : undefined,
              isStreaming: false,
              toolStatus: toolStatuses,
            };
          }
          return updated;
        });
        setLoading(false);
        resolve(mapActions.length > 0 ? mapActions : undefined);
      });
    });
  }, [messages]);

  const submitFeedback = useCallback(async (
    messageIndex: number,
    rating: 1 | -1,
    tags: string[] = [],
    comment: string = '',
  ) => {
    const assistantMsg = messages[messageIndex];
    if (!assistantMsg || assistantMsg.role !== 'assistant') return;

    let userContent = '';
    for (let i = messageIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userContent = messages[i].content;
        break;
      }
    }

    try {
      await fetch(`${API_BASE}/api/chat/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_message: userContent,
          assistant_message: assistantMsg.content,
          tool_calls: assistantMsg.tool_calls || [],
          rating,
          tags,
          comment,
        }),
      });
    } catch (err) {
      console.error('피드백 전송 실패:', err);
    }
  }, [messages]);

  return { messages, loading, sendMessage, submitFeedback };
}
