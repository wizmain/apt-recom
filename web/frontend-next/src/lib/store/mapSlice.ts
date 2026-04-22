import type { StateCreator } from "zustand";

export type FocusPnu = {
  pnu: string;
  lat: number;
  lng: number;
  name: string;
};

export type MapSlice = {
  selectedPnu: string | null;
  focusPnu: FocusPnu | null;
  viewMode: "map" | "dashboard";

  selectApartment: (pnu: string | null) => void;
  clearSelection: () => void;
  focusApartment: (focus: FocusPnu | null) => void;
  clearFocus: () => void;
  switchView: (mode: "map" | "dashboard") => void;
};

export const createMapSlice: StateCreator<MapSlice> = (set) => ({
  selectedPnu: null,
  focusPnu: null,
  viewMode: "map",

  selectApartment: (pnu) => set({ selectedPnu: pnu }),
  clearSelection: () => set({ selectedPnu: null }),
  focusApartment: (focus) => set({ focusPnu: focus }),
  clearFocus: () => set({ focusPnu: null }),
  switchView: (mode) => set({ viewMode: mode }),
});
