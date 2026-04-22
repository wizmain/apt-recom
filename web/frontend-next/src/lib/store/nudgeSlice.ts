import type { StateCreator } from "zustand";
import type { NudgeWeights, ScoredApartment, TopContributor } from "@/types/apartment";

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
    // Wave D Task 13
  },
  scoreApartments: async () => {
    // Wave D Task 13
  },
  setRankContext: (ctx) => set({ rankContext: ctx }),
});
