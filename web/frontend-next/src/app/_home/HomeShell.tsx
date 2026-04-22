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
      {compareList.length === 2 ? (
        <CompareModal
          pnu1={compareList[0].pnu}
          pnu2={compareList[1].pnu}
          onClose={clearCompare}
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
