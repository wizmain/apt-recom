export interface Apartment {
  pnu: string;
  bld_nm: string;
  lat: number;
  lng: number;
  total_hhld_cnt: number;
  sigungu_code: string;
}

export interface ScoredApartment extends Apartment {
  score: number;
  score_breakdown: Record<string, number>;
}

export interface NudgeWeights {
  [nudgeId: string]: Record<string, number>;
}

export interface MapBounds {
  sw: { lat: number; lng: number };
  ne: { lat: number; lng: number };
}
