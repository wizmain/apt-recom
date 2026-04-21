/**
 * URL ↔ 상태 동기화 헬퍼.
 *
 * 아파트 상세 모달을 라우트처럼 다루기 위해, 브라우저 주소창을 다음 두 상태 중 하나로 유지한다:
 *   - `/` (홈)
 *   - `/apartment/{pnu}` (특정 아파트 상세가 열려 있음)
 *
 * react-router 없이 `window.history` + `popstate` 만으로 구현하며, App.tsx 의
 * `selectedPnu` state 가 단일 진실 공급원이다.
 */

export const DEFAULT_DOCUMENT_TITLE = '집토리 - 라이프스타일 아파트 찾기';

/** PNU 스펙: 19자리 숫자 문자열. */
const PNU_PATTERN = /^[0-9]{19}$/;

/** `/apartment/{pnu}` 경로를 식별하는 패턴. */
const APT_PATH_PATTERN = /^\/apartment\/([0-9]{19})\/?$/;

/**
 * 현재 pathname 에서 아파트 PNU 를 추출한다. 경로가 `/apartment/:pnu` 가 아니거나
 * PNU 형식이 맞지 않으면 null.
 */
export function parseAptPnuFromPath(pathname: string): string | null {
  const match = APT_PATH_PATTERN.exec(pathname);
  return match ? match[1] : null;
}

/** PNU 문자열을 클라이언트 라우트로 변환. */
export function buildAptPath(pnu: string): string {
  return `/apartment/${pnu}`;
}

/** PNU 유효성 검사 (19자리 숫자). 외부 입력 방어용. */
export function isValidPnu(pnu: string): boolean {
  return PNU_PATTERN.test(pnu);
}
