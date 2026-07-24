/**
 * 지역 허브 페이지(/region, /region/[code]) 도메인 타입 — 서버 컴포넌트 fetch 전용.
 *
 * 필드는 실제 로컬 백엔드 응답(curl 실측, 2026-07-09)을 기준으로 정의했다.
 * DB 원본 컬럼명을 그대로 사용하는 detail.py 계열과 달리 dashboard.py 는 이미
 * 가공된 응답을 주므로 그대로 반영한다.
 */

/**
 * GET /api/dashboard/regions 응답 원소.
 * name 은 "강남구(서울)" 형식 — 괄호 안은 대부분 시도명이지만, 동일 지명이
 * 여러 시도에 겹치는 경우(예: "덕진구(전주)")에는 상위 시명이 들어간다.
 * common_code.extra 원본값을 그대로 노출하는 것이라 grain 이 섞여 있다.
 */
export interface RegionListItem {
  code: string;
  name: string;
  /**
   * 노출 가능한 단지 수 — /apartments 목록과 동일 기준
   * (backend APARTMENT_VISIBLE_CONDITIONS 공유). 0이면 빈 지역
   * (강원·전북 신구 행정코드 이원화의 구코드 등).
   * optional: 구 API(필드 부재)·롤아웃 중에는 undefined — 프론트/백엔드
   * 배포 순서에 의존하지 않도록 부재를 허용한다.
   */
  apt_count?: number;
}

/** parseRegionName() 결과 — h1/breadcrumb 표시용. */
export interface ParsedRegionName {
  /** "강남구" */
  district: string;
  /** "서울" | "청주" 등 — 시도명 또는 상위 시명 (extra 원본, 없으면 빈 문자열) */
  parent: string;
}

/** GET /api/dashboard/summary?sigungu={code} 응답 (routers/dashboard.py:dashboard_summary). */
export interface DashboardSummary {
  current_period: string;
  prev_period: string;
  /** "전년 동기" — comparison_mode=yoy 고정 (MoM 아님, 문구 그대로 사용할 것) */
  prev_label: string;
  comparison_mode: string;
  last_updated: string | null;
  new_today: number;
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

/**
 * GET /api/dashboard/trend?sigungu={code}&months= 응답 원소.
 * trade_avg_price_m2 는 평균가(avg) — dashboard_summary 의 median_price_m2 와
 * 달리 중위값이 아니므로 화면 라벨을 "평균가"로 구분해 표기해야 한다.
 */
export interface TrendMonth {
  month: string;
  trade_volume: number;
  trade_avg_price: number;
  trade_avg_price_m2: number;
  rent_volume: number;
  rent_avg_deposit: number;
  jeonse_ratio: number;
}

/** GET /api/dashboard/recent?sigungu={code}&limit= 응답 원소 (type=trade 기본값). */
export interface RecentTrade {
  apt_nm: string;
  sgg_cd: string;
  sigungu: string;
  area: number | null;
  floor: number | null;
  date: string;
  /** trade_apt_mapping 매핑 실패 시 null — 상세 링크 없이 텍스트만 렌더 */
  pnu: string | null;
  lat: number | null;
  lng: number | null;
  bld_nm: string | null;
  price: number;
}

/**
 * apartment/[pnu] 상세 페이지 ↔ _view.tsx 가 공유하는 지역 링크 계약.
 * page.tsx 의 resolveRegion() 결과 — breadcrumb·"지역 아파트 더보기" 링크에 사용.
 * 두 파일 모두에서 변경될 가능성이 높아 route 내부가 아닌 공용 타입으로 정의.
 */
export interface ResolvedRegion {
  code: string;
  label: string;
}

/** GET /api/apartments?sigungu_code={code} 응답 원소. */
export interface RegionApartment {
  pnu: string;
  bld_nm: string;
  lat: number;
  lng: number;
  total_hhld_cnt: number;
  sigungu_code: string;
  max_floor: number | null;
  /** "20040703" (YYYYMMDD) */
  use_apr_day: string | null;
  area_min: number | null;
  area_max: number | null;
  avg_area: number | null;
  price_per_m2: number | null;
  jeonse_ratio: number | null;
}
