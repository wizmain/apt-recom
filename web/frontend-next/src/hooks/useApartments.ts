// src/hooks/useApartments.ts
"use client";

import { useEffect, useRef } from "react";
import { useAppStore } from "@/lib/store";

/**
 * 지도 bounds·region·filters·keywords 변화에 따라 /api/apartments 재조회.
 * 300ms debounce — 지도 drag 스팸 방지.
 */
export function useApartments() {
  const mapBounds = useAppStore((s) => s.mapBounds);
  const selectedRegion = useAppStore((s) => s.selectedRegion);
  const filters = useAppStore((s) => s.filters);
  const searchKeywords = useAppStore((s) => s.searchKeywords);
  const fetchApartments = useAppStore((s) => s.fetchApartments);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      void fetchApartments();
    }, 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [mapBounds, selectedRegion, filters, searchKeywords, fetchApartments]);
}

export function countActiveFilters(f: Record<string, unknown>): number {
  return Object.values(f).filter((v) => v !== undefined && v !== null && v !== "").length;
}
