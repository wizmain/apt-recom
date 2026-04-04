import { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';
import { useCodes } from '../hooks/useCodes';

interface NudgeBarProps {
  selectedNudges: string[];
  onToggleNudge: (nudgeId: string) => void;
  onOpenSettings: () => void;
  onOpenFilter: () => void;
  filterCount: number;
  searchKeywords: string[];
  keywordLabels?: Record<string, string>;
  onAddKeyword: (keyword: string, label?: string) => void;
  onRemoveKeyword: (keyword: string) => void;
  onClearAll?: () => void;
  viewMode: 'map' | 'dashboard';
  onViewChange: (mode: 'map' | 'dashboard') => void;
  onSelectApartment?: (pnu: string, lat: number, lng: number, name: string) => void;
}

export default function NudgeBar({
  selectedNudges,
  onToggleNudge,
  onOpenSettings,
  onOpenFilter,
  filterCount,
  searchKeywords,
  keywordLabels,
  onAddKeyword,
  onRemoveKeyword,
  onClearAll,
  viewMode,
  onViewChange,
  onSelectApartment,
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
            onSelectApartment={onSelectApartment}
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
            keywordLabels={keywordLabels}
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

interface SearchResult {
  pnu: string;
  bld_nm: string;
  lat: number | null;
  lng: number | null;
  new_plat_plc: string | null;
  match_type: 'region' | 'name' | 'region_empty';
  region_label?: string;
}

function MapControls({
  selectedNudges, onToggleNudge, onOpenSettings, onOpenFilter, filterCount, searchKeywords, onAddKeyword, onSelectApartment,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void;
  onOpenSettings: () => void; onOpenFilter: () => void; filterCount: number;
  searchKeywords: string[]; onAddKeyword: (kw: string, label?: string) => void;
  onSelectApartment?: (pnu: string, lat: number, lng: number, name: string) => void;
}) {
  const { codes: nudgeCodes } = useCodes('nudge');
  const nudges = nudgeCodes.map(c => ({ id: c.code, label: c.name }));
  const [inputValue, setInputValue] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const [noResultsMsg, setNoResultsMsg] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSelectApt = useCallback((apt: SearchResult) => {
    if (apt.lat && apt.lng) {
      onSelectApartment?.(apt.pnu, apt.lat, apt.lng, apt.bld_nm);
      const addr = apt.new_plat_plc || '';
      const match = addr.match(/^[가-힣]+\s[가-힣]+[시군구]/);
      const regionKw = match ? match[0] : apt.bld_nm;
      if (!searchKeywords.includes(regionKw)) onAddKeyword(regionKw);
    }
    setInputValue('');
    setShowDropdown(false);
    setHighlightIdx(-1);
  }, [onSelectApartment, onAddKeyword, searchKeywords]);

  const handleKeyDown = useCallback(async (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;

    // 드롭다운 열려있을 때 화살표/Enter 처리
    if (showDropdown && searchResults.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlightIdx(prev => {
          const next = prev < searchResults.length - 1 ? prev + 1 : 0;
          listRef.current?.children[next + 1]?.scrollIntoView({ block: 'nearest' });
          return next;
        });
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlightIdx(prev => {
          const next = prev > 0 ? prev - 1 : searchResults.length - 1;
          listRef.current?.children[next + 1]?.scrollIntoView({ block: 'nearest' });
          return next;
        });
        return;
      }
      if (e.key === 'Enter' && highlightIdx >= 0) {
        e.preventDefault();
        handleSelectApt(searchResults[highlightIdx]);
        return;
      }
    }

    if (e.key === 'Enter' && inputValue.trim()) {
      const kw = inputValue.trim();
      if (searchKeywords.includes(kw)) { setInputValue(''); return; }

      // API 호출하여 region/name 구분
      try {
        const res = await axios.get<SearchResult[]>(`${API_BASE}/api/apartments/search`, { params: { q: kw } });
        const data = res.data;
        const regionEmpty = data.find(d => d.match_type === 'region_empty');
        const hasRegion = data.some(d => d.match_type === 'region');

        if (regionEmpty) {
          // 지역 매칭됐지만 아파트 없음
          setSearchResults([]);
          setNoResultsMsg(`${regionEmpty.region_label || kw} 지역에 등록된 아파트가 없습니다`);
          setShowDropdown(true);
        } else if (hasRegion) {
          const regionItem = data.find(d => d.match_type === 'region' && d.region_label);
          const label = regionItem?.region_label || undefined;
          onAddKeyword(kw, label);
          setInputValue('');
          setShowDropdown(false);
          setNoResultsMsg('');
        } else if (data.length > 0) {
          const filtered = data.filter(d => d.lat != null);
          setSearchResults(filtered);
          setHighlightIdx(-1);
          setShowDropdown(true);
          setNoResultsMsg('');
        } else {
          setSearchResults([]);
          setNoResultsMsg('검색 결과가 없습니다');
          setShowDropdown(true);
        }
      } catch {
        onAddKeyword(kw);
        setInputValue('');
      }
    }
    if (e.key === 'Escape') {
      setShowDropdown(false);
      setHighlightIdx(-1);
    }
  }, [inputValue, searchKeywords, onAddKeyword, showDropdown, searchResults, highlightIdx, handleSelectApt]);

  return (
    <>
      {/* 검색 */}
      <div className="relative flex-1 sm:flex-none" ref={dropdownRef}>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => { setInputValue(e.target.value); setShowDropdown(false); setNoResultsMsg(''); }}
          onKeyDown={handleKeyDown}
          placeholder="지역명·단지명 (Enter)"
          className="w-full sm:w-48 px-3 py-1.5 pr-7 text-sm border border-gray-300 rounded-full
                     focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500
                     placeholder-gray-400"
        />
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none">🔍</span>

        {/* 단지명 검색 결과 드롭다운 */}
        {showDropdown && (noResultsMsg ? (
          <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
            <div className="px-3 py-3 text-sm text-gray-500 text-center">
              {noResultsMsg}
            </div>
          </div>
        ) : searchResults.length > 0 && (
          <div ref={listRef} className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg
                          max-h-64 overflow-y-auto z-50">
            <div className="px-3 py-1.5 text-xs text-gray-500 border-b border-gray-100">
              아파트를 선택하세요 ({searchResults.length}건) — ↑↓ 이동, Enter 선택
            </div>
            {searchResults.map((apt, idx) => (
              <button
                key={apt.pnu}
                onClick={() => handleSelectApt(apt)}
                onMouseEnter={() => setHighlightIdx(idx)}
                className={`w-full text-left px-3 py-2 transition-colors border-b border-gray-50 last:border-b-0
                  ${idx === highlightIdx ? 'bg-blue-50 text-blue-800' : 'hover:bg-gray-50'}`}
              >
                <div className="text-sm font-medium truncate">{apt.bld_nm}</div>
                {apt.new_plat_plc && (
                  <div className="text-xs text-gray-500 truncate">{apt.new_plat_plc}</div>
                )}
              </button>
            ))}
          </div>
        ))}
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
  searchKeywords, keywordLabels, onRemoveKeyword, onClearAll,
}: {
  searchKeywords: string[]; keywordLabels?: Record<string, string>; onRemoveKeyword: (kw: string) => void; onClearAll?: () => void;
}) {
  if (searchKeywords.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 px-3 sm:px-4 pb-2 -mt-1 overflow-x-auto scrollbar-hide">
      {searchKeywords.map(kw => (
        <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full whitespace-nowrap">
          📍 {keywordLabels?.[kw] || kw}
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
