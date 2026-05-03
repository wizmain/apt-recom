/**
 * WebMCP tool 정의 + 등록 — AI 에이전트가 브라우저에서 사이트 핵심 액션을 호출.
 *
 * spec: https://webmachinelearning.github.io/webmcp/
 * 검증: POST https://isitagentready.com/api/scan { "url": "<site>" }
 *       → response.checks.discovery.webMcp.status === "pass"
 */

import { api } from "@/lib/api";
import type { ModelContextTool } from "@/types/webmcp";

type Json = Record<string, unknown>;

async function apiGet(path: string, params?: Json): Promise<unknown> {
  const res = await api.get(path, { params });
  return res.data;
}

const searchApartments: ModelContextTool<{ query: string }> = {
  name: "search_apartments",
  title: "아파트 검색",
  description:
    "키워드(단지명·지역명·도로명·지번)로 아파트를 검색합니다. 결과는 단지 목록과, 동일 명칭 지역이 여러 곳일 경우 후보 지역 목록을 함께 반환합니다.",
  inputSchema: {
    type: "object",
    properties: {
      query: {
        type: "string",
        minLength: 1,
        description: "검색어 (예: '래미안', '서초구', '광안해변로 100')",
      },
    },
    required: ["query"],
    additionalProperties: false,
  },
  annotations: { readOnlyHint: true },
  execute: async ({ query }) => apiGet("/api/apartments/search", { q: query }),
};

const getApartmentDetail: ModelContextTool<{ pnu: string }> = {
  name: "get_apartment_detail",
  title: "아파트 상세 정보",
  description:
    "PNU(필지 식별자)로 단지의 상세 정보를 조회합니다. 주소·세대수·동수·최고층·좌표·시설/안전/가격 점수 등을 포함.",
  inputSchema: {
    type: "object",
    properties: {
      pnu: {
        type: "string",
        description: "단지의 PNU (19자리 필지 코드)",
      },
    },
    required: ["pnu"],
    additionalProperties: false,
  },
  annotations: { readOnlyHint: true },
  execute: async ({ pnu }) => apiGet(`/api/apartment/${encodeURIComponent(pnu)}`),
};

const getApartmentTrades: ModelContextTool<{ pnu: string }> = {
  name: "get_apartment_trades",
  title: "아파트 거래 이력",
  description:
    "특정 단지(PNU)의 매매·전월세 거래 이력을 조회합니다.",
  inputSchema: {
    type: "object",
    properties: {
      pnu: {
        type: "string",
        description: "단지의 PNU",
      },
    },
    required: ["pnu"],
    additionalProperties: false,
  },
  annotations: { readOnlyHint: true },
  execute: async ({ pnu }) =>
    apiGet(`/api/apartment/${encodeURIComponent(pnu)}/trades`),
};

const getRecentTrades: ModelContextTool<{
  type?: "trade" | "rent";
  sigungu?: string;
  limit?: number;
}> = {
  name: "get_recent_trades",
  title: "최근 거래 목록",
  description:
    "전국 또는 특정 시군구의 최근 매매/전월세 거래 목록을 조회합니다.",
  inputSchema: {
    type: "object",
    properties: {
      type: {
        type: "string",
        enum: ["trade", "rent"],
        description: "거래 유형 (기본 trade)",
      },
      sigungu: {
        type: "string",
        description: "시군구 코드 5자리 (선택, 미지정 시 전국)",
      },
      limit: {
        type: "integer",
        minimum: 1,
        maximum: 100,
        description: "최대 반환 건수 (기본 20, 최대 100)",
      },
    },
    additionalProperties: false,
  },
  annotations: { readOnlyHint: true },
  execute: async ({ type, sigungu, limit }) => {
    const params: Json = { type: type ?? "trade", limit: limit ?? 20 };
    if (sigungu) params.sigungu = sigungu;
    return apiGet("/api/dashboard/recent", params);
  },
};

const navigateToApartment: ModelContextTool<{ pnu: string }> = {
  name: "navigate_to_apartment",
  title: "단지 상세 페이지로 이동",
  description:
    "지정한 PNU 의 단지 상세 페이지(/apartment/{pnu})로 브라우저를 이동시킵니다.",
  inputSchema: {
    type: "object",
    properties: {
      pnu: {
        type: "string",
        description: "이동할 단지의 PNU",
      },
    },
    required: ["pnu"],
    additionalProperties: false,
  },
  annotations: { readOnlyHint: false },
  execute: async ({ pnu }) => {
    const url = `/apartment/${encodeURIComponent(pnu)}`;
    window.location.assign(url);
    return { navigated: true, url };
  },
};

export const WEBMCP_TOOLS: ModelContextTool[] = [
  searchApartments as ModelContextTool,
  getApartmentDetail as ModelContextTool,
  getApartmentTrades as ModelContextTool,
  getRecentTrades as ModelContextTool,
  navigateToApartment as ModelContextTool,
];

export function registerWebMcpTools(signal: AbortSignal): boolean {
  if (typeof navigator === "undefined") return false;
  const ctx = navigator.modelContext;
  if (!ctx?.registerTool) return false;
  for (const tool of WEBMCP_TOOLS) {
    ctx.registerTool(tool, { signal });
  }
  return true;
}
