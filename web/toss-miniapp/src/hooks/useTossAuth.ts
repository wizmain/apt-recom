/**
 * 앱 마운트 시 익명 식별자(anon-key) 를 초기화한다.
 * 결과를 기다리지 않으므로 페이지 렌더링은 즉시 시작된다.
 * (백엔드는 헤더 미존재 시 no-op 처리 — services/identity.py)
 */

import { useEffect } from 'react';
import { initAnonKey } from '../lib/anonKey';

export function useTossAuth(): void {
  useEffect(() => {
    initAnonKey();
  }, []);
}
