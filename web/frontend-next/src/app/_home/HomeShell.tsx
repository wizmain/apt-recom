// src/app/_home/HomeShell.tsx
"use client";

import { useState } from "react";
import { useAppStore } from "@/lib/store";
import { useApartments, countActiveFilters } from "@/hooks/useApartments";
import { useNudge } from "@/hooks/useNudge";
import { useUrlSyncedPnu } from "@/hooks/useUrlSyncedPnu";
import { MapView } from "./Map/MapView";
import FilterPanel from "./FilterPanel";
import NudgeBar from "./NudgeBar";
import ResultCards from "./ResultCards";
import RecentTradesBanner from "./RecentTradesBanner";
import ChatButton from "./ChatButton";
import ChatModal from "./ChatModal";
import CompareModal from "./CompareModal";
import WeightDrawer from "./WeightDrawer";
import Dashboard from "./Dashboard";
import { DetailModalClient } from "./DetailModalClient";

export function HomeShell() {
  // store state
  const apartments = useAppStore((s) => s.apartments);
  const regionFitNonce = useAppStore((s) => s.regionFitNonce);
  const filters = useAppStore((s) => s.filters);
  const nudgeResults = useAppStore((s) => s.nudgeResults);
  const nudgeLoading = useAppStore((s) => s.nudgeLoading);
  const selectedNudges = useAppStore((s) => s.selectedNudges);
  const defaultWeights = useAppStore((s) => s.defaultWeights);
  const chatHighlights = useAppStore((s) => s.chatHighlightApts);
  const focusPnu = useAppStore((s) => s.focusPnu);
  const selectedPnu = useAppStore((s) => s.selectedPnu);
  const viewMode = useAppStore((s) => s.viewMode);
  const showChat = useAppStore((s) => s.showChat);
  const compareList = useAppStore((s) => s.compareList);

  // store actions
  const onBoundsChange = useAppStore((s) => s.onBoundsChange);
  const selectApartment = useAppStore((s) => s.selectApartment);
  const focusApartment = useAppStore((s) => s.focusApartment);
  const toggleCompare = useAppStore((s) => s.toggleCompare);
  const clearCompare = useAppStore((s) => s.clearCompare);
  const setAnalyzeContext = useAppStore((s) => s.setAnalyzeContext);
  const setInitialMessage = useAppStore((s) => s.setInitialMessage);
  const openChat = useAppStore((s) => s.openChat);
  const switchView = useAppStore((s) => s.switchView);
  const setCustomWeights = useAppStore((s) => s.setCustomWeights);

  // side-effect hooks
  useApartments();
  useNudge();
  useUrlSyncedPnu();

  // HomeShell-owned UI state (not in store)
  const [filterOpen, setFilterOpen] = useState(false);
  const [weightOpen, setWeightOpen] = useState(false);

  const hasResults = nudgeResults.length > 0 || nudgeLoading;
  const filterCount = countActiveFilters(filters);

  // Dashboard 진입 시 검색 행동 + chat 행동
  const handleAnalyzeFromMap = (name: string, pnu: string) => {
    setAnalyzeContext({ pnu, name });
    setInitialMessage(`${name} 분석해줘`);
    openChat();
  };

  // ResultCards onSelect — focus + select 동시 수행
  const handleResultSelect = (pnu: string) => {
    const apt = nudgeResults.find((r) => r.pnu === pnu);
    if (apt?.lat && apt?.lng) {
      focusApartment({ pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm });
    }
    selectApartment(pnu);
  };

  // RecentTradesBanner onSelect — 같은 패턴, apartments 에서 조회.
  // 컴포넌트 시그니처: (pnu: string, aptName: string) => void
  const handleBannerSelect = (pnu: string) => {
    const apt = apartments.find((a) => a.pnu === pnu);
    if (apt?.lat && apt?.lng) {
      focusApartment({ pnu, lat: apt.lat, lng: apt.lng, name: apt.bld_nm });
    }
    selectApartment(pnu);
  };

  // WeightDrawer onApply — 선택된 nudge 하나의 weights 를 store 에 설정.
  // 기존 App.tsx 패턴: customWeights = { [nudgeId]: weights } 하나씩 누적.
  const handleWeightApply = (weights: Record<string, number>) => {
    if (selectedNudges.length === 0) return;
    const nudgeId = selectedNudges[selectedNudges.length - 1];
    setCustomWeights({ [nudgeId]: weights });
  };

  return (
    <div className="relative w-full h-[100dvh] flex flex-col">
      <NudgeBar
        onOpenSettings={() => setWeightOpen(true)}
        onOpenFilter={() => setFilterOpen(true)}
        filterCount={filterCount}
      />

      {viewMode === "map" ? (
        <div className="relative flex-1">
          <MapView
            apartments={apartments}
            scoredApartments={nudgeResults}
            chatHighlights={chatHighlights}
            focusPnu={focusPnu}
            regionFitNonce={regionFitNonce}
            onBoundsChange={onBoundsChange}
            onDetailOpen={(pnu) => selectApartment(pnu)}
            onChatAnalyze={handleAnalyzeFromMap}
            onCompareToggle={toggleCompare}
          />
          <ResultCards
            results={nudgeResults}
            loading={nudgeLoading}
            onSelect={handleResultSelect}
          />
          <RecentTradesBanner
            onSelect={handleBannerSelect}
            onGoToDashboard={() => switchView("dashboard")}
            hasResults={hasResults}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <Dashboard />
        </div>
      )}

      {selectedPnu ? <DetailModalClient pnu={selectedPnu} /> : null}
      {showChat ? <ChatModal /> : null}
      {/* Compare bar — 비교 대상 1~2개 선택 시 하단 pill 노출 */}
      {compareList.length > 0 ? (
        <div
          className={`fixed bottom-0 left-0 right-0 sm:left-1/2 sm:right-auto sm:-translate-x-1/2
            ${hasResults ? "sm:bottom-32" : "sm:bottom-6"}
            z-20 bg-white border-t sm:border border-gray-200 shadow-lg sm:rounded-full
            px-4 py-3 sm:px-4 sm:py-2 flex items-center gap-2 sm:gap-3 sm:max-w-[95vw]`}
        >
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {compareList.map((c) => (
              <span
                key={c.pnu}
                className="inline-flex items-center gap-1 text-xs bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full min-w-0"
              >
                <span className="truncate max-w-[120px] sm:max-w-none">{c.name}</span>
                <button
                  onClick={() => toggleCompare(c.pnu, c.name)}
                  className="text-violet-400 hover:text-violet-700 flex-shrink-0"
                  aria-label={`${c.name} 비교에서 제거`}
                >
                  &times;
                </button>
              </span>
            ))}
            {compareList.length < 2 ? (
              <span className="text-xs text-gray-400 whitespace-nowrap">+ 1개 더 선택</span>
            ) : null}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {compareList.length === 2 ? (
              <button
                id="compare-btn"
                className="text-xs bg-violet-600 text-white px-3 py-1.5 rounded-full hover:bg-violet-700 font-medium whitespace-nowrap"
              >
                비교하기
              </button>
            ) : null}
            <button
              onClick={clearCompare}
              className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap"
            >
              초기화
            </button>
          </div>
        </div>
      ) : null}

      {compareList.length === 2 ? (
        <CompareModal
          pnu1={compareList[0].pnu}
          pnu2={compareList[1].pnu}
          onClose={clearCompare}
          triggerBtnId="compare-btn"
        />
      ) : null}

      <ChatButton hasResults={hasResults} />

      <FilterPanel
        isOpen={filterOpen}
        onClose={() => setFilterOpen(false)}
        resultCount={apartments.length}
      />

      <WeightDrawer
        isOpen={weightOpen}
        onClose={() => setWeightOpen(false)}
        defaultWeights={defaultWeights ?? {}}
        selectedNudges={selectedNudges}
        onApply={handleWeightApply}
      />
    </div>
  );
}
