import { useEffect, useRef, useCallback } from 'react';
import { useChat } from '../hooks/useChat';
import type { MapAction } from '../hooks/useChat';
import ChatInput from './ChatInput';
import ChatMessage, { LoadingIndicator } from './ChatMessage';

interface ChatModalProps {
  onClose: () => void;
  onMapAction?: (actions: MapAction[]) => void;
  onApartmentClick?: (pnu: string) => void;
  initialMessage?: string | null;
  analyzeContext?: { pnu: string; name: string } | null;
}

export default function ChatModal({ onClose, onMapAction, onApartmentClick, initialMessage, analyzeContext }: ChatModalProps) {
  const { messages, loading, sendMessage, submitFeedback } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const initialSentRef = useRef(false);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Send initial message if provided (with context)
  useEffect(() => {
    if (initialMessage && !initialSentRef.current) {
      initialSentRef.current = true;
      const ctx = analyzeContext ? { apartment_pnu: analyzeContext.pnu, apartment_name: analyzeContext.name } : undefined;
      handleSend(initialMessage, ctx);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMessage]);

  const handleSend = useCallback(async (message: string, context?: Record<string, string>) => {
    const mapActions = await sendMessage(message, context);
    if (mapActions && mapActions.length > 0) {
      onMapAction?.(mapActions);
    }
  }, [sendMessage, onMapAction]);

  const handleFeedback = useCallback((
    messageIndex: number,
    rating: 1 | -1,
    tags?: string[],
    comment?: string,
  ) => {
    submitFeedback(messageIndex, rating, tags || [], comment || '');
  }, [submitFeedback]);

  return (
    <div className="fixed bottom-20 right-6 z-20 w-96 max-h-[70vh] bg-white rounded-xl shadow-2xl flex flex-col animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h3 className="text-sm font-bold text-gray-900 flex items-center gap-1.5">
          <span>🐿</span>
          <span className="text-amber-600">집토리</span>
        </h3>
        <div className="flex items-center gap-1">
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="닫기"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-3 min-h-0" style={{ maxHeight: 'calc(70vh - 120px)' }}>
        {messages.length === 0 && !loading && (
          <div className="text-center text-gray-400 text-sm py-8">
            <p>안녕하세요! 🐿 <span className="text-amber-600 font-semibold">집토리</span>입니다.</p>
            <p className="mt-1">아파트에 대해 무엇이든 물어보세요!</p>
          </div>
        )}
        {messages.map((msg, idx) => (
          <ChatMessage
            key={idx}
            message={msg}
            messageIndex={idx}
            onApartmentClick={onApartmentClick}
            onFeedback={handleFeedback}
          />
        ))}
        {loading && <LoadingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  );
}
