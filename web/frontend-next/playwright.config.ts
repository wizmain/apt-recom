import { defineConfig, devices } from "@playwright/test";

/**
 * web/frontend-next E2E 스모크 설정.
 *
 * 의존성 업그레이드(React/Next 등) 회귀 방지가 1차 목적이라 가볍게 유지한다.
 *
 * webServer 2개를 순차 기동:
 *   1) e2e/mock-api.mjs — 캔드 백엔드 (실 FastAPI·DB 불필요)
 *   2) next dev         — NEXT_PUBLIC_API_URL 을 mock 으로 주입해 기동
 *
 * 실행 전 1회: `npx playwright install chromium`
 * 실행: `npm run e2e`  (개별: `npx playwright test`)
 */

const APP_PORT = Number(process.env.E2E_APP_PORT ?? 3100);
const MOCK_PORT = Number(process.env.E2E_MOCK_PORT ?? 8788);
const BASE_URL = `http://localhost:${APP_PORT}`;
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: isCI ? "github" : "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: `node e2e/mock-api.mjs`,
      url: `http://localhost:${MOCK_PORT}/healthz`,
      reuseExistingServer: !isCI,
      stdout: "pipe",
      env: { MOCK_API_PORT: String(MOCK_PORT) },
    },
    {
      command: `npx next dev --port ${APP_PORT}`,
      url: BASE_URL,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_URL: `http://localhost:${MOCK_PORT}`,
        NEXT_PUBLIC_SITE_URL: BASE_URL,
      },
    },
  ],
});
