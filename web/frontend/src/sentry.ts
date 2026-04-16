/**
 * Sentry 초기화 (DSN이 설정된 환경에서만 활성화).
 * main.tsx 에서 가장 먼저 import 하여 부수효과로 init.
 */
import * as Sentry from '@sentry/react';

const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;

if (dsn) {
  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_GIT_COMMIT_SHA as string | undefined,
    // 무료 티어 절감을 위해 보수적 샘플링
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 1.0,
    integrations: [Sentry.browserTracingIntegration()],
  });
  console.info('[sentry] initialized');
}

export { Sentry };
