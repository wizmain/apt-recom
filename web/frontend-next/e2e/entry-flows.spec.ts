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
    // E2 첫 실행 힌트가 fresh context 에서 함께 떠 있으면 first_run_hint_shown
    // 로깅 요청이 아래 waitForRequest(범용 /api/log/event 매처)와 경합한다 —
    // 먼저 닫아 이 테스트의 관심사(nudge_chip_blocked)만 남긴다.
    await page.getByRole("button", { name: "힌트 닫기" }).click();
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

test.describe("E3: 신규거래 배너 → 이 지역 추천", () => {
  test("배너 아이템의 지역 추천 → 지역 태그 + 스코어 호출", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "최근 거래 내역 열기" }).click();

    const scoreReq = page.waitForRequest(
      (r) => r.url().includes("/api/nudge/score") && r.method() === "POST",
    );
    await page.getByRole("button", { name: "서울 종로구 지역 추천 보기" }).click();

    await expect(page.getByText("📍 서울 종로구")).toBeVisible();
    const req = await scoreReq;
    expect(req.postDataJSON()).toMatchObject({
      nudges: ["cost", "commute", "education"],
      sigungu_code: "11110",
    });
  });
});

test.describe("E2: 첫 실행 힌트", () => {
  const HINT_TEXT = "지역 검색";

  test("첫 방문 노출 → ✕ 닫기 → 새로고침 후 미노출 (1회성)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("status").filter({ hasText: HINT_TEXT })).toBeVisible();

    await page.getByRole("button", { name: "힌트 닫기" }).click();
    await expect(page.getByRole("status").filter({ hasText: HINT_TEXT })).toBeHidden();

    await page.reload();
    // localStorage 마킹으로 재노출 없음
    await expect(page.getByRole("button", { name: "집토리 열기" })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: HINT_TEXT })).toBeHidden();
  });

  test("힌트의 둘러보기 링크 → /explore", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "추천 조합 둘러보기 →" }).click();
    await expect(page.getByRole("heading", { name: "라이프스타일 추천 둘러보기" })).toBeVisible();
  });
});

test.describe("D: /explore 큐레이션 갤러리", () => {
  test("프리셋 타일 렌더 — 깨진 행은 제외", async ({ page }) => {
    const res = await page.goto("/explore");
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "라이프스타일 추천 둘러보기" })).toBeVisible();
    await expect(page.getByText("강남구 · 학군과 안전")).toBeVisible();
    await expect(page.getByText("마포구 · 출퇴근과 가성비")).toBeVisible();
    await expect(page.getByText("깨진 프리셋")).toBeHidden();
  });

  test("타일 클릭 → 홈 딥링크 소비 → 지역 태그 + 스코어 호출", async ({ page }) => {
    await page.goto("/explore");
    const scoreReq = page.waitForRequest(
      (r) => r.url().includes("/api/nudge/score") && r.method() === "POST",
    );
    await page.getByRole("link", { name: /강남구 · 학군과 안전/ }).click();

    await expect(page.getByText("📍 강남구")).toBeVisible();
    const req = await scoreReq;
    expect(req.postDataJSON()).toMatchObject({
      nudges: ["education", "safety"],
      sigungu_code: "11680",
    });
    // 소비 후 쿼리 제거 (useBridgeParams 규약)
    await expect(page).toHaveURL(/\/$/);
  });

  test("홈 상단바에서 둘러보기 진입", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "추천 둘러보기" }).click();
    await expect(page.getByRole("heading", { name: "라이프스타일 추천 둘러보기" })).toBeVisible();
  });
});
