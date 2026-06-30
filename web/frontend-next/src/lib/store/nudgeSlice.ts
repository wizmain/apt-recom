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
  /**
   * 스코어링 결과(top-N) 기준으로 지도 fitBounds 를 트리거하는 nonce.
   *
   * bump 조건: selectedRegion 이 존재한 상태에서 scoreApartments 가 성공적으로 끝났을 때.
   * bounds 기반(지역 미선택) 스코어링은 지도 이동으로 반복 실행되므로 bump 하지 않음
   * (자동 fit → 지도 튕김 피드백 루프 방지).
   */
  scoredFitNonce: number;

  toggleNudge: (nudgeId: string) => void;
  /**
   * 유효한 nudge 코드 목록을 한 번에 덮어씀 (프리셋 세팅용).
   * `toggleNudge` 반복 호출의 경합 위험 없이 단일 set 으로 처리.
   *
   * 필터:
   * - 빈 문자열/공백은 항상 제거.
   * - `validCodes` 가 주어지면 그 화이트리스트(common_code group='nudge')에
   *   속하지 않는 코드도 제거한다. 변조/오타된 딥링크가 깨진 코드를 store 에
   *   주입하는 것을 막기 위함. `validCodes` 를 생략하면 화이트리스트 검사를 건너뛴다
   *   (코드 목록을 아직 모르는 호출부의 하위호환).
   */
  setSelectedNudges: (ids: string[], validCodes?: string[]) => void;
  setCustomWeights: (w: Record<string, Record<string, number>> | null) => void;
  fetchDefaultWeights: () => Promise<void>;
  scoreApartments: () => Promise<void>;
  setRankContext: (ctx: RankContext | null) => void;
  clearSelectedNudges: () => void;
};

export const createNudgeSlice: StateCreator<NudgeSlice> = (set) => ({
  selectedNudges: [],
  customWeights: null,
  defaultWeights: null,
  nudgeResults: [],
  nudgeLoading: false,
  rankContext: null,
  scoredFitNonce: 0,

  toggleNudge: (nudgeId) =>
    set((s) => ({
      selectedNudges: s.selectedNudges.includes(nudgeId)
        ? s.selectedNudges.filter((n) => n !== nudgeId)
        : [...s.selectedNudges, nudgeId],
    })),
  setSelectedNudges: (ids, validCodes) =>
    set(() => {
      const cleaned = ids.map((id) => id.trim()).filter((id) => id.length > 0);
      const filtered = validCodes
        ? cleaned.filter((id) => validCodes.includes(id))
        : cleaned;
      return { selectedNudges: filtered };
    }),
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
      // 지역 선택 상태에서만 fit nonce bump — bounds 기반 재스코어링 시 지도 튕김 방지.
      const shouldFit = selectedRegion !== null && res.data.length > 0;
      set((s) => ({
        nudgeResults: res.data,
        nudgeLoading: false,
        scoredFitNonce: shouldFit ? s.scoredFitNonce + 1 : s.scoredFitNonce,
      }));
    } catch (err) {
      console.error("scoreApartments failed", err);
      set({ nudgeLoading: false });
    }
  },
  setRankContext: (ctx) => set({ rankContext: ctx }),
  clearSelectedNudges: () => set({ selectedNudges: [] }),
});
