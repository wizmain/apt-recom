import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { ChatMessage as ChatMessageType, ApartmentCard } from '../hooks/useChat';

interface ChatMessageProps {
  message: ChatMessageType;
  messageIndex: number;
  onApartmentClick?: (pnu: string) => void;
  onFeedback?: (messageIndex: number, rating: 1 | -1, tags?: string[], comment?: string) => void;
}

const FEEDBACK_TAGS = [
  { id: 'inaccurate', label: '정보 부정확' },
  { id: 'too_long', label: '너무 길다' },
  { id: 'not_relevant', label: '원하는 답이 아님' },
  { id: 'score_wrong', label: '점수가 이상함' },
  { id: 'missing_info', label: '정보 부족' },
  { id: 'formatting', label: '가독성 나쁨' },
];

export default function ChatMessage({ message, messageIndex, onApartmentClick, onFeedback }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const [feedbackState, setFeedbackState] = useState<'none' | 'liked' | 'disliked' | 'tagging'>('none');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [comment, setComment] = useState('');

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0 mr-2 mt-0.5">
          <span className="text-white text-xs font-bold">AI</span>
        </div>
      )}
      <div className={`max-w-[88%] space-y-2`}>
        {/* Tool status indicators */}
        {!isUser && message.toolStatus && message.toolStatus.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-1">
            {message.toolStatus.map((tool, idx) => (
              <span
                key={idx}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium
                  ${tool.status === 'running'
                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                    : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  }`}
              >
                {tool.status === 'running' ? (
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                ) : (
                  <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
                {TOOL_LABELS[tool.name] || tool.name}
              </span>
            ))}
          </div>
        )}

        {/* Generating indicator (after tools, before streaming text) */}
        {!isUser && !message.content && message.isGenerating && (
          <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-gray-500 flex items-center gap-2">
            <svg className="w-4 h-4 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            답변 생성 중...
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <div className="bg-blue-600 text-white px-3.5 py-2.5 text-sm leading-relaxed rounded-2xl rounded-br-sm">
            {message.content}
          </div>
        ) : (
          message.content && (
            <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 text-sm leading-relaxed">
              <MarkdownContent content={message.content} />
              {message.isStreaming && <StreamingCursor />}
            </div>
          )
        )}

        {/* Apartment cards */}
        {message.apartments && message.apartments.length > 0 && (
          <div className="space-y-2">
            {message.apartments.map((apt, idx) => (
              <ApartmentCardItem
                key={idx}
                apartment={apt}
                onClick={() => apt.pnu && onApartmentClick?.(apt.pnu)}
              />
            ))}
          </div>
        )}

        {/* Feedback buttons — only for completed assistant messages */}
        {!isUser && message.content && !message.isStreaming && onFeedback && (
          <FeedbackBar
            state={feedbackState}
            selectedTags={selectedTags}
            comment={comment}
            onLike={() => {
              setFeedbackState('liked');
              onFeedback(messageIndex, 1);
            }}
            onDislike={() => {
              setFeedbackState('tagging');
            }}
            onTagToggle={(tagId) => {
              setSelectedTags(prev =>
                prev.includes(tagId) ? prev.filter(t => t !== tagId) : [...prev, tagId]
              );
            }}
            onCommentChange={setComment}
            onSubmitDislike={() => {
              setFeedbackState('disliked');
              onFeedback(messageIndex, -1, selectedTags, comment);
            }}
            onCancel={() => {
              setFeedbackState('none');
              setSelectedTags([]);
              setComment('');
            }}
          />
        )}
      </div>
    </div>
  );
}

/* ── Tool name labels ── */
const TOOL_LABELS: Record<string, string> = {
  search_apartments: '아파트 검색',
  get_apartment_detail: '상세 조회',
  compare_apartments: '아파트 비교',
  get_market_trend: '시세 분석',
  get_school_info: '학군 조회',
  search_knowledge: '지식 검색',
  search_commute: '출퇴근 조회',
};

/* ── Markdown renderer with styled components ── */
function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        h3: ({ children }) => (
          <h3 className="text-[13px] font-bold text-gray-900 mt-3 mb-1.5 flex items-center gap-1.5">
            <span className="w-1 h-4 bg-blue-500 rounded-full inline-block" />
            {children}
          </h3>
        ),
        h4: ({ children }) => (
          <h4 className="text-xs font-semibold text-gray-700 mt-2 mb-1">{children}</h4>
        ),
        strong: ({ children }) => {
          const text = String(children);
          // Score highlight — detect patterns like "23.34점" or "60.0점"
          const scoreMatch = text.match(/^([\d.]+)점$/);
          if (scoreMatch) {
            const score = parseFloat(scoreMatch[1]);
            return <ScoreBadge score={score} />;
          }
          // Price highlight — detect "N억", "N만 원"
          if (/[0-9,]+억|[0-9,]+만\s*원/.test(text)) {
            return <span className="text-blue-700 font-bold">{children}</span>;
          }
          return <strong className="font-semibold text-gray-900">{children}</strong>;
        },
        ul: ({ children }) => (
          <ul className="space-y-1 my-1">{children}</ul>
        ),
        li: ({ children }) => (
          <li className="flex items-start gap-1.5 text-[13px] text-gray-700">
            <span className="text-blue-400 mt-0.5 flex-shrink-0">•</span>
            <span className="flex-1">{children}</span>
          </li>
        ),
        p: ({ children }) => (
          <p className="text-[13px] text-gray-700 my-1">{children}</p>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2 rounded-lg border border-gray-200">
            <table className="w-full text-[11px]">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-gray-100">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1.5 text-left font-semibold text-gray-600">{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1.5 text-gray-700 border-t border-gray-100">{children}</td>
        ),
        hr: () => <hr className="my-2 border-gray-200" />,
        code: ({ children }) => (
          <code className="bg-gray-100 text-blue-700 px-1 py-0.5 rounded text-[11px]">{children}</code>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/* ── Score badge with color coding ── */
function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-emerald-100 text-emerald-800 border-emerald-200' :
    score >= 40 ? 'bg-blue-100 text-blue-800 border-blue-200' :
    score >= 20 ? 'bg-amber-100 text-amber-800 border-amber-200' :
    'bg-gray-100 text-gray-600 border-gray-200';

  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[11px] font-bold border ${color}`}>
      <ScoreMiniBar score={score} />
      {score.toFixed(1)}점
    </span>
  );
}

function ScoreMiniBar({ score }: { score: number }) {
  const pct = Math.min(score, 100);
  const color =
    pct >= 70 ? '#10b981' :
    pct >= 40 ? '#3b82f6' :
    pct >= 20 ? '#f59e0b' :
    '#9ca3af';
  return (
    <svg width="24" height="8" className="inline-block">
      <rect x="0" y="1" width="24" height="6" rx="3" fill="#e5e7eb" />
      <rect x="0" y="1" width={24 * pct / 100} height="6" rx="3" fill={color} />
    </svg>
  );
}

/* ── Streaming cursor ── */
function StreamingCursor() {
  return (
    <span className="inline-block w-1.5 h-4 bg-blue-500 rounded-sm ml-0.5 animate-pulse" />
  );
}

/* ── Apartment card ── */
function ApartmentCardItem({
  apartment,
  onClick,
}: {
  apartment: ApartmentCard;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left border border-gray-200 rounded-lg p-3 hover:shadow-md
                 hover:border-blue-300 transition-all bg-white cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {apartment.name}
          </p>
          {apartment.address && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{apartment.address}</p>
          )}
          {apartment.summary && (
            <p className="text-xs text-gray-600 mt-1 line-clamp-2">{apartment.summary}</p>
          )}
        </div>
        {apartment.score != null && (
          <ScoreBadge score={apartment.score} />
        )}
      </div>
    </button>
  );
}

