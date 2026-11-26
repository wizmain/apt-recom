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

/** 상세 팝업 가격흐름 탭 — 단지의 전 면적대 요약 조회. pnu 가 바뀌면 이전 요청을 취소한다. */
export function useRisingComplex(pnu: string) {
  const [result, setResult] = useState<SummaryResult | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<RisingComplexSummary>(`/api/rising/complex/${encodeURIComponent(pnu)}`, {
        signal: controller.signal,
      })
      .then((res) => setResult({ requestKey: pnu, summary: res.data, error: null }))
      .catch((err: unknown) => {
        if (isCancel(err)) return;
        setResult({ requestKey: pnu, summary: null, error: SUMMARY_ERROR_MESSAGE });
      });
    return () => controller.abort();
  }, [pnu]);

  const settled = result?.requestKey === pnu;
  return {
    summary: settled ? result.summary : null,
    loading: !settled,
    error: settled ? result.error : null,
  };
}
