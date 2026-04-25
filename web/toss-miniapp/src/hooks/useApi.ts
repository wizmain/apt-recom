/**
 * 단순 GET 요청을 위한 훅.
 * - path 가 변경되면 재요청 (의존성 배열로 enabled/key 제어)
 * - AbortController 로 unmount 또는 path 변경 시 이전 요청 취소
 *
 * 사용:
 *   const { data, loading, error, reload } = useApi<DashboardSummary>(
 *     apiPaths.dashboardSummary(),
 *     { sigungu: regionCode }
 *   );
 */

import { useCallback, useEffect, useState } from 'react';
import { ApiError, request } from '../api/client';

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
}

export function useApi<T>(
  path: string | null,
  query?: Record<string, string | number | boolean | undefined | null>
): UseApiState<T> & { reload: () => void } {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: path !== null,
    error: null,
  });
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    setTick((v) => v + 1);
  }, []);

  // useApi 호출자는 query 객체를 매 렌더 새로 만드므로 stringify 로 안정화.
  const queryKey = query ? JSON.stringify(query) : '';

  useEffect(() => {
    if (path === null) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true, error: null }));
    request<T>(path, { query, signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ data, loading: false, error: null });
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const error =
          err instanceof Error ? err : new Error(String(err));
        setState({ data: null, loading: false, error });
      });
    return () => controller.abort();
    // queryKey 는 query 의 안정 직렬화 키. query 자체를 의존성에 두면 매 렌더 재요청.
  }, [path, queryKey, tick]);

  return { ...state, reload };
}
