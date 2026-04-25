/**
 * SYNCED FROM packages/shared/types/apartment-list.ts — keep in sync.
 */

export interface ApartmentListItem {
  pnu: string;
  bld_nm: string;
  lat: number | null;
  lng: number | null;
  total_hhld_cnt: number | null;
  sigungu_code: string | null;
  max_floor: number | null;
  use_apr_day: string | null;
  area_min: number | null;
  area_max: number | null;
  avg_area: number | null;
  price_per_m2: number | null;
  jeonse_ratio: number | null;
}

/** GET /api/codes/{group} 응답. */
export interface CommonCodeRow {
  code: string;
  name: string;
  extra: string | null;
  sort_order: number | null;
}
