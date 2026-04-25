/**
 * Toss 미니앱 익명 식별자(anon-key) 관리.
 *
 * 정책:
 *  1. 첫 실행 시 Storage 에서 anonKey 조회.
 *  2. 없으면 getAnonymousKey() 로 발급. 발급된 hash 는 미니앱별 고유.
 *  3. 발급된 키를 Storage 에 저장 후 client.setAuthHeader('x-anon-key', hash) 로 주입.
 *  4. SDK 미지원 버전(undefined)/오류(ERROR) 인 경우 헤더 미주입 — 백엔드는 no-op 처리 (services/identity.py).
 *
 * AsyncStorage 는 Apps-in-Toss 환경에서 화면 white-out 을 유발하므로 Storage SDK 만 사용한다.
 */

import { Storage, getAnonymousKey } from '@apps-in-toss/framework';
import { setAuthHeader } from '../api/client';

const STORAGE_KEY = 'jiptori_anon_key';
const HEADER_NAME = 'x-anon-key';

let resolvedKey: string | null = null;
let initPromise: Promise<string | null> | null = null;

export function getAnonKey(): string | null {
  return resolvedKey;
}

/**
 * 1회만 실제 SDK 호출. 동시 호출은 같은 promise 를 공유한다.
 * 호출 종료 시 client 에 헤더가 설정된 상태가 보장된다.
 */
export function initAnonKey(): Promise<string | null> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    try {
      const stored = await Storage.getItem(STORAGE_KEY);
      if (stored) {
        resolvedKey = stored;
        setAuthHeader(HEADER_NAME, stored);
        return stored;
      }
      const result = await getAnonymousKey();
      // SDK 미지원 / 오류 — 헤더 미주입 후 종료. 백엔드 no-op 처리.
      if (!result || result === 'ERROR' || result.type !== 'HASH') {
        return null;
      }
      const hash = result.hash;
      await Storage.setItem(STORAGE_KEY, hash);
      resolvedKey = hash;
      setAuthHeader(HEADER_NAME, hash);
      return hash;
    } catch {
      // Storage / SDK 오류: 익명 키 없이 진행. 백엔드 no-op.
      return null;
    }
  })();
  return initPromise;
}
