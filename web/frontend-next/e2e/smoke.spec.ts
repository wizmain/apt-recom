import { test, expect, type Page } from "@playwright/test";
import { FIXTURE_PNU, FIXTURE_APT_NAME } from "./fixtures.mjs";

/**
 * web/frontend-next 스모크 — 의존성 업그레이드(React/Next 등) 회귀 방지.
 *
 * 각 라우트가 (1) 200 으로 응답하고 (2) 핵심 UI 가 렌더되며 (3) 처리되지 않은
 * 런타임 예외(pageerror)나 치명적 React 콘솔 에러(hydration mismatch / minified
 * React error)를 내지 않는지 확인한다. 데이터는 e2e/mock-api.mjs 가 캔드 응답으로
 * 채우므로 실 백엔드·DB 가 필요 없다.
 */

/** "앱이 깨졌다" 신호로 취급할 콘솔 에러 패턴 (그 외 dev 모드 잡음은 무시). */
const FATAL_CONSOLE_PATTERNS = [
  /hydrat/i,
  /Minified React error/i,
  /Maximum update depth exceeded/i,
];

type ErrorSink = { pageErrors: string[]; fatalConsole: string[] };

/** 페이지의 미처리 예외·치명적 콘솔 에러를 수집한다. goto 이전에 호출할 것. */
function watchErrors(page: Page): ErrorSink {
  const sink: ErrorSink = { pageErrors: [], fatalConsole: [] };
  page.on("pageerror", (err) => sink.pageErrors.push(err.message));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (FATAL_CONSOLE_PATTERNS.some((re) => re.test(text))) {
      sink.fatalConsole.push(text);
    }
  });
  return sink;
}

function assertNoFatalErrors(sink: ErrorSink) {
  expect(sink.pageErrors, `uncaught page errors:\n${sink.pageErrors.join("\n")}`).toEqual([]);
  expect(sink.fatalConsole, `fatal console errors:\n${sink.fatalConsole.join("\n")}`).toEqual([]);
}

test.describe("frontend-next 스모크", () => {
  test("홈(/) — 200 + 핵심 UI 렌더", async ({ page }) => {
    const sink = watchErrors(page);
    const res = await page.goto("/");
    expect(res?.status()).toBe(200);
    await expect(page).toHaveTitle(/집토리/);
    // 결과 없음 상태 → 챗봇 FAB 노출
    await expect(page.getByRole("button", { name: "집토리 열기" })).toBeVisible();
    assertNoFatalErrors(sink);
  });

  test("챗봇 패널 토글", async ({ page }) => {
    const sink = watchErrors(page);
    await page.goto("/");
    await page.getByRole("button", { name: "집토리 열기" }).click();
    await expect(page.getByPlaceholder("메시지를 입력하세요...")).toBeVisible();
    // 토글 상태 반영 확인
    await expect(page.getByRole("button", { name: "채팅 닫기" })).toBeVisible();
    assertNoFatalErrors(sink);
  });

  test("/guide — 200 + 헤딩 렌더", async ({ page }) => {
    const sink = watchErrors(page);
    const res = await page.goto("/guide");
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "집토리 사용 가이드" })).toBeVisible();
    assertNoFatalErrors(sink);
  });

  test("/about — 200 + 헤딩 렌더", async ({ page }) => {
    const sink = watchErrors(page);
    const res = await page.goto("/about");
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "집토리 서비스 소개" })).toBeVisible();
    assertNoFatalErrors(sink);
  });

  test("/apartment/[pnu] — 200 + 단지명 렌더 (SSR fetch → mock)", async ({ page }) => {
    const sink = watchErrors(page);
    const res = await page.goto(`/apartment/${FIXTURE_PNU}`);
    expect(res?.status()).toBe(200);
    await expect(page.getByText(FIXTURE_APT_NAME).first()).toBeVisible();
    // 홈 밖 SSR 페이지 공용 네비 (막다른 길 방지 — SiteNav)
    await expect(page.getByRole("link", { name: /실거래 대시보드/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /콘텐츠/ })).toBeVisible();
    assertNoFatalErrors(sink);
  });

  test("robots.txt / sitemap.xml — 200", async ({ request }) => {
    expect((await request.get("/robots.txt")).status()).toBe(200);
    expect((await request.get("/sitemap.xml")).status()).toBe(200);
  });
});