/* ── Feedback bar ── */
function FeedbackBar({
  state,
  selectedTags,
  comment,
  onLike,
  onDislike,
  onTagToggle,
  onCommentChange,
  onSubmitDislike,
  onCancel,
}: {
  state: 'none' | 'liked' | 'disliked' | 'tagging';
  selectedTags: string[];
  comment: string;
  onLike: () => void;
  onDislike: () => void;
  onTagToggle: (tagId: string) => void;
  onCommentChange: (v: string) => void;
  onSubmitDislike: () => void;
  onCancel: () => void;
}) {
  if (state === 'liked') {
    return (
      <div className="flex items-center gap-1 mt-1 text-[11px] text-emerald-600">
        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
          <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
        </svg>
        감사합니다!
      </div>
    );
  }

  if (state === 'disliked') {
    return (
      <div className="flex items-center gap-1 mt-1 text-[11px] text-gray-500">
        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
        </svg>
        피드백 반영됨
      </div>
    );
  }

  if (state === 'tagging') {
    return (
      <div className="mt-2 p-2.5 bg-gray-50 border border-gray-200 rounded-lg space-y-2">
        <p className="text-[11px] font-medium text-gray-600">어떤 점이 아쉬웠나요?</p>
        <div className="flex flex-wrap gap-1">
          {FEEDBACK_TAGS.map(tag => (
            <button
              key={tag.id}
              onClick={() => onTagToggle(tag.id)}
              className={`px-2 py-0.5 rounded-full text-[10px] border transition-colors
                ${selectedTags.includes(tag.id)
                  ? 'bg-red-50 text-red-700 border-red-300'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
            >
              {tag.label}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={comment}
          onChange={e => onCommentChange(e.target.value)}
          placeholder="추가 의견 (선택)"
          className="w-full px-2 py-1 text-[11px] border border-gray-200 rounded-md
                     focus:outline-none focus:border-blue-400"
        />
        <div className="flex gap-1.5 justify-end">
          <button
            onClick={onCancel}
            className="px-2 py-0.5 text-[10px] text-gray-500 hover:text-gray-700"
          >
            취소
          </button>
          <button
            onClick={onSubmitDislike}
            className="px-2.5 py-0.5 text-[10px] bg-blue-600 text-white rounded-md
                       hover:bg-blue-700 disabled:opacity-40"
            disabled={selectedTags.length === 0}
          >
            제출
          </button>
        </div>
      </div>
    );
  }

  // state === 'none'
  return (
    <div className="flex items-center gap-0.5 mt-1 opacity-0 group-hover:opacity-100 hover:!opacity-100 transition-opacity"
         style={{ opacity: undefined }}
         onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
         onMouseLeave={e => (e.currentTarget.style.opacity = '0')}
    >
      <button
        onClick={onLike}
        className="p-1 rounded hover:bg-gray-100 text-gray-300 hover:text-emerald-500 transition-colors"
        title="좋아요"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3" />
        </svg>
      </button>
      <button
        onClick={onDislike}
        className="p-1 rounded hover:bg-gray-100 text-gray-300 hover:text-red-500 transition-colors"
        title="아쉬워요"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 15v3.586a1 1 0 01-.293.707l-3.414 3.414A1 1 0 015 22.414V15m5 0h6.586a2 2 0 001.707-3.04l-3.5-7A2 2 0 0018.086 3H10m0 12V3m0 0H7a2 2 0 00-2 2v7a2 2 0 002 2" />
        </svg>
      </button>
    </div>
  );
}

/* ── Loading indicator ── */
export function LoadingIndicator() {
  return (
    <div className="flex justify-start mb-3">
      <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0 mr-2">
        <span className="text-white text-xs font-bold">AI</span>
      </div>
      <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
        <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  );
}
