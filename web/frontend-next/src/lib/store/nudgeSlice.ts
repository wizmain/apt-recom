import type { StateCreator } from "zustand";
import type { NudgeWeights, ScoredApartment, TopContributor } from "@/types/apartment";
import { api } from "@/lib/api";
import { useAppStore } from "./index";

export type RankContext = {
  rank: number;
  selectedNudges: string[];
  topContributors: TopContributor[];
};

export type NudgeSlice = {
  selectedNudges: string[];
  customWeights: Record<string, Record<string, number>> | null;
  defaultWeights: NudgeWeights | null;
  nudgeResults: ScoredApartment[];
  nudgeLoading: boolean;
  rankContext: RankContext | null;

  toggleNudge: (nudgeId: string) => void;
  setCustomWeights: (w: Record<string, Record<string, number>> | null) => void;
  fetchDefaultWeights: () => Promise<void>;
  scoreApartments: () => Promise<void>;
  setRankContext: (ctx: RankContext | null) => void;
};

export const createNudgeSlice: StateCreator<NudgeSlice> = (set) => ({
  selectedNudges: [],
  customWeights: null,
  defaultWeights: null,
  nudgeResults: [],
  nudgeLoading: false,
  rankContext: null,

  toggleNudge: (nudgeId) =>
    set((s) => ({
      selectedNudges: s.selectedNudges.includes(nudgeId)
        ? s.selectedNudges.filter((n) => n !== nudgeId)
        : [...s.selectedNudges, nudgeId],
    })),
  setCustomWeights: (w) => set({ customWeights: w }),
  fetchDefaultWeights: async () => {
    try {
      const res = await api.get<NudgeWeights>("/api/nudge/weights");
      set({ defaultWeights: res.data });
    } catch (err) {
      console.error("fetchDefaultWeights failed", err);
    }
  },
  scoreApartments: async () => {
    const state = useAppStore.getState();
    const {
      selectedNudges,
      customWeights,
      searchKeywords,
      filters,
      selectedRegion,
      mapBounds,
    } = state;

    if (selectedNudges.length === 0) {
      set({ nudgeResults: [], nudgeLoading: false });
      return;
    }
    set({ nudgeLoading: true });
    try {
      const body: Record<string, unknown> = {
        nudges: selectedNudges,
        weights: customWeights,
        top_n: 10,
      };
      // region이 있으면 bounds 생략 (vite + backend 정책)
      if (selectedRegion) {
        if (selectedRegion.type === "emd") body.bjd_code = selectedRegion.code;
        else body.sigungu_code = selectedRegion.code;
      } else if (mapBounds) {
        body.sw_lat = mapBounds.sw.lat;
        body.sw_lng = mapBounds.sw.lng;
        body.ne_lat = mapBounds.ne.lat;
        body.ne_lng = mapBounds.ne.lng;
      }
      if (searchKeywords.length > 0) body.keywords = searchKeywords;
      // filters는 이미 snake_case(min_area/max_area/...) — spread로 flat 전개
      Object.assign(body, filters);

      const res = await api.post<ScoredApartment[]>("/api/nudge/score", body);
      set({ nudgeResults: res.data, nudgeLoading: false });
    } catch (err) {
      console.error("scoreApartments failed", err);
      set({ nudgeLoading: false });
    }
  },
  setRankContext: (ctx) => set({ rankContext: ctx }),
});
