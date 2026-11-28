// 오르는 단지 API(/api/rising*) 응답 타입. 필드명·null 허용은 backend/services/rising.py 기준.

/** 정렬 키 — backend SORT_ORDER_SQL 의 키와 1:1. */
export type RisingSort =
  | "change_6m"
  | "change_12m"
  | "relative_6m"
  | "region_price"
  | "complex_rank"
  | "price_asc"
  | "budget_near";

/** common_code rising_area_band 한 행. max_area null = 상한 없음. */
export interface RisingBand {
  code: string;
  name: string;
  min_area: number;
  max_area: number | null;
}

/** 시군구×면적대 집계 한 행 (metadata 의 regions[면적대코드]). */
export interface RisingRegion {
  sigungu_code: string;
  sigungu_name: string;
  sido_code: string;
  median_price_3m: number | null;
  trade_count_3m: number | null;
  change_6m_pct: number | null;
  change_12m_pct: number | null;
  region_grade: string | null;
  region_rank: number | null;
  region_rank_total: number | null;
}

/** common_code rising_scope_sido 한 행 — 지역 패널 시도 탭. */
export interface RisingSido {
  code: string;
  name: string;
}

/** GET /api/rising/meta. base_ym(YYYYMM) null = 집계 전. */
export interface RisingMeta {
  base_ym: number | null;
  bands: RisingBand[];
  sidos: RisingSido[];
  regions: Record<string, RisingRegion[]>;
}

/** 주의 표시 한 건 (common_code rising_caution). 판정은 배치, 화면은 표시만 한다. */
export interface RisingCaution {
  code: string;
  /** 배지 문구 */
  name: string;
  /** 툴팁·상세 설명 */
  description: string;
}

/** 단지×면적대 집계 한 행. 금액은 만원, 변화율은 %. */
export interface RisingItem {
  pnu: string;
  name: string;
  address: string | null;
  sigungu_code: string;
  median_price_3m: number | null;
  trade_count_3m: number | null;
  change_6m_pct: number | null;
  change_12m_pct: number | null;
  matched_type_count_6m: number | null;
  matched_type_count_12m: number | null;
  relative_change_6m_pct: number | null;
  complex_grade: string | null;
  complex_rank: number | null;
  complex_rank_total: number | null;
  grade_window_months: number | null;
  /** 최근 3개월 / 6개월 전 3개월 창의 지상층 평균. 층 정보가 없으면 null. */
  avg_floor_3m: number | null;
  avg_floor_past_6m: number | null;
  /** 변화율 해석 주의(표본 적음·고층 거래 위주 등). 없으면 빈 배열. */
  cautions: RisingCaution[];
  region_grade: string | null;
}

/** GET /api/rising. region_counts 는 시군구 선택·검색어를 뺀 지역별 단지 수. */
export interface RisingListResponse {
  base_ym: number | null;
  total_count: number;
  region_count: number;
  page: number;
  page_size: number;
  items: RisingItem[];
  region_counts: Record<string, number>;
}

export interface RisingMonthlyPoint {
  ym: number;
  median_price: number | null;
  trade_count: number;
}

export interface RisingRecentTrade {
  deal_date: string | null;
  exclu_use_ar: number;
  floor: number | null;
  deal_amount: number;
  is_direct_deal: boolean;
}

/** 상승과 함께 보이는 정보 한 건 (common_code rising_signal). 판정은 backend services/rising_signals.py. */
export interface RisingSignal {
  code: string;
  /** 제목 */
  name: string;
  /** 일반 설명 */
  description: string;
  /** 이 단지의 근거 수치 문구 (예: "1987년 준공 · 39년") */
  evidence: string;
}

/** GET /api/rising/{pnu}?area_band= */
export interface RisingDetail {
  pnu: string;
  name: string;
  address: string | null;
  item: RisingItem;
  /** 6개월 상승 단지만 채워진다. 하락·보합·비교 부족은 빈 배열. */
  signals: RisingSignal[];
  monthly: RisingMonthlyPoint[];
  recent_trades: RisingRecentTrade[];
}

/** GET /api/rising/complex/{pnu} 의 면적대 한 줄 — 상세 팝업 가격흐름 탭. */
export interface RisingComplexBand {
  area_band: string;
  area_band_name: string;
  item: RisingItem;
  region: RisingRegion | null;
}

/** GET /api/rising/complex/{pnu} — 요청 PNU 의 대표 단지(pnu) 전 면적대 요약. */
export interface RisingComplexSummary {
  base_ym: number | null;
  pnu: string;
  name: string;
  address: string | null;
  /** 지도 배지와 같은 기준(최근 3개월 거래 최다)의 첫 면적대. 집계 없으면 null. */
  default_band: string | null;
  bands: RisingComplexBand[];
}

/** 화면 필터 상태. 예산은 억 단위(API 파라미터와 동일), 양 끝 값은 "제한 없음"(budgetScale.ts). */
export interface RisingFilters {
  areaBand: string;
  budgetMin: number;
  budgetMax: number;
  sido: string | null;
  sggCodes: string[];
  query: string;
  sort: RisingSort;
  page: number;
}

/** 지도 마커 방향 — 서버 판정(보합 ±2%, 비교 부족·표본 적음은 none). backend services/rising.py trend_direction */
export type TrendDirection = "up" | "down" | "flat" | "none";

/** POST /api/rising/map 단지별 추세 요약 (면적 필터와 겹치는 면적대 중 거래 최다). */
export interface MapTrend {
  area_band: string;
  area_band_name: string;
  median_price_3m: number | null;
  trade_count_3m: number | null;
  change_6m_pct: number | null;
  change_12m_pct: number | null;
  /** 비교에 쓴 주택형 수 — 1 이면 "한 주택형만 비교" 표시. */
  matched_type_count_6m: number | null;
  matched_type_count_12m: number | null;
  complex_grade: string | null;
  complex_rank: number | null;
  complex_rank_total: number | null;
  grade_window_months: number | null;
  region_grade: string | null;
  direction: TrendDirection;
}

export interface MapTrendResponse {
  base_ym: number | null;
  /** 요청 PNU → 요약. 집계 행이 없는 PNU 는 키 없음. */
  items: Record<string, MapTrend>;
}
