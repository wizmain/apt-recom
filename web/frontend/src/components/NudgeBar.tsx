import { useState, useCallback } from 'react';
import { useCodes } from '../hooks/useCodes';

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
  viewMode: 'map' | 'dashboard';
  onViewChange: (mode: 'map' | 'dashboard') => void;
}

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
  viewMode,
  onViewChange,
}: NudgeBarProps) {
  const { codes: nudgeCodes } = useCodes('nudge');
  const NUDGES = nudgeCodes.map(c => ({ id: c.code, label: c.name }));
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
      {/* Row 1: 타이틀 + 검색 + 필터/가중치 */}
      <div className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 h-12 sm:h-14">
        <span className="text-sm font-semibold text-gray-700 whitespace-nowrap mr-0.5 sm:mr-1">🐿</span>

        {/* 지도/대시보드 탭 */}
        <div className="flex items-center bg-gray-100 rounded-full p-0.5 flex-shrink-0">
          <button
            onClick={() => onViewChange('map')}
            className={`px-2.5 sm:px-3 py-1 rounded-full text-xs font-medium transition-colors
              ${viewMode === 'map' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            지도
          </button>
          <button
            onClick={() => onViewChange('dashboard')}
            className={`px-2.5 sm:px-3 py-1 rounded-full text-xs font-medium transition-colors
              ${viewMode === 'dashboard' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            대시보드
          </button>
        </div>

        {/* 지역/단지 검색 */}
        <div className="relative flex-1 sm:flex-none">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="지역명·단지명 (Enter)"
            className="w-full sm:w-48 px-3 py-1.5 pr-7 text-sm border border-gray-300 rounded-full
                       focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500
                       placeholder-gray-400"
          />
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none">
            🔍
          </span>
        </div>

        {/* 넛지 칩 — 데스크톱에서만 Row 1에 표시 */}
        <div className="hidden sm:flex items-center gap-2 overflow-x-auto scrollbar-hide">
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

        {/* 필터/가중치 */}
        <div className="flex items-center gap-1.5 sm:gap-2 sm:ml-3 sm:pl-3 sm:border-l sm:border-gray-200 flex-shrink-0">
          <button
            onClick={onOpenFilter}
            className={`flex items-center gap-1 px-2 sm:px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium
                       border transition-all duration-200 whitespace-nowrap cursor-pointer
                       ${filterCount > 0
                         ? 'bg-blue-50 text-blue-600 border-blue-300'
                         : 'text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                       }`}
          >
            🔽<span className="hidden sm:inline"> 필터</span>{filterCount > 0 && ` (${filterCount})`}
          </button>
          <button
            onClick={onOpenSettings}
            className="flex items-center gap-1 px-2 sm:px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium
                       text-gray-600 border border-gray-300 hover:border-blue-400
                       hover:text-blue-600 transition-all duration-200 whitespace-nowrap cursor-pointer"
          >
            ⚙<span className="hidden sm:inline"> 가중치</span>
          </button>
        </div>
      </div>

      {/* Row 2: 넛지 칩 — 모바일에서만 별도 행 */}
      <div className="flex sm:hidden items-center gap-1.5 px-3 pb-2 overflow-x-auto scrollbar-hide">
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
                px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap
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

      {/* 검색 키워드 태그 */}
      {searchKeywords.length > 0 && (
        <div className="flex items-center gap-1.5 px-3 sm:px-4 pb-2 -mt-1 overflow-x-auto scrollbar-hide">
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
