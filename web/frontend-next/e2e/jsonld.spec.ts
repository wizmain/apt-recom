import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { FIXTURE_PNU } from "./fixtures.mjs";

/**
 * 구조화 데이터(JSON-LD) 배포 게이트.
 *
 * GSC 에서 '탐색경로 name/item.name 누락' 오류가 반복 보고된 이력이 있어,
 * 렌더된 모든 ld+json 을 파싱해 필수 이름 필드를 검증한다. 템플릿이
 * nullable 필드를 name 에 직접 쓰면 이 게이트가 배포 전에 잡는다.
 * (apartment 픽스처는 bld_nm=null + display_name 케이스로 회귀를 상시 재현.)
 */

type JsonLdNode = Record<string, unknown>;

function collectNodes(node: unknown, out: JsonLdNode[] = []): JsonLdNode[] {
  if (Array.isArray(node)) {
    for (const child of node) collectNodes(child, out);
    return out;
  }
  if (node !== null && typeof node === "object") {
    out.push(node as JsonLdNode);
    for (const value of Object.values(node)) collectNodes(value, out);
  }
  return out;
}

function isNonEmptyString(value: unknown): boolean {
  return typeof value === "string" && value.trim() !== "";
}

function assertJsonLdNames(raw: string, url: string): void {
  const nodes = collectNodes(JSON.parse(raw));
  for (const node of nodes) {
    const type = node["@type"];
    if (type === "ListItem") {
      expect
        .soft(
          isNonEmptyString(node.name),
          `${url}: ListItem.name 누락 — ${JSON.stringify(node)}`,
        )
        .toBe(true);
      expect
        .soft(
          isNonEmptyString(node.item) || isNonEmptyString(node.url),
          `${url}: ListItem.item/url 누락 — ${JSON.stringify(node)}`,
        )
        .toBe(true);
    }
    if (type === "BreadcrumbList" || type === "ItemList") {
      expect
        .soft(
          Array.isArray(node.itemListElement) && node.itemListElement.length > 0,
          `${url}: ${type}.itemListElement 비어 있음`,
        )
        .toBe(true);
    }
    if (type === "ApartmentComplex") {
      expect
        .soft(isNonEmptyString(node.name), `${url}: ApartmentComplex.name 누락`)
        .toBe(true);
    }
    if (type === "Article") {
      expect
        .soft(isNonEmptyString(node.headline), `${url}: Article.headline 누락`)
        .toBe(true);
    }
  }
}

// 커밋된 posts.json 기반 — 첫 published 콘텐츠 상세도 검증 대상에 포함.
const posts = JSON.parse(
  readFileSync(path.join(__dirname, "../src/content/instagram/posts.json"), "utf-8"),
) as { slug: string; status: string }[];
const firstContentSlug = posts.find((p) => p.status === "published")?.slug;

const PAGES: string[] = [
  `/apartment/${FIXTURE_PNU}`,
  "/region",
  ...(firstContentSlug ? [`/content/${firstContentSlug}`] : []),
];

test.describe("JSON-LD 구조화 데이터 게이트", () => {
  for (const url of PAGES) {
    test(`${url} — name/item 필수 필드 검증`, async ({ page }) => {
      const res = await page.goto(url);
      expect(res?.status()).toBe(200);
      const scripts = await page
        .locator('script[type="application/ld+json"]')
        .allTextContents();
      expect(scripts.length, `${url}: ld+json 스크립트 없음`).toBeGreaterThan(0);
      for (const raw of scripts) assertJsonLdNames(raw, url);
    });
  }
});
