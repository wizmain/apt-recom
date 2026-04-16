/**
 * 익명 device_id 관리 + opt-out.
 *
 * 정책:
 * - 최초 방문 시 UUID 생성 후 localStorage 저장. 재방문 시 동일 ID.
 * - 사용자가 opt-out 선택 시 device_id 반환 중단 → 모든 로깅이 서버에서 no-op.
 * - localStorage 접근 실패(Safari private mode 등)나 crypto.randomUUID 미지원 시 폴백.
 */

const DEVICE_KEY = 'apt_device_id'
const OPT_OUT_KEY = 'apt_device_optout'

function uuidFallback(): string {
  // crypto.randomUUID 미지원 환경 (non-secure context 등) 대비
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`
}

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* no-op */
  }
}

/**
 * 현재 device_id를 반환. opt-out 상태거나 localStorage 접근 불가면 null.
 */
export function getDeviceId(): string | null {
  if (safeGetItem(OPT_OUT_KEY) === '1') return null

  const existing = safeGetItem(DEVICE_KEY)
  if (existing) return existing

  const generated =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : uuidFallback()
  safeSetItem(DEVICE_KEY, generated)
  return generated
}

/**
 * 로그 수집 opt-out 토글. true=수집 허용, false=수집 중단.
 */
export function setTrackingEnabled(enabled: boolean): void {
  safeSetItem(OPT_OUT_KEY, enabled ? '0' : '1')
}

export function isTrackingEnabled(): boolean {
  return safeGetItem(OPT_OUT_KEY) !== '1'
}
