/**
 * 익명 device_id 관리 + opt-out.
 *
 * 정책:
 * - 최초 방문 시 UUID 생성 후 localStorage 저장. 재방문 시 동일 ID.
 * - opt-out 시 device_id 반환 중단 → 서버 이벤트 로깅 no-op.
 * - localStorage 접근 실패(Safari private mode, SSR 등)나 crypto.randomUUID
 *   미지원 시 폴백. 함수 전체가 try/catch 로 감싸져 SSR 호출 시에도 예외 없이 null 반환.
 *
 * 사용 범위: 클라이언트 컴포넌트 전용. 서버 컴포넌트에서 호출하면 의미 없이 null.
 */

const DEVICE_KEY = "apt_device_id";
const OPT_OUT_KEY = "apt_device_optout";

function uuidFallback(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

function safeGetItem(key: string): string | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

export function getDeviceId(): string | null {
  if (safeGetItem(OPT_OUT_KEY) === "1") return null;

  const existing = safeGetItem(DEVICE_KEY);
  if (existing) return existing;

  const generated =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : uuidFallback();
  safeSetItem(DEVICE_KEY, generated);
  return generated;
}

export function setTrackingEnabled(enabled: boolean): void {
  safeSetItem(OPT_OUT_KEY, enabled ? "0" : "1");
}

export function isTrackingEnabled(): boolean {
  return safeGetItem(OPT_OUT_KEY) !== "1";
}
