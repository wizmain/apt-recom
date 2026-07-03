/**
 * E2E 스모크용 mock 백엔드.
 *
 * Playwright webServer 가 `next dev` 보다 먼저 기동하며, `next dev` 는
 * `NEXT_PUBLIC_API_URL=http://localhost:<MOCK_PORT>` 로 이 서버를 바라본다.
 * 실 백엔드(FastAPI)·로컬 DB 없이 프론트 렌더 경로를 결정적으로 검증하기 위함.
 *
 * 라우팅 규칙: 정확 일치 → 접두어/패턴 일치 → catch-all(빈 배열). 모든 응답 200.
 * (404/500 을 내보내면 프론트가 에러 상태로 빠져 스모크 신호가 흐려진다.)
 *
 * 프론트는 별도 origin(`next dev`)에서 이 서버로 cross-origin 호출하며 axios 가
 * `X-Device-Id` 헤더를 붙여 CORS preflight 가 발생하므로, 모든 응답에 와일드카드
 * CORS 헤더를 부여하고 OPTIONS 는 204 로 즉답한다.
 */
import { createServer } from "node:http";
import {
  apartments,
  apartmentDetail,
  tradesResponse,
  dashboardTrades,
  nudgeWeights,
  codesByGroup,
  dashboardRecent,
  chatFeedbackStats,
  searchRegionResponse,
} from "./fixtures.mjs";

const PORT = Number(process.env.MOCK_API_PORT ?? 8788);

const SITEMAP_XML =
  '<?xml version="1.0" encoding="UTF-8"?>\n' +
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n';

/** path(쿼리 제외) → JSON 응답 본문. 함수면 동적 계산. */
function resolveBody(pathname) {
  // 정확 일치 라우트
  const exact = {
    "/healthz": "ok",
    "/api/apartments": apartments,
    "/api/apartments/search": searchRegionResponse,
    "/api/dashboard/regions": [],
    "/api/dashboard/summary": {},
    "/api/dashboard/trend": [],
    "/api/dashboard/ranking": [],
    "/api/dashboard/recent": dashboardRecent,
    "/api/dashboard/trades": dashboardTrades,
    "/api/nudge/weights": nudgeWeights,
    "/api/nudge/score": [],
    "/api/chat/feedback": { ok: true },
    "/api/chat/feedback/stats": chatFeedbackStats,
    "/api/chat/stream": "",
    "/api/log/event": { ok: true },
  };
  if (pathname in exact) return exact[pathname];

  // 패턴 라우트 — 거래이력이 단지 상세보다 먼저(접두어 충돌 회피)
  if (/^\/api\/apartment\/[^/]+\/trades$/.test(pathname)) return tradesResponse;
  if (/^\/api\/apartment\/[^/]+$/.test(pathname)) return apartmentDetail;

  // 공통코드 — 그룹별 fixture, 미정의 그룹은 빈 배열
  const codesMatch = pathname.match(/^\/api\/codes(?:\/([^/]+))?$/);
  if (codesMatch) {
    const group = codesMatch[1];
    if (!group) {
      return Object.entries(codesByGroup).map(([group_id, items]) => ({
        group_id,
        cnt: items.length,
      }));
    }
    return codesByGroup[group] ?? [];
  }

  // catch-all: 미정의 엔드포인트는 빈 배열(목록류 가정)
  return [];
}

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-allow-headers": "*",
  "access-control-max-age": "86400",
};

const server = createServer((req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS_HEADERS);
    res.end();
    return;
  }

  const pathname = new URL(req.url, `http://localhost:${PORT}`).pathname;

  if (pathname === "/sitemap.xml") {
    res.writeHead(200, { ...CORS_HEADERS, "content-type": "application/xml; charset=utf-8" });
    res.end(SITEMAP_XML);
    return;
  }

  const body = resolveBody(pathname);
  if (typeof body === "string") {
    res.writeHead(200, { ...CORS_HEADERS, "content-type": "text/plain; charset=utf-8" });
    res.end(body);
    return;
  }
  res.writeHead(200, { ...CORS_HEADERS, "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
});

server.listen(PORT, () => {
  console.log(`[e2e mock-api] listening on http://localhost:${PORT}`);
});
