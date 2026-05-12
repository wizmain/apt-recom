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

/** `/api/codes/:group` — region selector 옵션. 빈 배열이어도 UI 는 깨지지 않는다. */
export const codes = [];

export const chatFeedbackStats = { total: 0, helpful: 0, not_helpful: 0 };
