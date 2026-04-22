// src/hooks/useNudge.ts
"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";

/** 홈 mount 시 defaultWeights 를 받아오고, NUDGE 선택 변화에 반응해 스코어 재계산. */
export function useNudge() {
  const defaultWeights = useAppStore((s) => s.defaultWeights);
  const fetchDefaultWeights = useAppStore((s) => s.fetchDefaultWeights);
  const selectedNudges = useAppStore((s) => s.selectedNudges);
  const customWeights = useAppStore((s) => s.customWeights);
  const apartments = useAppStore((s) => s.apartments);
  const scoreApartments = useAppStore((s) => s.scoreApartments);

  useEffect(() => {
    if (!defaultWeights) void fetchDefaultWeights();
  }, [defaultWeights, fetchDefaultWeights]);

  useEffect(() => {
    void scoreApartments();
  }, [selectedNudges, customWeights, apartments, scoreApartments]);
}
