export interface Apartment {
  pnu: string;
  bld_nm: string;
  lat: number;
  lng: number;
  total_hhld_cnt: number;
  sigungu_code: string;
  match_type?: 'region' | 'name';
}

export interface TopContributor {
  subtype: string;
  score: number;
  weight_sum: number;
  contribution: number;
}

export interface ScoredApartment extends Apartment {
  score: number;
  score_breakdown: Record<string, number>;
  top_contributors?: TopContributor[];
}

export interface NudgeWeights {
  [nudgeId: string]: Record<string, number>;
}

export interface MapBounds {
  sw: { lat: number; lng: number };
  ne: { lat: number; lng: number };
}

/** 선택된 지역 필터 (동일 명칭 지역 구분용) */
export interface SelectedRegion {
  type: 'sigungu' | 'emd';
  code: string; // sigungu: 5자리, emd: 10자리 bjd_code
  label: string; // UI 표시용 라벨
}

/** 검색 API의 지역 후보 (동일명 여러 지역 매칭 시) */
export interface RegionCandidate {
  type: 'sigungu' | 'emd';
  code: string;
  sigungu_code: string;
  bjd_code: string | null;
  label: string;
  count: number;
}
