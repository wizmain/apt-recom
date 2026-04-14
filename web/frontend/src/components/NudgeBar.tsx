import { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';
import { useCodes } from '../hooks/useCodes';
import type { RegionCandidate, SelectedRegion } from '../types/apartment';

interface NudgeBarProps {
  selectedNudges: string[];
  onToggleNudge: (nudgeId: string) => void;
  onOpenSettings: () => void;
  onOpenFilter: () => void;
  filterCount: number;
  searchKeywords: string[];
  keywordLabels?: Record<string, string>;
  selectedRegion: SelectedRegion | null;
  onAddKeyword: (keyword: string, label?: string) => void;
  onRemoveKeyword: (keyword: string) => void;
  onClearAll?: () => void;
  onSelectRegion: (region: SelectedRegion) => void;
  onClearRegion: () => void;
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
  selectedRegion,
  onAddKeyword,
  onRemoveKeyword,
  onClearAll,
  onSelectRegion,
  onClearRegion,
  viewMode,
  onViewChange,
  onSelectApartment,
}: NudgeBarProps) {
  const isMapMode = viewMode === 'map';
  const hasAnyKeyword = searchKeywords.length > 0 || selectedRegion !== null;

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
            hasAnyKeyword={hasAnyKeyword}
            onAddKeyword={onAddKeyword}
            onSelectRegion={onSelectRegion}
            onSelectApartment={onSelectApartment}
          />
        )}

        <SiteInfo />
      </div>

      {/* 지도 모드 전용: 모바일 넛지 칩 + 키워드/지역 태그 */}
      {isMapMode && (
        <>
          <MobileNudgeChips
            selectedNudges={selectedNudges}
            onToggleNudge={onToggleNudge}
            hasAnyKeyword={hasAnyKeyword}
          />
          <KeywordTags
            searchKeywords={searchKeywords}
            keywordLabels={keywordLabels}
            selectedRegion={selectedRegion}
            onRemoveKeyword={onRemoveKeyword}
            onClearAll={onClearAll}
            onClearRegion={onClearRegion}
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
          {mode === 'map' ? '지도' : '실거래대시보드'}
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
  sigungu_code?: string;
  bjd_code?: string;
}

interface SearchResponse {
  results: SearchResult[];
  region_candidates?: RegionCandidate[];
}

type DropdownMode = 'apt' | 'region' | 'empty';

function MapControls({
  selectedNudges, onToggleNudge, onOpenSettings, onOpenFilter, filterCount,
  hasAnyKeyword, onAddKeyword, onSelectRegion, onSelectApartment,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void;
  onOpenSettings: () => void; onOpenFilter: () => void; filterCount: number;
  hasAnyKeyword: boolean;
  onAddKeyword: (kw: string, label?: string) => void;
  onSelectRegion: (region: SelectedRegion) => void;
  onSelectApartment?: (pnu: string, lat: number, lng: number, name: string) => void;
}) {
  const { codes: nudgeCodes } = useCodes('nudge');
  const nudges = nudgeCodes.map(c => ({ id: c.code, label: c.name }));
  const [inputValue, setInputValue] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [regionCandidates, setRegionCandidates] = useState<RegionCandidate[]>([]);
  const [dropdownMode, setDropdownMode] = useState<DropdownMode | null>(null);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const [noResultsMsg, setNoResultsMsg] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const showDropdown = dropdownMode !== null;
  const itemCount = dropdownMode === 'apt' ? searchResults.length
    : dropdownMode === 'region' ? regionCandidates.length : 0;

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownMode(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const resetDropdown = useCallback(() => {
    setDropdownMode(null);
    setHighlightIdx(-1);
    setNoResultsMsg('');
  }, []);

  const handleSelectApt = useCallback((apt: SearchResult) => {
    if (apt.lat && apt.lng) {
      onSelectApartment?.(apt.pnu, apt.lat, apt.lng, apt.bld_nm);
      onAddKeyword(apt.bld_nm);
    }
    setInputValue('');
    resetDropdown();
  }, [onSelectApartment, onAddKeyword, resetDropdown]);

  const handleSelectRegionCandidate = useCallback((cand: RegionCandidate) => {
    onSelectRegion({ type: cand.type, code: cand.code, label: cand.label });
    setInputValue('');
    resetDropdown();
  }, [onSelectRegion, resetDropdown]);

  const handleKeyDown = useCallback(async (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;

    // 드롭다운 열려있을 때 화살표/Enter 처리
    if (showDropdown && itemCount > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlightIdx(prev => {
          const next = prev < itemCount - 1 ? prev + 1 : 0;
          listRef.current?.children[next + 1]?.scrollIntoView({ block: 'nearest' });
          return next;
        });
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlightIdx(prev => {
          const next = prev > 0 ? prev - 1 : itemCount - 1;
          listRef.current?.children[next + 1]?.scrollIntoView({ block: 'nearest' });
          return next;
        });
        return;
      }
      if (e.key === 'Enter' && highlightIdx >= 0) {
        e.preventDefault();
        if (dropdownMode === 'apt') handleSelectApt(searchResults[highlightIdx]);
        else if (dropdownMode === 'region') handleSelectRegionCandidate(regionCandidates[highlightIdx]);
        return;
      }
    }

    if (e.key === 'Enter' && inputValue.trim()) {
      const kw = inputValue.trim();

      try {
        const res = await axios.get<SearchResponse>(
          `${API_BASE}/api/apartments/search`, { params: { q: kw } },
        );
        const data = res.data;
        const results = data.results || [];
        const candidates = data.region_candidates || [];
        const regionEmpty = results.find(d => d.match_type === 'region_empty');
        const regionItems = results.filter(d => d.match_type === 'region');
        const nameItems = results.filter(d => d.match_type === 'name' && d.lat != null);

        // 1. 지역 매칭됐으나 아파트 없음
        if (regionEmpty) {
          setSearchResults([]);
          setRegionCandidates([]);
          setNoResultsMsg(`${regionEmpty.region_label || kw} 지역에 등록된 아파트가 없습니다`);
          setDropdownMode('empty');
          return;
        }

        // 2. 동일명 지역이 여러 곳 → 후보 드롭다운 표시
        if (candidates.length >= 2) {
          setRegionCandidates(candidates);
          setSearchResults([]);
          setHighlightIdx(-1);
          setDropdownMode('region');
          setNoResultsMsg('');
          return;
        }

        // 3. 단일 지역 매칭 → 즉시 선택
        if (regionItems.length > 0) {
          const first = regionItems[0];
          const regionType: 'sigungu' | 'emd' = first.bjd_code ? 'emd' : 'sigungu';
          const code = first.bjd_code || (first.sigungu_code || '').slice(0, 5);
          if (code) {
            onSelectRegion({ type: regionType, code, label: first.region_label || kw });
            setInputValue('');
            resetDropdown();
            return;
          }
        }

        // 4. 단지명 매칭 → 기존 방식 드롭다운
        if (nameItems.length > 0) {
          setSearchResults(nameItems);
          setRegionCandidates([]);
          setHighlightIdx(-1);
          setDropdownMode('apt');
          setNoResultsMsg('');
          return;
        }

        // 5. 결과 없음
        setSearchResults([]);
        setRegionCandidates([]);
        setNoResultsMsg('검색 결과가 없습니다');
        setDropdownMode('empty');
      } catch {
        onAddKeyword(kw);
        setInputValue('');
      }
    }
    if (e.key === 'Escape') {
      resetDropdown();
    }
  }, [
    inputValue, onAddKeyword, onSelectRegion, showDropdown, itemCount, highlightIdx,
    dropdownMode, searchResults, regionCandidates, handleSelectApt, handleSelectRegionCandidate,
    resetDropdown,
  ]);

  return (
    <>
      {/* 검색 */}
      <div className="relative flex-1 sm:flex-none" ref={dropdownRef}>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => { setInputValue(e.target.value); resetDropdown(); }}
          onKeyDown={handleKeyDown}
          placeholder="지역명·단지명 (Enter)"
          className="w-full sm:w-48 px-3 py-1.5 pr-7 text-sm bg-blue-50/70 border-2 border-blue-300 rounded-full
                     hover:border-blue-400 hover:bg-blue-50
                     focus:outline-none focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200
                     placeholder-blue-400/70 transition-colors"
        />
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-blue-500 text-xs pointer-events-none">🔍</span>

        {/* 검색 결과 드롭다운 */}
        {dropdownMode === 'empty' && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
            <div className="px-3 py-3 text-sm text-gray-500 text-center">{noResultsMsg}</div>
          </div>
        )}

        {dropdownMode === 'region' && regionCandidates.length > 0 && (
          <div ref={listRef} className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg
                          max-h-64 overflow-y-auto z-50">
            <div className="px-3 py-1.5 text-xs text-gray-500 border-b border-gray-100">
              동일 명칭의 지역이 여러 곳입니다 — 원하는 지역을 선택하세요
            </div>
            {regionCandidates.map((cand, idx) => (
              <button
                key={`${cand.type}-${cand.code}`}
                onClick={() => handleSelectRegionCandidate(cand)}
                onMouseEnter={() => setHighlightIdx(idx)}
                className={`w-full text-left px-3 py-2 transition-colors border-b border-gray-50 last:border-b-0
                  ${idx === highlightIdx ? 'bg-blue-50 text-blue-800' : 'hover:bg-gray-50'}`}
              >
                <div className="text-sm font-medium truncate">📍 {cand.label}</div>
                <div className="text-xs text-gray-500">아파트 {cand.count}개</div>
              </button>
            ))}
          </div>
        )}

        {dropdownMode === 'apt' && searchResults.length > 0 && (
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
        )}
      </div>

      {/* 넛지 칩 (데스크톱) */}
      <div className="hidden sm:flex items-center gap-2 overflow-x-auto scrollbar-hide">
        {nudges.map(nudge => (
          <NudgeChip
            key={nudge.id}
            nudge={nudge}
            isSelected={selectedNudges.includes(nudge.id)}
            disabled={!hasAnyKeyword}
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
  selectedNudges, onToggleNudge, hasAnyKeyword,
}: {
  selectedNudges: string[]; onToggleNudge: (id: string) => void; hasAnyKeyword: boolean;
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
          disabled={!hasAnyKeyword}
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

function SiteInfo() {
  // 상단바 우측 끝: 도메인 + 운영자 이메일 (데스크톱 전용 — 모바일은 공간 부족)
  return (
    <div className="hidden lg:flex flex-col items-end leading-tight ml-auto text-[11px] text-gray-500 whitespace-nowrap flex-shrink-0">
      <a
        href="https://www.apt-recom.kr"
        target="_blank"
        rel="noreferrer"
        className="font-medium text-blue-600 hover:text-blue-700 hover:underline"
      >
        www.apt-recom.kr
      </a>
      <a
        href="mailto:kindofme46@gmail.com"
        className="text-gray-500 hover:text-gray-700 hover:underline"
      >
        kindofme46@gmail.com
      </a>
    </div>
  );
}

function KeywordTags({
  searchKeywords, keywordLabels, selectedRegion, onRemoveKeyword, onClearAll, onClearRegion,
}: {
  searchKeywords: string[];
  keywordLabels?: Record<string, string>;
  selectedRegion: SelectedRegion | null;
  onRemoveKeyword: (kw: string) => void;
  onClearAll?: () => void;
  onClearRegion: () => void;
}) {
  if (searchKeywords.length === 0 && !selectedRegion) return null;

  return (
    <div className="flex items-center gap-1.5 px-3 sm:px-4 pb-2 -mt-1 overflow-x-auto scrollbar-hide">
      {selectedRegion && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded-full whitespace-nowrap">
          📍 {selectedRegion.label}
          <button onClick={onClearRegion} className="hover:text-emerald-900 ml-0.5" aria-label="지역 필터 해제">✕</button>
        </span>
      )}
      {searchKeywords.map(kw => (
        <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full whitespace-nowrap">
          🏢 {keywordLabels?.[kw] || kw}
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
