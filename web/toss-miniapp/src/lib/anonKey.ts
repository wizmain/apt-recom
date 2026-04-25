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
 *
 * 방어 로직: Storage / getAnonymousKey 는 native bridge 기반.
 * 샌드박스 초기화 미완료 시점에 함수 자체가 undefined 이거나 비-Promise 반환 가능.
 */
export function initAnonKey(): Promise<string | null> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    try {
      const stored = await safeAwait(Storage?.getItem?.(STORAGE_KEY));
      if (stored && typeof stored === 'string') {
        resolvedKey = stored;
        setAuthHeader(HEADER_NAME, stored);
        return stored;
      }
      const result = await safeAwait(getAnonymousKey?.());
      if (!result || result === 'ERROR' || result.type !== 'HASH') {
        return null;
      }
      const hash = result.hash;
      await safeAwait(Storage?.setItem?.(STORAGE_KEY, hash));
      resolvedKey = hash;
      setAuthHeader(HEADER_NAME, hash);
      return hash;
    } catch {
      return null;
    }
  })();
  return initPromise;
}

// SDK 함수가 undefined 또는 비-Promise 를 반환해도 안전하게 풀어 주는 헬퍼.
async function safeAwait<T>(maybe: T | Promise<T> | undefined): Promise<T | null> {
  if (maybe == null) return null;
  if (typeof (maybe as { then?: unknown }).then === 'function') {
    try {
      return await (maybe as Promise<T>);
    } catch {
      return null;
    }
  }
  return maybe as T;
}
