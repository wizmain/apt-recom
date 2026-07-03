// src/lib/logEvent.ts
import { api } from "@/lib/api";

/**
 * 클라이언트 행동 이벤트 로깅 (fire-and-forget).
 *
 * 백엔드 POST /api/log/event 로 전송 (web/backend/routers/log.py).
 * X-Device-Id 는 api interceptor 가 자동 주입하며, opt-out 사용자는
 * 서버가 no-op 처리한다. 로깅 실패가 UX 를 막으면 안 되므로 오류는
 * 조용히 무시한다.
 */
export function logEvent(
  eventType: string,
  payload?: Record<string, unknown>,
): void {
  void api
    .post("/api/log/event", { event_type: eventType, payload: payload ?? null })
    .catch(() => {
      // 로깅 실패는 무시 — 측정은 best-effort, 사용자 경험에 영향 없음
    });
}
