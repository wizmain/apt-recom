import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * /content 랜딩 E2E — 커밋된 posts.json 을 직접 읽어 어서션 구동 (재발행에 견고).
 * posts.json 이 비어 있으면 명시적 실패: 파일럿 발행이 선행 조건 (spec §8).
 * 대상 선정은 테스트별 분리 — 첫 레코드가 CTA 없는 trade_top 이어도 깨지지 않게.
 */
type MinimalCta = {
  id: string;
  label: string;
  nudges: string[];
  sigungu_code: string | null;
  filters: Record<string, number>;
};
type MinimalPost = {
  slug: string;
  status: string;
  series: string;
  title: string;
  hook: string;
  data_as_of: string;
  map_ctas: MinimalCta[];
  items: { name: string; pnu: string | null }[];
};

const posts = JSON.parse(
  readFileSync(path.join(__dirname, "../src/content/instagram/posts.json"), "utf-8"),
) as MinimalPost[];
const published = posts.filter((p) => p.status === "published");
if (published.length === 0) {
  throw new Error("posts.json 에 published 레코드가 없습니다 — 파일럿 발행이 선행 조건");
}
const firstPost = published[0];
const ctaPost = published.find((p) => p.map_ctas.length > 0);
const tradeTopPost = published.find((p) => p.series === "trade_top");

// 제목에 "(서울)" 같은 지역 구분 괄호가 포함될 수 있어 정규식 메타문자로 오인되지
// 않도록 이스케이프한다 (posts.json 은 데이터이므로 정규식 안전성을 코드가 보장).
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test.describe("/content 콘텐츠 랜딩", () => {
  test("목록 페이지 — 발행 콘텐츠 노출", async ({ page }) => {
    const res = await page.goto("/content");
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "콘텐츠" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: new RegExp(escapeRegExp(firstPost.title)) }),
    ).toBeVisible();
  });

  test("상세 렌더 — 훅·기준일·주의 고지", async ({ page }) => {
    // content_view 는 마운트 시 즉시 발화하므로, 네비게이션 전에 리스너를 걸어야
    // 이후 가시성 어서션들이 지나가는 동안 이미 지나간 요청을 놓치지 않는다.
    const viewLog = page.waitForRequest(
      (r) =>
        r.url().includes("/api/log/event") &&
        r.method() === "POST" &&
        JSON.stringify(r.postDataJSON()).includes("content_view"),
    );
    const res = await page.goto(`/content/${firstPost.slug}`);
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: firstPost.hook })).toBeVisible();
    await expect(page.getByText(`데이터 기준일 ${firstPost.data_as_of}`)).toBeVisible();
    await expect(page.getByText("읽을 때 주의할 점")).toBeVisible();
    await viewLog;
  });

  test("unknown slug → 404", async ({ page }) => {
    const res = await page.goto("/content/no-such-slug-000");
    expect(res?.status()).toBe(404);
  });

  test("CTA 클릭 → 홈 딥링크 소비 → 필터 포함 score 호출", async ({ page }) => {
    if (!ctaPost) throw new Error("map_ctas 있는 published 레코드가 없습니다");
    const cta = ctaPost.map_ctas[0];
    await page.goto(`/content/${ctaPost.slug}`);

    const ctaClickLog = page.waitForRequest(
      (r) =>
        r.url().includes("/api/log/event") &&
        r.method() === "POST" &&
        JSON.stringify(r.postDataJSON()).includes("content_map_cta_click"),
    );
    const scoreReq = page.waitForRequest(
      (r) => r.url().includes("/api/nudge/score") && r.method() === "POST",
    );
    const arrivalLog = page.waitForRequest(
      (r) =>
        r.url().includes("/api/log/event") &&
        r.method() === "POST" &&
        JSON.stringify(r.postDataJSON()).includes("content_map_arrival"),
    );

    // inline CTA (본문 첫 번째) 클릭 — sticky 와 라벨이 같으므로 first()
    await page.getByRole("link", { name: cta.label }).first().click();
    await ctaClickLog;

    await expect(page).toHaveURL(/\/$/); // 소비 후 쿼리 제거 (useBridgeParams 규약)
    const scoreBody = (await scoreReq).postDataJSON() as Record<string, unknown>;
    expect(scoreBody).toMatchObject({
      nudges: cta.nudges,
      ...(cta.sigungu_code ? { sigungu_code: cta.sigungu_code } : {}),
      ...cta.filters, // 필터가 score 요청 본문에 flat 전개 (nudgeSlice 계약)
    });
    await arrivalLog;
  });

  test("trade_top — CTA 없음 + 단지 링크만", async ({ page }) => {
    test.skip(!tradeTopPost, "trade_top published 레코드 없음 — 발행 후 자동 활성화");
    if (!tradeTopPost) return;
    await page.goto(`/content/${tradeTopPost.slug}`);
    await expect(page.getByText("신고 최고가 TOP 5")).toBeVisible();
    // 지도 CTA 미노출 (map_ctas=[] — 가짜 의도 금지)
    await expect(page.locator("a[href^='/?nudges=']")).toHaveCount(0);
    // pnu 있는 첫 단지는 상세 링크
    const linked = tradeTopPost.items.find((i) => i.pnu !== null);
    if (linked) {
      await expect(
        page.getByRole("link", { name: linked.name }).first(),
      ).toHaveAttribute("href", `/apartment/${linked.pnu}`);
    }
  });
});
