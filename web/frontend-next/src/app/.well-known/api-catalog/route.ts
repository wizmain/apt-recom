import { NextResponse } from "next/server";

/**
 * `/.well-known/api-catalog` — RFC 9727 (well-known URI for API discovery) +
 * RFC 9264 (linkset) + RFC 8631 (link relations) 형식의 API 카탈로그.
 *
 * Cloudflare/agent 가 자동으로 발견할 수 있도록 단일 API endpoint(apt-recom 백엔드)
 * 에 대해 service-desc(OpenAPI), service-doc(Swagger), status(health) 링크를 노출.
 *
 * `NextResponse.json()` 은 Content-Type 을 `application/json` 으로 강제하므로
 * RFC 9727 권장 `application/linkset+json; profile="…rfc9727"` 부착을 위해
 * raw `NextResponse` + `JSON.stringify` 로 직렬화.
 */

const API_BASE = "https://api.apt-recom.kr";

const LINKSET = {
  linkset: [
    {
      anchor: API_BASE,
      "service-desc": [
        { href: `${API_BASE}/openapi.json`, type: "application/json" },
      ],
      "service-doc": [
        { href: `${API_BASE}/docs`, type: "text/html" },
      ],
      status: [
        { href: `${API_BASE}/api/health`, type: "application/json" },
      ],
    },
  ],
};

export const dynamic = "force-static";
export const revalidate = false;

export function GET() {
  return new NextResponse(JSON.stringify(LINKSET), {
    headers: {
      "Content-Type":
        'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
      "Cache-Control": "public, max-age=3600",
    },
  });
}
