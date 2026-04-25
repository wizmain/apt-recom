/**
 * /api/dashboard/* 응답 타입.
 * 백엔드: web/backend/routers/dashboard.py
 */

export interface DashboardSummary {
  current_month: string;
  last_updated: string | null;
  new_today: number;
  current_period: string;
  prev_period: string;
  prev_label?: string;
  comparison_mode?: string;
  data_lag_notice?: string;
  trade: {
    volume: number;
    median_price_m2: number;
    prev_volume: number;
    prev_median_price_m2: number;
  };
  rent: {
    volume: number;
    median_deposit_m2: number;
    prev_volume: number;
    prev_median_deposit_m2: number;
  };
}

export interface DashboardTrendItem {
  month: string;
  trade_volume: number;
  trade_avg_price: number;
  trade_avg_price_m2: number;
  rent_volume: number;
  rent_avg_deposit: number;
  jeonse_ratio: number;
}

export interface DashboardRankingItem {
  sigungu_code: string;
  sigungu_name: string;
  volume: number;
  avg_price?: number;
  avg_deposit?: number;
}

export interface DashboardRecentTrade {
  apt_nm: string;
  sgg_cd: string;
  sigungu: string;
  area: number | null;
  floor: number | null;
  date: string;
  price?: number;
  deposit?: number;
  monthly_rent?: number;
  pnu?: string;
}

export interface DashboardRegionOption {
  code: string;
  name: string;
}
