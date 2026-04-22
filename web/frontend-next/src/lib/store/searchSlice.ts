import type { StateCreator } from "zustand";
import type { Apartment, MapBounds, SelectedRegion } from "@/types/apartment";
import { api } from "@/lib/api";
import { useAppStore } from "./index";

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
    const { mapBounds, selectedRegion, filters } = useAppStore.getState() as SearchSlice;
    if (!mapBounds && !selectedRegion) return;

    const params: Record<string, string | number | undefined> = {
      ...filters,
    };
    if (selectedRegion) {
      params[selectedRegion.type === "emd" ? "bjd_code" : "sigungu_code"] =
        selectedRegion.code;
    } else if (mapBounds) {
      params.sw_lat = mapBounds.sw.lat;
      params.sw_lng = mapBounds.sw.lng;
      params.ne_lat = mapBounds.ne.lat;
      params.ne_lng = mapBounds.ne.lng;
    }

    try {
      const res = await api.get<Apartment[]>("/api/apartments", { params });
      set({ apartments: res.data });
    } catch (err) {
      console.error("fetchApartments failed", err);
    }
  },
});
