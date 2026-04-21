/**
 * Cloudflare Pages Function: `/sitemap.xml` 프록시.
 *
 * sitemaps.org 프로토콜 상 sitemap.xml 은 그 안의 URL 과 같은 host 에서 서빙되어야 한다.
 * 집토리는 프론트(apt-recom.kr)와 백엔드(api.apt-recom.kr)가 분리돼 있어, 백엔드의 동적
 * sitemap 을 프론트 host 에서 그대로 노출한다.
 *
 * `_redirects` 의 `/sitemap.xml  https://api... 200` rewrite 도 동일 의도이나,
 * Cloudflare Pages 의 외부 host rewrite 는 동작이 보장되지 않는 경우가 있다
 * (환경·경로별 차이). Pages Function 은 명시적 fetch 로 어떤 환경에서도 동일하게 동작
 * 하므로 이쪽을 정식 경로로 쓴다. Pages Function 이 존재하면 `_redirects` 보다 우선하므로
 * 자동으로 여기가 실행된다.
 */

// @cloudflare/workers-types 를 별도 설치하지 않기 위해 PagesFunction 타입 없이 기본 Web API 로만 작성.
// Cloudflare 의 `cf` fetch 옵션은 표준 RequestInit 에 없으므로 RequestInit 캐스팅으로 주입한다.
export const onRequestGet = async (): Promise<Response> => {
  const upstream = 'https://api.apt-recom.kr/sitemap.xml';

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream, {
      cf: {
        // CF edge 캐시: 동일 응답을 1시간 재사용 → 백엔드 부하 최소화.
        cacheTtl: 3600,
        cacheEverything: true,
      },
    } as RequestInit);
  } catch (err) {
    return new Response(`sitemap upstream unreachable: ${String(err)}`, {
      status: 502,
      headers: { 'content-type': 'text/plain; charset=utf-8' },
    });
  }

  if (!upstreamRes.ok) {
    return new Response(`sitemap upstream error: ${upstreamRes.status}`, {
      status: 502,
      headers: { 'content-type': 'text/plain; charset=utf-8' },
    });
  }

  // 백엔드의 스트리밍 body 를 그대로 재사용하되, 응답 헤더는 프론트 관점으로 재지정한다.
  return new Response(upstreamRes.body, {
    status: 200,
    headers: {
      'content-type': 'application/xml; charset=utf-8',
      'cache-control': 'public, max-age=3600, s-maxage=3600',
    },
  });
};
