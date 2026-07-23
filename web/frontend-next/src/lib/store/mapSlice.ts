import type { StateCreator } from "zustand";

export type FocusPnu = {
  pnu: string;
  lat: number;
  lng: number;
  name: string;
};

/** 콘텐츠 딥링크 유입 컨텍스트 — 지도 상단 1회성 배너용 (B-1) */
export type ContentBanner = {
  slug: string;
  title: string;
};

export type MapSlice = {
  selectedPnu: string | null;
  focusPnu: FocusPnu | null;
  viewMode: "map" | "dashboard";
  contentBanner: ContentBanner | null;

  selectApartment: (pnu: string | null) => void;
  clearSelection: () => void;
  focusApartment: (focus: FocusPnu | null) => void;
  clearFocus: () => void;
  switchView: (mode: "map" | "dashboard") => void;
  setContentBanner: (banner: ContentBanner) => void;
  clearContentBanner: () => void;
};

export const createMapSlice: StateCreator<MapSlice> = (set) => ({
  selectedPnu: null,
  focusPnu: null,
  viewMode: "map",
  contentBanner: null,

  selectApartment: (pnu) => set({ selectedPnu: pnu }),
  clearSelection: () => set({ selectedPnu: null }),
  focusApartment: (focus) => set({ focusPnu: focus }),
  clearFocus: () => set({ focusPnu: null }),
  switchView: (mode) => set({ viewMode: mode }),
  setContentBanner: (banner) => set({ contentBanner: banner }),
  clearContentBanner: () => set({ contentBanner: null }),
});
