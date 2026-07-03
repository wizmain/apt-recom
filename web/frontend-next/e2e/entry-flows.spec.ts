import { test, expect } from "@playwright/test";
import { FIXTURE_REGION_LABEL } from "./fixtures.mjs";

/**
 * 진입 마찰 제거(E) + 큐레이션 갤러리(D) 플로우 검증.
 * 데이터는 e2e/mock-api.mjs 캔드 응답 — 실 백엔드·DB 불필요.
 * 스펙: docs/prd/2026-07-03-entry-barrier-reduction-proposals.md §5-6
 */

const COACH_TEXT = "지역을 먼저 검색하면 라이프스타일 추천이 켜져요";

test.describe("E1: 비활성 넛지 칩 → 인라인 코치", () => {
  test("alert 없이 코치 노출 + nudge_chip_blocked 로깅", async ({ page }) => {
    let dialogAppeared = false;
    page.on("dialog", async (d) => {
      dialogAppeared = true;
      await d.dismiss();
    });

    await page.goto("/");
    const logReq = page.waitForRequest(
      (r) => r.url().includes("/api/log/event") && r.method() === "POST",
    );
    await page.getByRole("button", { name: "가성비" }).filter({ visible: true }).first().click();

    await expect(page.getByText(COACH_TEXT)).toBeVisible();
    expect(dialogAppeared).toBe(false);
    const req = await logReq;
    expect(req.postDataJSON()).toMatchObject({
      event_type: "nudge_chip_blocked",
      payload: { nudge_id: "cost" },
    });
  });

  test("코치 ✕ 로 닫기", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "가성비" }).filter({ visible: true }).first().click();
    await expect(page.getByText(COACH_TEXT)).toBeVisible();
    await page.getByRole("button", { name: "안내 닫기" }).click();
    await expect(page.getByText(COACH_TEXT)).toBeHidden();
  });

  test("지역 해제 후 코치가 무단 재노출되지 않음", async ({ page }) => {
    await page.goto("/");

    // 1. 비활성 칩 클릭 → 코치 노출
    await page.getByRole("button", { name: "가성비" }).filter({ visible: true }).first().click();
    await expect(page.getByText(COACH_TEXT)).toBeVisible();

    // 2. 지역 검색·선택 → hasAnyKeyword true → 코치 숨김
    const searchInput = page.getByPlaceholder("지역명·단지명 (Enter)");
    await searchInput.fill("종로구");
    await searchInput.press("Enter");
    await expect(page.getByText(FIXTURE_REGION_LABEL)).toBeVisible();
    await expect(page.getByText(COACH_TEXT)).toBeHidden();

    // 3. 지역 해제 → 조건이 다시 비어도, 칩 재클릭 전에는 코치가 다시 나오면 안 된다
    await page.getByRole("button", { name: "지역 필터 해제" }).click();
    await expect(page.getByText(FIXTURE_REGION_LABEL)).toBeHidden();
    await expect(page.getByText(COACH_TEXT)).toBeHidden();
  });
});
