"use client";

import { useEffect, useState } from "react";
import { api, isCancel } from "@/lib/api";
import type { RisingComplexSummary } from "@/types/rising";

const SUMMARY_ERROR_MESSAGE = "가격흐름 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";

interface SummaryResult {
  requestKey: string;
  summary: RisingComplexSummary | null;
  error: string | null;
}

/**
 * 상세 팝업 가격흐름 탭 — 단지의 전 면적대 요약 조회. pnu·면적 필터가 바뀌면 이전 요청을 취소한다.
 * 면적 필터는 지도와 같은 값을 넘겨 첫 면적대가 지도 배지와 같아지게 한다(서버가 선택).
 */
export function useRisingComplex(pnu: string, minArea: number | undefined, maxArea: number | undefined) {
  const [result, setResult] = useState<SummaryResult | null>(null);
  const requestKey = `${pnu}|${minArea ?? ""}|${maxArea ?? ""}`;

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<RisingComplexSummary>(`/api/rising/complex/${encodeURIComponent(pnu)}`, {
        params: { min_area: minArea, max_area: maxArea },
        signal: controller.signal,
      })
      .then((res) => setResult({ requestKey, summary: res.data, error: null }))
      .catch((err: unknown) => {
        if (isCancel(err)) return;
        setResult({ requestKey, summary: null, error: SUMMARY_ERROR_MESSAGE });
      });
    return () => controller.abort();
  }, [pnu, minArea, maxArea, requestKey]);

  const settled = result?.requestKey === requestKey;
  return {
    summary: settled ? result.summary : null,
    loading: !settled,
    error: settled ? result.error : null,
  };
}
