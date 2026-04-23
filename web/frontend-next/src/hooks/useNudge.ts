// src/hooks/useNudge.ts
"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";

/**
 * 홈 mount 시 defaultWeights 를 받아오고, 사용자가 검색 조건(넛지·가중치·
 * 키워드·지역·필터) 을 바꿀 때만 스코어 재계산.
 *
 * 의도적으로 `apartments` / `mapBounds` 는 deps 에 넣지 않는다 —
 * 지도 드래그로 apartments 가 바뀔 때마다 rescore 하면 결과 카드가 깜빡이고
 * 백엔드에 불필요한 호출이 쌓인다. 스코어는 사용자 의도 변화에만 반응한다.
 */
export function useNudge() {
  const defaultWeights = useAppStore((s) => s.defaultWeights);
  const fetchDefaultWeights = useAppStore((s) => s.fetchDefaultWeights);
  const selectedNudges = useAppStore((s) => s.selectedNudges);
  const customWeights = useAppStore((s) => s.customWeights);
  const searchKeywords = useAppStore((s) => s.searchKeywords);
  const selectedRegion = useAppStore((s) => s.selectedRegion);
  const filters = useAppStore((s) => s.filters);
  const scoreApartments = useAppStore((s) => s.scoreApartments);

  useEffect(() => {
    if (!defaultWeights) void fetchDefaultWeights();
  }, [defaultWeights, fetchDefaultWeights]);

  useEffect(() => {
    void scoreApartments();
  }, [selectedNudges, customWeights, searchKeywords, selectedRegion, filters, scoreApartments]);
}
