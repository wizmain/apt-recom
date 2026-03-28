import { useState, useCallback, useRef } from 'react';

interface NudgeBarProps {
  selectedNudges: string[];
  onToggleNudge: (nudgeId: string) => void;
  onOpenSettings: () => void;
  onOpenFilter: () => void;
  filterCount: number;
  searchKeywords: string[];
  onAddKeyword: (keyword: string) => void;
  onRemoveKeyword: (keyword: string) => void;
  onClearAll?: () => void;
}

const NUDGES = [
  { id: 'cost', label: '가성비' },
  { id: 'pet', label: '반려동물' },
  { id: 'commute', label: '출퇴근' },
  { id: 'newlywed', label: '신혼육아' },
  { id: 'education', label: '학군' },
  { id: 'senior', label: '시니어' },
  { id: 'investment', label: '투자' },
  { id: 'nature', label: '자연친화' },
  { id: 'safety', label: '안전' },
];

export default function NudgeBar({
  selectedNudges,
  onToggleNudge,
  onOpenSettings,
  onOpenFilter,
  filterCount,
  searchKeywords,
  onAddKeyword,
  onRemoveKeyword,
  onClearAll,
}: NudgeBarProps) {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && inputValue.trim()) {
      const kw = inputValue.trim();
      if (!searchKeywords.includes(kw)) {
        onAddKeyword(kw);
      }
      setInputValue('');
    }
  }, [inputValue, searchKeywords, onAddKeyword]);

  const handleClearAll = useCallback(() => {
    setInputValue('');
    onClearAll?.();
  }, [onClearAll]);

  return (
    <div className="fixed top-0 left-0 right-0 z-10 bg-white/95 backdrop-blur-sm shadow-sm">
      <div className="flex items-center gap-2 px-4 h-14 overflow-x-auto">
        <span className="text-sm font-semibold text-gray-700 whitespace-nowrap mr-1">
          🐿 라이프스타일 아파트 찾기
        </span>

        {/* 지역/단지 검색 */}
        <div className="relative flex-shrink-0">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="지역명·단지명 (Enter로 추가)"
            className="w-48 px-3 py-1.5 pr-7 text-sm border border-gray-300 rounded-full
                       focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500
                       placeholder-gray-400"
          />
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none">
            🔍
          </span>
        </div>

        {/* 넛지 칩 */}
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide">
          {NUDGES.map((nudge) => {
            const isSelected = selectedNudges.includes(nudge.id);
            const disabled = searchKeywords.length === 0;
            return (
              <button
                key={nudge.id}
                onClick={() => {
                  if (disabled) {
                    alert('지역명 또는 단지명을 먼저 입력해주세요.');
                    return;
                  }
                  onToggleNudge(nudge.id);
                }}
                className={`
                  px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap
                  transition-all duration-200 border
                  ${disabled
                    ? 'bg-gray-50 text-gray-300 border-gray-200 cursor-not-allowed'
                    : isSelected
                      ? 'bg-blue-600 text-white border-blue-600 shadow-sm cursor-pointer'
                      : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600 cursor-pointer'
                  }
                `}
              >
                {nudge.label}
              </button>
            );
          })}
        </div>

        {/* 구분선 + 필터/가중치 */}
        <div className="flex items-center gap-2 ml-3 pl-3 border-l border-gray-200 flex-shrink-0">
          <button
            onClick={onOpenFilter}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium
                       border transition-all duration-200 whitespace-nowrap cursor-pointer
                       ${filterCount > 0
                         ? 'bg-blue-50 text-blue-600 border-blue-300'
                         : 'text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                       }`}
          >
            🔽 필터{filterCount > 0 && ` (${filterCount})`}
          </button>
          <button
            onClick={onOpenSettings}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium
                       text-gray-600 border border-gray-300 hover:border-blue-400
                       hover:text-blue-600 transition-all duration-200 whitespace-nowrap cursor-pointer"
          >
            ⚙ 가중치
          </button>
        </div>
      </div>

      {/* 검색 키워드 태그 */}
      {searchKeywords.length > 0 && (
        <div className="flex items-center gap-1.5 px-4 pb-2 -mt-1 overflow-x-auto">
          {searchKeywords.map((kw) => (
            <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full whitespace-nowrap">
              📍 {kw}
              <button onClick={() => onRemoveKeyword(kw)} className="hover:text-blue-900 ml-0.5">✕</button>
            </span>
          ))}
          {searchKeywords.length > 1 && (
            <button
              onClick={handleClearAll}
              className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap ml-1"
            >
              전체삭제
            </button>
          )}
        </div>
      )}
    </div>
  );
}
