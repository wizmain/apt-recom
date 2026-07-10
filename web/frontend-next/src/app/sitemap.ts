import type { MetadataRoute } from "next";
import { API_URL, SITE_URL } from "@/lib/site";

/**
 * /sitemap.xml — Next.js 16 MetadataRoute.Sitemap 규약.
 *
 * 전략
 * - 백엔드(api.apt-recom.kr)의 `/sitemap.xml` 을 fetch 해 `<loc>` 목록만 추출.
 *   백엔드는 이미 좌표 있는 유효 PNU 만 필터링해 30k+ URL 을 반환.
 * - <loc> 에는 백엔드가 생성한 host(=SITE_URL)가 들어 있으므로 경로만 재작성 없이 그대로 사용.
 *   (다른 host 가 들어있어도 SITE_URL 로 정규화하는 방어 코드 포함.)
 * - `revalidate` 로 1시간 캐시 → Next.js 가 Route Handler 를 ISR.
 *
 * 빌드 시 백엔드가 닿지 않으면 홈 URL 만 포함한 최소 sitemap 을 반환해 빌드 실패 회피.
 *
 * Output Content-Type 은 Next.js 가 자동 `application/xml`.
 */

export const revalidate = 3600;

// <url> 블록 단위로 loc + (선택) lastmod 추출 — 백엔드가 최근 실거래일을
// lastmod 로 내려주므로 그대로 통과시켜 크롤러 재수집 효율을 살린다.
const URL_BLOCK_REGEX =
  /<url><loc>([^<]+)<\/loc>(?:<lastmod>([^<]+)<\/lastmod>)?<\/url>/g;

type UpstreamUrl = { loc: string; lastmod?: string };

async function fetchUpstreamUrls(): Promise<UpstreamUrl[]> {
  try {
    const res = await fetch(`${API_URL}/sitemap.xml`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    const xml = await res.text();
    return [...xml.matchAll(URL_BLOCK_REGEX)].map((m) => ({
      loc: m[1],
      lastmod: m[2],
    }));
  } catch {
    return [];
  }
}

function normalizeToSiteHost(urlStr: string): string {
  try {
    const u = new URL(urlStr);
    // 백엔드가 반환한 host 와 SITE_URL 이 다르면 SITE_URL 로 정규화.
    const site = new URL(SITE_URL);
    if (u.host !== site.host) {
      return `${site.origin}${u.pathname}${u.search}`;
    }
    return urlStr;
  } catch {
    // URL 파싱 실패 시 원본 유지
    return urlStr;
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const urls = await fetchUpstreamUrls();

  // 백엔드가 비어 있거나 실패한 경우 최소 홈 URL 만.
  if (urls.length === 0) {
    return [{ url: `${SITE_URL}/`, changeFrequency: "daily", priority: 1.0 }];
  }

  // `/about` 같은 정적 페이지는 백엔드 sitemap 에 없으므로 수동 추가.
  // 홈 URL 은 이미 백엔드가 생성(=SITE_URL/)하지만, normalize 과정에서 정돈.
  const normalized: UpstreamUrl[] = urls.map((u) => ({
    loc: normalizeToSiteHost(u.loc),
    lastmod: u.lastmod,
  }));
  const staticPages: UpstreamUrl[] = [
    { loc: `${SITE_URL}/about` },
    { loc: `${SITE_URL}/guide` },
    { loc: `${SITE_URL}/explore` },
  ];

  const seen = new Set<string>();
  const merged: MetadataRoute.Sitemap = [];
  for (const u of [...normalized, ...staticPages]) {
    if (seen.has(u.loc)) continue;
    seen.add(u.loc);
    merged.push({ url: u.loc, ...(u.lastmod ? { lastModified: u.lastmod } : {}) });
  }
  return merged;
}
