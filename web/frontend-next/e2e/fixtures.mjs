/**
 * E2E 스모크 테스트용 캔드 백엔드 응답 (단일 소스).
 *
 * 목표: 컴포넌트가 깨지지 않을 "최소 유효 형태". 차트·목록류는 빈 배열로 두어
 * 의존 컴포넌트(recharts 등) crash 를 피하고, 단지 1건만 실값으로 채워
 * 상세 페이지(`/apartment/[pnu]`)를 검증한다.
 * 실제 백엔드(web/backend/routers/*.py)와 1:1 일치할 필요는 없다.
 *
 * `.mjs` 인 이유: Playwright webServer 가 띄우는 mock 서버(`mock-api.mjs`)는
 * 컴파일 없이 node 로 직접 실행되므로 plain ESM 이어야 한다. 스펙 파일은
 * `allowJs` 로 이 모듈을 그대로 import 한다.
 */

/** 19자리 PNU 패턴(`/^[0-9]{19}$/`)을 만족해야 상세 페이지가 notFound() 하지 않는다. */
export const FIXTURE_PNU = "1111010100100010000";
export const FIXTURE_APT_NAME = "스모크테스트아파트";
export const FIXTURE_APT_ADDRESS = "서울특별시 종로구 청운동 1";

const apartment = {
  pnu: FIXTURE_PNU,
  bld_nm: FIXTURE_APT_NAME,
  lat: 37.5665,
  lng: 126.978,
  total_hhld_cnt: 500,
  sigungu_code: "11110",
};

export const apartments = [apartment];

export const apartmentDetail = {
  basic: {
    ...apartment,
    // GSC 'name 누락' 회귀 재현 케이스: 건축물대장명(bld_nm)이 없고
    // 보정명(display_name)만 있는 단지 — JSON-LD·h1 이 display_name 을 써야 한다.
    bld_nm: null,
    display_name: FIXTURE_APT_NAME,
    new_plat_plc: FIXTURE_APT_ADDRESS,
    plat_plc: FIXTURE_APT_ADDRESS,
    bjd_code: "1111010100",
    use_apr_day: "20100101",
    dong_count: 5,
    max_floor: 20,
    min_area: 59,
    max_area: 114,
    avg_area: 84,
  },
  scores: {},
  facility_summary: {},
  nearby_facilities: null,
  school: null,
  safety: null,
  population: null,
  kapt_info: null,
  mgmt_cost: null,
};

export const tradesResponse = { trades: [], rents: [] };

export const dashboardTrades = { trades: [], rents: [], total: 0 };

/** `NudgeWeights` — { [nudgeId]: { [subtype]: weight } }. 빈 객체면 넛지 비활성. */
export const nudgeWeights = {};

/**
 * common_code 그룹별 fixture — mock-api 가 `/api/codes/:group` 을 그룹별로 응답.
 * nudge 코드/이름은 실 DB(common_code group='nudge')와 동일 체계.
 */
export const nudgeCodes = [
  { code: "cost", name: "가성비", extra: "", sort_order: 1 },
  { code: "commute", name: "출퇴근", extra: "", sort_order: 2 },
  { code: "education", name: "학군", extra: "", sort_order: 3 },
  { code: "newlywed", name: "신혼", extra: "", sort_order: 4 },
  { code: "pet", name: "반려동물", extra: "", sort_order: 5 },
  { code: "senior", name: "시니어", extra: "", sort_order: 6 },
  { code: "investment", name: "투자", extra: "", sort_order: 7 },
  { code: "nature", name: "자연", extra: "", sort_order: 8 },
  { code: "safety", name: "안전", extra: "", sort_order: 9 },
];

/** 배너 "이 지역 추천"이 쓰는 기본 넛지 세트 (실 DB 는 seed_explore_presets.py 가 시드). */
export const recommendDefaultCodes = [
  { code: "cost", name: "가성비", extra: "", sort_order: 1 },
  { code: "commute", name: "출퇴근", extra: "", sort_order: 2 },
  { code: "education", name: "학군", extra: "", sort_order: 3 },
];

/** /explore 갤러리 프리셋. broken_preset 은 파서가 건너뛰어야 할 깨진 행(고의). */
export const explorePresetCodes = [
  {
    code: "gangnam_edu",
    name: "강남구 · 학군과 안전",
    extra: JSON.stringify({
      emoji: "🏫",
      description: "학군과 치안을 모두 잡는 강남 라이프",
      nudges: ["education", "safety"],
      sigungu_code: "11680",
      region_label: "강남구",
    }),
    sort_order: 1,
  },
  {
    code: "mapo_value",
    name: "마포구 · 출퇴근과 가성비",
    extra: JSON.stringify({
      emoji: "🚇",
      description: "도심 접근성과 합리적인 가격",
      nudges: ["commute", "cost"],
      sigungu_code: "11440",
      region_label: "마포구",
    }),
    sort_order: 2,
  },
  { code: "broken_preset", name: "깨진 프리셋", extra: "not-json", sort_order: 99 },
];

export const codesByGroup = {
  nudge: nudgeCodes,
  recommend_default: recommendDefaultCodes,
  explore_preset: explorePresetCodes,
};

/** `/api/dashboard/recent` — RecentTradesBanner 렌더 + E3 "이 지역 추천" 검증용. */
export const dashboardRecent = [
  {
    apt_nm: FIXTURE_APT_NAME,
    sgg_cd: "11110",
    sigungu: "서울 종로구",
    area: 84.9,
    floor: 10,
    date: "2026.07.01",
    price: 120000,
    pnu: FIXTURE_PNU,
    lat: 37.5665,
    lng: 126.978,
    bld_nm: FIXTURE_APT_NAME,
  },
];

export const chatFeedbackStats = { total: 0, helpful: 0, not_helpful: 0 };

/**
 * `/api/apartments/search` — 단일 지역(sigungu) 매칭 응답.
 * 검색 Enter → 즉시 지역 선택되는 경로(E1 코치 자동 종료/재노출 방지 검증)에 사용.
 * 프론트 계약: results[].match_type === 'region' + sigungu_code → selectRegion.
 */
export const FIXTURE_REGION_LABEL = "서울 종로구";

export const searchRegionResponse = {
  results: [
    {
      pnu: "",
      bld_nm: "",
      lat: null,
      lng: null,
      new_plat_plc: null,
      match_type: "region",
      region_label: FIXTURE_REGION_LABEL,
      sigungu_code: "11110",
    },
  ],
  region_candidates: [],
};
