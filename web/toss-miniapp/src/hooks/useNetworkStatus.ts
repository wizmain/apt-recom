/**
 * 네트워크 상태 모니터링.
 * v1: 마운트 시 한 번 조회 후 OFFLINE 이면 콜백 실행 (Toast 등).
 * 지속 모니터링이 필요하면 SDK 의 이벤트 구독 API 추가 검토 (Phase 6+).
 */

import { useEffect, useState } from 'react';
import { getNetworkStatus, type NetworkStatus } from '@apps-in-toss/framework';

export function useNetworkStatus(): NetworkStatus | null {
  const [status, setStatus] = useState<NetworkStatus | null>(null);

  useEffect(() => {
    let mounted = true;
    getNetworkStatus()
      .then((s) => {
        if (mounted) setStatus(s);
      })
      .catch(() => {
        // 무시 — 네트워크 상태 조회 실패는 사용자 경험에 영향 없음
      });
    return () => {
      mounted = false;
    };
  }, []);

  return status;
}
