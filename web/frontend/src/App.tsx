import { useState, useCallback, useEffect } from 'react';
import Map from './components/Map';
import NudgeBar from './components/NudgeBar';
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
  const { apartments, filters, applyFilters, clearFilters } = useApartments();
  const { results, loading, defaultWeights, scoreApartments, fetchWeights } = useNudge();

  const [selectedNudges, setSelectedNudges] = useState<string[]>([]);
  const [showWeightDrawer, setShowWeightDrawer] = useState(false);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [customWeights, setCustomWeights] = useState<Record<string, Record<string, number>> | null>(null);
  const [, setMapBounds] = useState<MapBounds | undefined>(undefined);
  const [selectedPnu, setSelectedPnu] = useState<string | null>(null);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [showChat, setShowChat] = useState(false);
  const [chatHighlightPnus, setChatHighlightPnus] = useState<string[]>([]);
  const [chatInitialMessage, setChatInitialMessage] = useState<string | null>(null);
  const [chatAnalyzeContext, setChatAnalyzeContext] = useState<{ pnu: string; name: string } | null>(null);
  const [compareList, setCompareList] = useState<{ pnu: string; name: string }[]>([]);
  const [chatFocusApts, setChatFocusApts] = useState<{ lat: number; lng: number }[]>([]);

  // Fetch default weights on mount
  useEffect(() => {
    fetchWeights();
  }, [fetchWeights]);

  // Re-score when nudges, keyword, or filters change
  useEffect(() => {
    if (selectedNudges.length > 0) {
      scoreApartments(selectedNudges, customWeights, 10, undefined, searchKeyword || undefined, filters);
    } else {
      scoreApartments([], null, 0);
    }
  }, [selectedNudges, customWeights, searchKeyword, filters, scoreApartments]);

  const handleToggleNudge = useCallback((nudgeId: string) => {
    setSelectedNudges((prev) =>
      prev.includes(nudgeId)
        ? prev.filter((n) => n !== nudgeId)
        : [...prev, nudgeId]
    );
  }, []);

  const handleBoundsChange = useCallback((bounds: MapBounds) => {
    setMapBounds(bounds);
  }, []);

  const handleApplyWeights = useCallback((flatWeights: Record<string, number>) => {
    // API expects { nudge_id: { facility: weight } } — wrap flat weights per selected nudge
    const wrapped: Record<string, Record<string, number>> = {};
    for (const nid of selectedNudges) {
      wrapped[nid] = { ...flatWeights };
    }
    setCustomWeights(wrapped);
  }, [selectedNudges]);

  const handleSearchChange = useCallback((keyword: string) => {
    setSearchKeyword(keyword);
  }, []);

  const handleMapAction = useCallback((actions: MapAction[]) => {
    for (const action of actions) {
      const actionType = action.type || action.action;
      if (actionType === 'highlight' && action.pnus) {
        setChatHighlightPnus(action.pnus);
        // 아파트 좌표가 있으면 지도 포커싱
        if (action.apartments && action.apartments.length > 0) {
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
    setSelectedPnu(pnu);
  }, []);

  const handleCompareToggle = useCallback((pnu: string, name: string) => {
    setCompareList(prev => {
      const exists = prev.find(c => c.pnu === pnu);
      if (exists) return prev.filter(c => c.pnu !== pnu);
      if (prev.length >= 2) return prev; // max 2
      return [...prev, { pnu, name }];
    });
  }, []);

  // NudgeBar 높이 (검색 키워드가 있으면 더 높아짐)
  const barHeight = searchKeyword ? 'pt-[4.5rem]' : 'pt-14';

  return (
    <div className="relative w-full h-screen overflow-hidden">
      {/* Top nudge bar */}
      <NudgeBar
        selectedNudges={selectedNudges}
        onToggleNudge={handleToggleNudge}
        onOpenSettings={() => setShowWeightDrawer(true)}
        onOpenFilter={() => setShowFilterPanel(true)}
        filterCount={Object.values(filters).filter(v => v !== undefined).length}
        searchKeyword={searchKeyword}
        onSearchChange={handleSearchChange}
      />

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
          highlightPnus={chatHighlightPnus}
          chatFocusApts={chatFocusApts}
          searchKeyword={searchKeyword}
        />
      </div>

      {/* Bottom result cards */}
      <ResultCards results={results} loading={loading} onSelect={(pnu) => setSelectedPnu(pnu)} />

      {/* Detail modal */}
      {selectedPnu && (
        <DetailModal pnu={selectedPnu} onClose={() => setSelectedPnu(null)} />
      )}

      {/* Chat button & modal */}
      <ChatButton onClick={() => {
        setShowChat(prev => !prev);
        if (showChat) setChatInitialMessage(null);
      }} isOpen={showChat} />
      {showChat && (
        <ChatModal
          onClose={() => { setShowChat(false); setChatInitialMessage(null); setChatAnalyzeContext(null); }}
          onMapAction={handleMapAction}
          onApartmentClick={handleChatApartmentClick}
          initialMessage={chatInitialMessage}
          analyzeContext={chatAnalyzeContext}
        />
      )}

      {/* Compare bar */}
      {compareList.length > 0 && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-20 bg-white border border-gray-200 shadow-lg rounded-full px-4 py-2 flex items-center gap-3">
          {compareList.map(c => (
            <span key={c.pnu} className="inline-flex items-center gap-1 text-xs bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full">
              {c.name.length > 10 ? c.name.slice(0, 10) + '…' : c.name}
              <button onClick={() => handleCompareToggle(c.pnu, c.name)} className="text-violet-400 hover:text-violet-700 ml-0.5">&times;</button>
            </span>
          ))}
          {compareList.length < 2 && (
            <span className="text-xs text-gray-400">+ 아파트 1개 더 선택</span>
          )}
          {compareList.length === 2 && (
            <button
              onClick={() => {/* open compare modal handled below */}}
              className="text-xs bg-violet-600 text-white px-3 py-1 rounded-full hover:bg-violet-700 font-medium"
              id="compare-btn"
            >
              비교하기
            </button>
          )}
          <button onClick={() => setCompareList([])} className="text-xs text-gray-400 hover:text-gray-600">초기화</button>
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
