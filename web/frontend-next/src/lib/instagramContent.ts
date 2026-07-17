// posts.json 정적 import + 로드 시점 전체 검증. 깨진 레코드는 빌드 실패로
// 드러낸다 — 콘텐츠는 게시물 단위 신뢰성이 핵심이라 조용한 skip 금지 (PRD §6-1).
import rawPosts from "@/content/instagram/posts.json";
import type { ContentPost, MapCta, Series } from "@/types/instagramContent";
import { SCHEMA_VERSION } from "@/types/instagramContent";

const SERIES_VALUES: readonly Series[] = [
  "trade_top",
  "compare",
  "value",
  "budget_choice",
  "lifestyle",
];

// useBridgeParams 소비 allowlist와 동일 (FilterState 9키 — searchSlice.ts)
export const FILTER_KEYS = [
  "min_area",
  "max_area",
  "min_price",
  "max_price",
  "min_floor",
  "min_hhld",
  "max_hhld",
  "built_after",
  "built_before",
] as const;

const COVER_IMAGE_PATTERN = /^\/content\/instagram\/[a-z0-9-]+\/cover\.png$/;
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function fail(slug: string, message: string): never {
  throw new Error(`posts.json 검증 실패 [${slug}]: ${message}`);
}

function assertPost(raw: unknown, index: number): ContentPost {
  const p = raw as ContentPost;
  const slug = typeof p.slug === "string" ? p.slug : `#${index}`;
  if (typeof p.slug !== "string" || !SLUG_PATTERN.test(p.slug))
    fail(slug, "slug 형식 오류");
  if (p.schema_version !== SCHEMA_VERSION)
    fail(slug, `schema_version ${p.schema_version} ≠ ${SCHEMA_VERSION}`);
  if (p.status !== "draft" && p.status !== "published") fail(slug, "status 오류");
  if (!SERIES_VALUES.includes(p.series)) fail(slug, `알 수 없는 series: ${p.series}`);
  for (const key of [
    "title",
    "eyebrow",
    "hook",
    "summary",
    "data_as_of",
    "period_label",
    "cover_alt",
  ] as const) {
    if (typeof p[key] !== "string" || p[key].trim() === "")
      fail(slug, `${key} 누락/빈 값`);
  }
  if (p.status === "published" && !p.published_at)
    fail(slug, "published 인데 published_at 없음");
  if (!COVER_IMAGE_PATTERN.test(p.cover_image))
    fail(slug, `cover_image 형식 오류: ${p.cover_image}`);
  if (!Array.isArray(p.items) || p.items.length === 0) fail(slug, "items 비어 있음");
  if (!Array.isArray(p.methodology) || p.methodology.length === 0)
    fail(slug, "methodology 비어 있음");
  if (!Array.isArray(p.caveats) || p.caveats.length === 0)
    fail(slug, "caveats 비어 있음");
  if (!Array.isArray(p.map_ctas)) fail(slug, "map_ctas 배열 아님");
  for (const cta of p.map_ctas) {
    const badKeys = Object.keys(cta.filters ?? {}).filter(
      (k) => !(FILTER_KEYS as readonly string[]).includes(k),
    );
    if (badKeys.length > 0) fail(slug, `filters 허용 외 키: ${badKeys.join(",")}`);
  }
  if (
    (p.series === "compare" || p.series === "budget_choice") &&
    (p.comparison === null || p.items.length < 2 || p.map_ctas.length !== 2)
  )
    fail(slug, "비교형 계약 위반 (comparison/items≥2/map_ctas=2)");
  if (p.series === "trade_top" && (p.secondary_items?.length ?? 0) === 0)
    fail(slug, "trade_top 인데 secondary_items 없음");
  return p;
}

const POSTS: ContentPost[] = (rawPosts as unknown[]).map(assertPost);

export function getPublishedPosts(): ContentPost[] {
  return POSTS.filter((p) => p.status === "published");
}

export function getPublishedPost(slug: string): ContentPost | null {
  return getPublishedPosts().find((p) => p.slug === slug) ?? null;
}

/**
 * 지도 CTA 딥링크 — useBridgeParams 가 1회 소비 (필터 포함).
 * typedRoutes: 반환 타입을 템플릿 리터럴로 명시 (PresetTiles.tsx 선례).
 */
export function buildMapCtaHref(post: ContentPost, cta: MapCta): `/?${string}` {
  const params = new URLSearchParams({ nudges: cta.nudges.join(",") });
  if (cta.sigungu_code) params.set("sigungu_code", cta.sigungu_code);
  if (cta.region_label) params.set("region_label", cta.region_label);
  for (const key of FILTER_KEYS) {
    const value = cta.filters[key];
    if (typeof value === "number" && Number.isFinite(value))
      params.set(key, String(value));
  }
  params.set("content_slug", post.slug);
  params.set("content_cta", cta.id);
  return `/?${params.toString()}`;
}
