/**
 * 네트워크 상태 모니터링.
 * v1: 마운트 시 한 번 조회.
 *
 * 방어 로직: getNetworkStatus 는 native bridge 기반이라 샌드박스 초기화 시점에
 * undefined 또는 비-Promise 를 반환할 수 있다. Promise 가 아니면 무시.
 */

import { useEffect, useState } from 'react';
import { getNetworkStatus, type NetworkStatus } from '@apps-in-toss/framework';

export function useNetworkStatus(): NetworkStatus | null {
  const [status, setStatus] = useState<NetworkStatus | null>(null);

  useEffect(() => {
    let mounted = true;
    try {
      const result = getNetworkStatus?.();
      if (result && typeof result.then === 'function') {
        result
          .then((s) => {
            if (mounted) setStatus(s);
          })
          .catch(() => {
            // 무시 — 네트워크 상태 조회 실패는 사용자 경험에 영향 없음
          });
      }
    } catch {
      // SDK bridge 미초기화 등 — 무시
    }
    return () => {
      mounted = false;
    };
  }, []);

  return status;
}
