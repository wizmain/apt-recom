import type { StateCreator } from "zustand";
import type { Apartment, MapBounds, SelectedRegion } from "@/types/apartment";

export type FilterState = {
  min_area?: number;
  max_area?: number;
  min_price?: number;
  max_price?: number;
  min_floor?: number;
  built_after?: number;
};

export type SearchSlice = {
  searchKeywords: string[];
  keywordLabels: Record<string, string>;
  selectedRegion: SelectedRegion | null;
  filters: FilterState;
  apartments: Apartment[];
  mapBounds: MapBounds | null;
  regionFitNonce: number;

  addKeyword: (keyword: string, label?: string) => void;
  removeKeyword: (keyword: string) => void;
  clearKeywords: () => void;
  selectRegion: (region: SelectedRegion) => void;
  clearRegion: () => void;
  applyFilters: (filters: FilterState) => void;
  clearFilters: () => void;
  onBoundsChange: (bounds: MapBounds) => void;
  fetchApartments: () => Promise<void>;
};

export const createSearchSlice: StateCreator<SearchSlice> = (set) => ({
  searchKeywords: [],
  keywordLabels: {},
  selectedRegion: null,
  filters: {},
  apartments: [],
  mapBounds: null,
  regionFitNonce: 0,

  addKeyword: (keyword, label) =>
    set((s) => ({
      searchKeywords: s.searchKeywords.includes(keyword)
        ? s.searchKeywords
        : [...s.searchKeywords, keyword],
      keywordLabels: label
        ? { ...s.keywordLabels, [keyword]: label }
        : s.keywordLabels,
    })),
  removeKeyword: (keyword) =>
    set((s) => ({
      searchKeywords: s.searchKeywords.filter((k) => k !== keyword),
    })),
  clearKeywords: () => set({ searchKeywords: [], keywordLabels: {} }),
  selectRegion: (region) =>
    set((s) => ({ selectedRegion: region, regionFitNonce: s.regionFitNonce + 1 })),
  clearRegion: () => set({ selectedRegion: null }),
  applyFilters: (filters) => set({ filters }),
  clearFilters: () => set({ filters: {} }),
  onBoundsChange: (bounds) => set({ mapBounds: bounds }),
  fetchApartments: async () => {
    // Wave D Task 12 에서 구현
  },
});
