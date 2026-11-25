"use client";

import { useEffect, useState } from "react";
import { api, isCancel } from "@/lib/api";
import type { RisingDetail } from "@/types/rising";

const HTTP_NOT_FOUND = 404;

interface DetailResult {
  requestKey: string;
  detail: RisingDetail | null;
  notFound: boolean;
  error: string | null;
}

const DETAIL_ERROR_MESSAGE = "상세 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";

/** 단지×면적대 상세 조회. pnu 가 null 이면 요청하지 않는다. 404 는 notFound 로 구분. */
export function useRisingDetail(pnu: string | null, areaBand: string) {
  const [result, setResult] = useState<DetailResult | null>(null);
  const requestKey = pnu ? `${pnu}|${areaBand}` : null;

  useEffect(() => {
    if (!pnu || !requestKey) return;
    const controller = new AbortController();
    api
      .get<RisingDetail>(`/api/rising/${encodeURIComponent(pnu)}`, {
        params: { area_band: areaBand },
        signal: controller.signal,
      })
      .then((res) =>
        setResult({ requestKey, detail: res.data, notFound: false, error: null }),
      )
      .catch((err: unknown) => {
        if (isCancel(err)) return;
        const status =
          typeof err === "object" && err !== null && "response" in err
            ? (err as { response?: { status?: number } }).response?.status
            : undefined;
        const isNotFound = status === HTTP_NOT_FOUND;
        setResult({
          requestKey,
          detail: null,
          notFound: isNotFound,
          error: isNotFound ? null : DETAIL_ERROR_MESSAGE,
        });
      });
    return () => controller.abort();
  }, [pnu, areaBand, requestKey]);

  const settled = requestKey !== null && result?.requestKey === requestKey;
  return {
    detail: settled ? result.detail : null,
    loading: requestKey !== null && !settled,
    notFound: settled ? result.notFound : false,
    error: settled ? result.error : null,
  };
}
