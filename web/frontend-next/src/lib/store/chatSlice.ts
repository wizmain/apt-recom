import type { StateCreator } from "zustand";

export type ChatHighlightApt = {
  pnu: string;
  bld_nm: string;
  lat: number;
  lng: number;
  score?: number;
};

export type ChatFocusApt = { lat: number; lng: number };

export type ChatSlice = {
  showChat: boolean;
  chatInitialMessage: string | null;
  chatAnalyzeContext: { pnu: string; name: string } | null;
  chatHighlightApts: ChatHighlightApt[];
  chatFocusApts: ChatFocusApt[];
  compareList: { pnu: string; name: string }[];

  openChat: () => void;
  closeChat: () => void;
  setInitialMessage: (msg: string | null) => void;
  setAnalyzeContext: (ctx: { pnu: string; name: string } | null) => void;
  setHighlights: (apts: ChatHighlightApt[]) => void;
  clearHighlights: () => void;
  setFocusApts: (apts: ChatFocusApt[]) => void;
  toggleCompare: (pnu: string, name: string) => void;
  clearCompare: () => void;
};

export const createChatSlice: StateCreator<ChatSlice> = (set) => ({
  showChat: false,
  chatInitialMessage: null,
  chatAnalyzeContext: null,
  chatHighlightApts: [],
  chatFocusApts: [],
  compareList: [],

  openChat: () => set({ showChat: true }),
  closeChat: () =>
    set({ showChat: false, chatInitialMessage: null, chatAnalyzeContext: null }),
  setInitialMessage: (msg) => set({ chatInitialMessage: msg }),
  setAnalyzeContext: (ctx) => set({ chatAnalyzeContext: ctx }),
  setHighlights: (apts) => set({ chatHighlightApts: apts }),
  clearHighlights: () => set({ chatHighlightApts: [] }),
  setFocusApts: (apts) => set({ chatFocusApts: apts }),
  toggleCompare: (pnu, name) =>
    set((s) => ({
      compareList: s.compareList.some((c) => c.pnu === pnu)
        ? s.compareList.filter((c) => c.pnu !== pnu)
        : s.compareList.length < 5
          ? [...s.compareList, { pnu, name }]
          : s.compareList,
    })),
  clearCompare: () => set({ compareList: [] }),
});
