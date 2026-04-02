import { useState, useCallback, useEffect } from 'react';
import Map from './components/Map';
import NudgeBar from './components/NudgeBar';
import Dashboard from './components/Dashboard';
import WeightDrawer from './components/WeightDrawer';
import ResultCards from './components/ResultCards';
import DetailModal from './components/DetailModal';
import CompareModal from './components/CompareModal';
import ChatButton from './components/ChatButton';
import ChatModal from './components/ChatModal';
import FilterPanel from './components/FilterPanel';
import { useApartments } from './hooks/useApartments';
import { useNudge } from './hooks/useNudge';
import type { MapBounds } from './types/apartment';
import type { MapAction } from './hooks/useChat';

function App() {
  const { apartments, filters, applyFilters, clearFilters, onBoundsChange, addKeyword, removeKeyword, clearKeywords } = useApartments();
  const { results, loading, defaultWeights, scoreApartments, fetchWeights } = useNudge();

  const [selectedNudges, setSelectedNudges] = useState<string[]>([]);
  const [showWeightDrawer, setShowWeightDrawer] = useState(false);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [customWeights, setCustomWeights] = useState<Record<string, Record<string, number>> | null>(null);
  // mapBounds는 useApartments에서 관리
  const [selectedPnu, setSelectedPnu] = useState<string | null>(null);
  const [searchKeywords, setSearchKeywords] = useState<string[]>([]);
  const [showChat, setShowChat] = useState(false);
  const [chatHighlightApts, setChatHighlightApts] = useState<{ pnu: string; bld_nm: string; lat: number; lng: number; score?: number }[]>([]);
  const [chatInitialMessage, setChatInitialMessage] = useState<string | null>(null);
  const [chatAnalyzeContext, setChatAnalyzeContext] = useState<{ pnu: string; name: string } | null>(null);
  const [compareList, setCompareList] = useState<{ pnu: string; name: string }[]>([]);
  const [chatFocusApts, setChatFocusApts] = useState<{ lat: number; lng: number }[]>([]);
  const [focusPnu, setFocusPnu] = useState<{ pnu: string; lat: number; lng: number; name: string } | null>(null);
  const [viewMode, setViewMode] = useState<'map' | 'dashboard'>('map');

  // Fetch default weights on mount
  useEffect(() => {
    fetchWeights();
  }, [fetchWeights]);

  // Re-score when nudges, keywords, or filters change
  useEffect(() => {
    if (selectedNudges.length > 0) {
      scoreApartments(selectedNudges, customWeights, 10, undefined, searchKeywords.length > 0 ? searchKeywords : undefined, filters);
    } else {
      scoreApartments([], null, 0);
    }
  }, [selectedNudges, customWeights, searchKeywords, filters, scoreApartments]);

  const handleToggleNudge = useCallback((nudgeId: string) => {
    setSelectedNudges((prev) =>
      prev.includes(nudgeId)
        ? prev.filter((n) => n !== nudgeId)
        : [...prev, nudgeId]
    );
  }, []);

  const handleBoundsChange = useCallback((bounds: MapBounds) => {
    onBoundsChange(bounds);
  }, [onBoundsChange]);

  const handleApplyWeights = useCallback((flatWeights: Record<string, number>) => {
    // API expects { nudge_id: { facility: weight } } — wrap flat weights per selected nudge
    const wrapped: Record<string, Record<string, number>> = {};
    for (const nid of selectedNudges) {
      wrapped[nid] = { ...flatWeights };
    }
    setCustomWeights(wrapped);
  }, [selectedNudges]);

  const handleAddKeyword = useCallback((keyword: string) => {
    setSearchKeywords(prev => prev.includes(keyword) ? prev : [...prev, keyword]);
    addKeyword(keyword);
  }, [addKeyword]);

  const handleRemoveKeyword = useCallback((keyword: string) => {
    setSearchKeywords(prev => {
      const next = prev.filter(k => k !== keyword);
      if (next.length === 0) setSelectedNudges([]);
      return next;
    });
    removeKeyword(keyword);
  }, [removeKeyword]);

  const handleClearAllKeywords = useCallback(() => {
    setSearchKeywords([]);
    clearKeywords();
    setSelectedNudges([]);
  }, [clearKeywords]);

  const handleMapAction = useCallback((actions: MapAction[]) => {
    for (const action of actions) {
      const actionType = action.type || action.action;
      if (actionType === 'highlight' && action.pnus) {
        // 아파트 좌표 데이터가 있으면 하이라이트 마커 + 지도 포커싱
        if (action.apartments && action.apartments.length > 0) {
          setChatHighlightApts(action.apartments);
          setChatFocusApts(action.apartments);
        }
      }
    }
  }, []);

  const handleAnalyzeApartment = useCallback((name: string, pnu: string) => {
    setChatAnalyzeContext({ pnu, name });
    setChatInitialMessage(`${name} 분석해줘`);
    setShowChat(true);
  }, []);

  const handleChatApartmentClick = useCallback((pnu: string) => {
    // highlightApts에서 좌표 찾기
    const apt = chatHighlightApts.find(a => a.pnu === pnu);
    if (apt?.lat && apt?.lng) {
      setFocusPnu({ pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm });
    } else {
      setSelectedPnu(pnu);
    }
  }, [chatHighlightApts]);

  const handleCompareToggle = useCallback((pnu: string, name: string) => {
    setCompareList(prev => {
      const exists = prev.find(c => c.pnu === pnu);
      if (exists) return prev.filter(c => c.pnu !== pnu);
      if (prev.length >= 2) return prev; // max 2
      return [...prev, { pnu, name }];
    });
  }, []);

  // NudgeBar 높이 — 대시보드 모드에서는 탭만 표시되므로 높이 축소
  const barHeight = viewMode === 'dashboard'
    ? 'pt-12 sm:pt-14'
    : searchKeywords.length > 0 ? 'pt-28 sm:pt-[4.5rem]' : 'pt-24 sm:pt-14';

  return (
    <div className="relative w-full h-dvh overflow-hidden">
      {/* Top nudge bar */}
      <NudgeBar
        selectedNudges={selectedNudges}
        onToggleNudge={handleToggleNudge}
        onOpenSettings={() => setShowWeightDrawer(true)}
        onOpenFilter={() => setShowFilterPanel(true)}
        filterCount={Object.values(filters).filter(v => v !== undefined).length}
        searchKeywords={searchKeywords}
        onAddKeyword={handleAddKeyword}
        onRemoveKeyword={handleRemoveKeyword}
        onClearAll={handleClearAllKeywords}
        viewMode={viewMode}
        onViewChange={setViewMode}
      />

      {viewMode === 'map' ? (
        <>
          {/* Map fills the viewport */}
          <div className={`absolute inset-0 ${barHeight}`}>
            <Map
              apartments={apartments}
              scoredResults={results}
              onBoundsChange={handleBoundsChange}
              onMarkerClick={(pnu) => setSelectedPnu(pnu)}
              onAnalyzeApartment={handleAnalyzeApartment}
              onDetailClick={(pnu) => setSelectedPnu(pnu)}
              onCompareToggle={handleCompareToggle}
              compareSelected={compareList.map(c => c.pnu)}
              highlightApts={chatHighlightApts}
              chatFocusApts={chatFocusApts}
              focusPnu={focusPnu}
              onFocusPnuHandled={() => setFocusPnu(null)}
              searchKeywords={searchKeywords}
            />
          </div>

          {/* Bottom result cards */}
          <ResultCards results={results} loading={loading} onSelect={(pnu) => {
            const apt = results.find(r => r.pnu === pnu);
            if (apt?.lat && apt?.lng) {
              setFocusPnu({ pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm });
            }
          }} />
        </>
      ) : (
        <div className={`absolute inset-0 ${barHeight} overflow-y-auto`}>
          <Dashboard />
        </div>
      )}

      {/* Detail modal */}
      {selectedPnu && (
        <DetailModal pnu={selectedPnu} onClose={() => setSelectedPnu(null)} />
      )}

      {/* Chat button & modal */}
      <ChatButton onClick={() => {
        setShowChat(prev => !prev);
        if (showChat) setChatInitialMessage(null);
      }} isOpen={showChat} hasResults={results.length > 0 || loading} />
      {showChat && (
        <ChatModal
          onClose={() => { setShowChat(false); setChatInitialMessage(null); setChatAnalyzeContext(null); setChatHighlightApts([]); setChatFocusApts([]); }}
          onMapAction={handleMapAction}
          onApartmentClick={handleChatApartmentClick}
          initialMessage={chatInitialMessage}
          analyzeContext={chatAnalyzeContext}
        />
      )}

      {/* Compare bar */}
      {compareList.length > 0 && (
        <div className={`fixed bottom-0 left-0 right-0
                        sm:left-1/2 sm:right-auto sm:-translate-x-1/2
                        ${results.length > 0 ? 'sm:bottom-32' : 'sm:bottom-6'}
                        z-20 bg-white border-t sm:border border-gray-200 shadow-lg sm:rounded-full
                        px-4 py-3 sm:px-4 sm:py-2 flex items-center gap-2 sm:gap-3 sm:max-w-[95vw]`}>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {compareList.map(c => (
              <span key={c.pnu} className="inline-flex items-center gap-1 text-xs bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full min-w-0">
                <span className="truncate max-w-[120px] sm:max-w-none">{c.name}</span>
                <button onClick={() => handleCompareToggle(c.pnu, c.name)} className="text-violet-400 hover:text-violet-700 flex-shrink-0">&times;</button>
              </span>
            ))}
            {compareList.length < 2 && (
              <span className="text-xs text-gray-400 whitespace-nowrap">+ 1개 더 선택</span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {compareList.length === 2 && (
              <button
                onClick={() => {/* open compare modal handled below */}}
                className="text-xs bg-violet-600 text-white px-3 py-1.5 rounded-full hover:bg-violet-700 font-medium whitespace-nowrap"
                id="compare-btn"
              >
                비교하기
              </button>
            )}
            <button onClick={() => setCompareList([])} className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap">초기화</button>
          </div>
        </div>
      )}

      {/* Compare modal */}
      {compareList.length === 2 && (
        <CompareModal
          pnu1={compareList[0].pnu}
          pnu2={compareList[1].pnu}
          onClose={() => setCompareList([])}
          triggerBtnId="compare-btn"
        />
      )}

      {/* Filter panel */}
      <FilterPanel
        isOpen={showFilterPanel}
        onClose={() => setShowFilterPanel(false)}
        filters={filters}
        onApply={applyFilters}
        onClear={clearFilters}
        resultCount={apartments.length}
      />

      {/* Weight drawer */}
      <WeightDrawer
        isOpen={showWeightDrawer}
        onClose={() => setShowWeightDrawer(false)}
        defaultWeights={defaultWeights}
        selectedNudges={selectedNudges}
        onApply={handleApplyWeights}
      />
    </div>
  );
}

export default App;
