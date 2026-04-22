/**
 * 아파트 도메인 공통 타입 — 서버/클라이언트 공용.
 */

export interface Apartment {
  pnu: string;
  bld_nm: string;
  lat: number;
  lng: number;
  total_hhld_cnt: number;
  sigungu_code: string;
  match_type?: "region" | "name";
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
  type: "sigungu" | "emd";
  code: string;
  label: string;
}

/** 검색 API 의 지역 후보 (동일명 여러 지역 매칭 시) */
export interface RegionCandidate {
  type: "sigungu" | "emd";
  code: string;
  sigungu_code: string;
  bjd_code: string | null;
  label: string;
  count: number;
}

/**
 * `/api/apartment/{pnu}` 상세 응답 구조 (routers/detail.py 기준).
 * DB 원본 컬럼명을 그대로 사용. services/tools.py 의 LLM alias (`name`,
 * `address`, `total_households` 등) 와 구별할 것.
 */
export interface ApartmentBasic {
  pnu: string;
  bld_nm: string;
  total_hhld_cnt?: number | null;
  dong_count?: number | null;
  max_floor?: number | null;
  use_apr_day?: string | null;
  plat_plc?: string | null;
  new_plat_plc?: string | null;
  bjd_code?: string | null;
  sigungu_code?: string;
  lat: number;
  lng: number;
  bld_nm_norm?: string | null;
  coord_source?: string | null;
  group_pnu?: string | null;
  min_area?: number | null;
  max_area?: number | null;
  avg_area?: number | null;
  min_supply_area?: number | null;
  max_supply_area?: number | null;
  avg_supply_area?: number | null;
  price_per_m2?: number | null;
}

export interface SchoolZone {
  pnu?: string;
  elementary_school_name?: string | null;
  elementary_school_full_name?: string | null;
  elementary_school_id?: string | null;
  elementary_zone_id?: string | null;
  middle_school_zone?: string | null;
  middle_school_zone_id?: string | null;
  high_school_zone?: string | null;
  high_school_zone_id?: string | null;
  high_school_zone_type?: string | null;
  edu_office_name?: string | null;
  edu_district?: string | null;
}

export interface ApartmentDetail {
  basic: ApartmentBasic;
  scores?: Record<string, number>;
  facility_summary?: Record<
    string,
    {
      facility_subtype?: string;
      nearest_distance_m?: number | null;
      count_1km?: number | null;
      count_3km?: number | null;
      count_5km?: number | null;
    }
  >;
  nearby_facilities?: unknown;
  school?: SchoolZone | null;
  safety?: Record<string, unknown> | null;
  population?: Record<string, unknown> | null;
  kapt_info?: Record<string, unknown> | null;
  mgmt_cost?: Record<string, unknown> | null;
}

/** `/api/apartment/{pnu}/trades` 응답 */
export interface TradeHistoryItem {
  deal_year: number;
  deal_month: number;
  deal_day?: number;
  deal_amount: number;
  exclu_use_ar?: number;
  floor?: number;
}
export interface RentHistoryItem {
  deal_year: number;
  deal_month: number;
  deposit: number;
  monthly_rent?: number;
  exclu_use_ar?: number;
  floor?: number;
}
export interface TradesResponse {
  trades: TradeHistoryItem[];
  rents: RentHistoryItem[];
}
