import { useState, useCallback, useRef } from 'react';
import { API_BASE } from '../config';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  tool_calls?: Record<string, unknown>[];
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
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (
    message: string,
    context?: Record<string, string>,
  ): Promise<MapAction[] | undefined> => {
    const userMsg: ChatMessage = { role: 'user', content: message };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    // Build conversation history
    const conversation = [...messages, userMsg]
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }));

    // Abort previous stream if any
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Add placeholder assistant message
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: '',
      isStreaming: true,
      toolStatus: [],
    }]);

    let collectedContent = '';
    let toolCalls: Record<string, unknown>[] = [];
    const mapActions: MapAction[] = [];
    let toolStatuses: { name: string; status: 'running' | 'done'; preview?: string }[] = [];

    try {
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, conversation, context: context || {} }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = 'delta';
        for (const line of lines) {
          if (line.trim() === '') {
            // SSE event boundary — reset event type
            eventType = 'delta';
            continue;
          }
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
            continue;
          }
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);

              if (eventType === 'delta' && data.content) {
                collectedContent += data.content;
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      content: collectedContent,
                      isStreaming: true,
                      toolStatus: toolStatuses,
                    };
                  }
                  return updated;
                });
              } else if (eventType === 'generating') {
                // Tool execution done, LLM generating final response
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant') {
                    updated[updated.length - 1] = { ...last, isGenerating: true };
                  }
                  return updated;
                });
              } else if (eventType === 'tool_start') {
                toolStatuses = [...toolStatuses, { name: data.name, status: 'running' }];
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant') {
                    updated[updated.length - 1] = { ...last, toolStatus: toolStatuses };
                  }
                  return updated;
                });
              } else if (eventType === 'tool_done') {
                toolStatuses = toolStatuses.map(t =>
                  t.name === data.name ? { ...t, status: 'done' as const, preview: data.result_preview } : t
                );
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant') {
                    updated[updated.length - 1] = { ...last, toolStatus: toolStatuses };
                  }
                  return updated;
                });
              } else if (eventType === 'map_action') {
                mapActions.push(data);
              } else if (eventType === 'done') {
                toolCalls = data.tool_calls || [];
                if (data.map_actions) {
                  mapActions.push(...data.map_actions);
                }
              }
            } catch {
              // skip malformed JSON
            }
            eventType = 'delta'; // reset
          }
        }
      }

      // Finalize message
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

      return mapActions.length > 0 ? mapActions : undefined;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return undefined;
      console.error('채팅 스트리밍 실패:', err);
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === 'assistant') {
          updated[updated.length - 1] = {
            ...last,
            content: '죄송합니다. 오류가 발생했습니다. 다시 시도해 주세요.',
            isStreaming: false,
          };
        }
        return updated;
      });
      return undefined;
    } finally {
      setLoading(false);
    }
  }, [messages]);

  const submitFeedback = useCallback(async (
    messageIndex: number,
    rating: 1 | -1,
    tags: string[] = [],
    comment: string = '',
  ): Promise<{ success: boolean }> => {
    const assistantMsg = messages[messageIndex];
    if (!assistantMsg || assistantMsg.role !== 'assistant') return { success: false };

    // Find the preceding user message
    let userContent = '';
    for (let i = messageIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userContent = messages[i].content;
        break;
      }
    }

    try {
      const res = await fetch(`${API_BASE}/api/chat/feedback`, {
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
      return { success: res.ok };
    } catch (err) {
      console.error('피드백 전송 실패:', err);
      return { success: false };
    }
  }, [messages]);

  return { messages, loading, sendMessage, submitFeedback };
}
