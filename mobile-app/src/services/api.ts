import axios from 'axios';

// 개발 환경에서는 로컬 백엔드, 프로덕션에서는 실제 서버 URL 사용
const API_BASE = __DEV__
  ? 'http://localhost:8000'
  : 'https://api.jiptori.com';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

export { API_BASE };

// 아파트 상세 정보
export interface ApartmentDetail {
  basic: {
    pnu: string; bld_nm: string; total_hhld_cnt: number;
    dong_count: number; max_floor: number; use_apr_day: string;
    plat_plc: string; lat: number; lng: number; sigungu_code: string;
  };
  scores: Record<string, number>;
  facility_summary: Record<string, {
    nearest_distance_m: number; count_1km: number; count_3km: number; count_5km: number;
  }>;
  nearby_facilities: Record<string, { subtype: string; name: string; distance_m: number }[]>;
  school: {
    elementary_school_name: string; elementary_school_full_name: string;
    middle_school_zone: string; high_school_zone: string;
    high_school_zone_type: string; edu_office_name: string;
  } | null;
  safety: {
    safety_score: number; crime_safety_score: number; nudge_safety_score: number;
    cctv_nearest_m: number; cctv_count_500m: number; cctv_count_1km: number;
    police_nearest_m: number; police_count_3km: number;
    fire_nearest_m: number; fire_count_3km: number;
    crime_detail: Record<string, number> | null;
  } | null;
  population: {
    sigungu_name: string; total_pop: number; male_pop: number; female_pop: number;
    age_groups: { age_group: string; total: number; ratio: number; male: number; female: number }[];
  } | null;
}

export interface TradeData {
  trades: { deal_year: number; deal_month: number; deal_day: number; floor: number; exclu_use_ar: number; deal_amount: number }[];
  rents: { deal_year: number; deal_month: number; deal_day: number; floor: number; exclu_use_ar: number; deposit: number; monthly_rent: number }[];
}

export async function fetchApartmentDetail(pnu: string): Promise<ApartmentDetail> {
  const res = await api.get<ApartmentDetail>(`/api/apartment/${pnu}`);
  return res.data;
}

export async function fetchApartmentTrades(pnu: string): Promise<TradeData> {
  const res = await api.get<TradeData>(`/api/apartment/${pnu}/trades`);
  return res.data;
}
