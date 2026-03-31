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
  const isMapMode = viewMode === 'map';

  return (
    <div className="fixed top-0 left-0 right-0 z-10 bg-white/95 backdrop-blur-sm shadow-sm">
      {/* 공통: 로고 + 탭 + 지도 전용 컨트롤 */}
      <div className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 h-12 sm:h-14">
        <span className="text-sm font-semibold text-gray-700 whitespace-nowrap mr-0.5 sm:mr-1">🐿</span>
        <ViewTabs viewMode={viewMode} onViewChange={onViewChange} />

        {isMapMode && (
          <MapControls
            selectedNudges={selectedNudges}
            onToggleNudge={onToggleNudge}
            onOpenSettings={onOpenSettings}
            onOpenFilter={onOpenFilter}
            filterCount={filterCount}
            searchKeywords={searchKeywords}
            onAddKeyword={onAddKeyword}
          />
        )}
      </div>

      {/* 지도 모드 전용: 모바일 넛지 칩 + 키워드 태그 */}
      {isMapMode && (
        <>
          <MobileNudgeChips
            selectedNudges={selectedNudges}
            onToggleNudge={onToggleNudge}
            searchKeywords={searchKeywords}
          />
          <KeywordTags
            searchKeywords={searchKeywords}
            onRemoveKeyword={onRemoveKeyword}
            onClearAll={onClearAll}
          />
        </>
      )}
    </div>
  );
}

/* ── 하위 컴포넌트 ── */

function ViewTabs({ viewMode, onViewChange }: { viewMode: string; onViewChange: (m: 'map' | 'dashboard') => void }) {
  return (
    <div className="flex items-center bg-gray-100 rounded-full p-0.5 flex-shrink-0">
      {(['map', 'dashboard'] as const).map(mode => (
        <button
          key={mode}
          onClick={() => onViewChange(mode)}
          className={`px-2.5 sm:px-3 py-1 rounded-full text-xs font-medium transition-colors
            ${viewMode === mode ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
        >
          {mode === 'map' ? '지도' : '대시보드'}
        </button>
      ))}
    </div>
  );
}

function MapControls({
  selectedNudges, onToggleNudge, onOpenSettings, onOpenFilter, filterCount, searchKeywords, onAddKeyword,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void;
  onOpenSettings: () => void; onOpenFilter: () => void; filterCount: number;
  searchKeywords: string[]; onAddKeyword: (kw: string) => void;
}) {
  const { codes: nudgeCodes } = useCodes('nudge');
  const nudges = nudgeCodes.map(c => ({ id: c.code, label: c.name }));
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && inputValue.trim()) {
      const kw = inputValue.trim();
      if (!searchKeywords.includes(kw)) onAddKeyword(kw);
      setInputValue('');
    }
  }, [inputValue, searchKeywords, onAddKeyword]);

  return (
    <>
      {/* 검색 */}
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
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none">🔍</span>
      </div>

      {/* 넛지 칩 (데스크톱) */}
      <div className="hidden sm:flex items-center gap-2 overflow-x-auto scrollbar-hide">
        {nudges.map(nudge => (
          <NudgeChip
            key={nudge.id}
            nudge={nudge}
            isSelected={selectedNudges.includes(nudge.id)}
            disabled={searchKeywords.length === 0}
            onToggle={onToggleNudge}
            size="desktop"
          />
        ))}
      </div>

      {/* 필터 / 가중치 */}
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
    </>
  );
}

function MobileNudgeChips({
  selectedNudges, onToggleNudge, searchKeywords,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void; searchKeywords: string[];
}) {
  const { codes: nudgeCodes } = useCodes('nudge');
  const nudges = nudgeCodes.map(c => ({ id: c.code, label: c.name }));

  return (
    <div className="flex sm:hidden items-center gap-1.5 px-3 pb-2 overflow-x-auto scrollbar-hide">
      {nudges.map(nudge => (
        <NudgeChip
          key={nudge.id}
          nudge={nudge}
          isSelected={selectedNudges.includes(nudge.id)}
          disabled={searchKeywords.length === 0}
          onToggle={onToggleNudge}
          size="mobile"
        />
      ))}
    </div>
  );
}

function NudgeChip({
  nudge, isSelected, disabled, onToggle, size,
}: {
  nudge: { id: string; label: string }; isSelected: boolean; disabled: boolean;
  onToggle: (id: string) => void; size: 'desktop' | 'mobile';
}) {
  const sizeClass = size === 'desktop' ? 'px-3 py-1.5 text-sm' : 'px-2.5 py-1 text-xs';
  return (
    <button
      onClick={() => {
        if (disabled) { alert('지역명 또는 단지명을 먼저 입력해주세요.'); return; }
        onToggle(nudge.id);
      }}
      className={`${sizeClass} rounded-full font-medium whitespace-nowrap transition-all duration-200 border
        ${disabled
          ? 'bg-gray-50 text-gray-300 border-gray-200 cursor-not-allowed'
          : isSelected
            ? 'bg-blue-600 text-white border-blue-600 shadow-sm cursor-pointer'
            : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600 cursor-pointer'
        }`}
    >
      {nudge.label}
    </button>
  );
}

function KeywordTags({
  searchKeywords, onRemoveKeyword, onClearAll,
}: {
  searchKeywords: string[]; onRemoveKeyword: (kw: string) => void; onClearAll?: () => void;
}) {
  if (searchKeywords.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 px-3 sm:px-4 pb-2 -mt-1 overflow-x-auto scrollbar-hide">
      {searchKeywords.map(kw => (
        <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full whitespace-nowrap">
          📍 {kw}
          <button onClick={() => onRemoveKeyword(kw)} className="hover:text-blue-900 ml-0.5">✕</button>
        </span>
      ))}
      {searchKeywords.length > 1 && (
        <button onClick={onClearAll} className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap ml-1">
          전체삭제
        </button>
      )}
    </div>
  );
}
