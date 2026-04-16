/**
 * Cloudflare Pages Function — /api/* 요청을 Railway 백엔드로 프록시.
 *
 * 같은 도메인(/api/...)에서 호출되어 CORS 부담이 없고,
 * Authorization 등 모든 요청 헤더/메서드/본문을 그대로 forward한다.
 *
 * _redirects 의 외부 도메인 splat 프록시는 Cloudflare Pages 에서
 * 정상 동작하지 않아 Functions 로 처리한다.
 */

const RAILWAY_BASE = "https://apt-recom-production.up.railway.app";

export const onRequest: PagesFunction = async ({ request }) => {
  const url = new URL(request.url);
  const target = RAILWAY_BASE + url.pathname + url.search;
  // request 객체를 그대로 넘겨 method/headers/body 를 보존.
  return fetch(new Request(target, request));
};
