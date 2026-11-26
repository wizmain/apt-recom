"use client";

import { useEffect, useMemo, useState } from "react";
import { api, isCancel } from "@/lib/api";
import type { MapTrend, MapTrendResponse } from "@/types/rising";

/**
 * 한 번에 요청하는 PNU 상한 — backend services/rising.py MAP_TREND_MAX_PNUS 와 같은 값.
 * 클러스터러 minLevel(5) 이상 줌은 마커가 묶여 개별 화살표가 보이지 않으므로 요청하지 않는다.
 */
export const MAP_TREND_MAX_PNUS = 2000;
/** 지도 이동·필터 변경 연속 발생 시 요청 묶음 지연(ms). */
const MAP_TREND_DEBOUNCE_MS = 300;

const EMPTY: Record<string, MapTrend> = {};

/**
 * 지도에 보이는 단지들의 오르는 단지 추세 요약.
 * 면적 필터와 겹치는 면적대 중 거래 최다 면적대 기준. 실패하면 빈 객체 — 지도는 그대로 동작한다.
 */
export function useMapTrends(
  pnus: string[],
  minArea: number | undefined,
  maxArea: number | undefined,
): Record<string, MapTrend> {
  const [result, setResult] = useState<{ key: string; items: Record<string, MapTrend> } | null>(
    null,
  );

  // PNU 배열 참조가 매 렌더 바뀌어도 내용이 같으면 재요청하지 않도록 정렬 키를 쓴다.
  const pnuKey = useMemo(() => [...new Set(pnus)].sort().join(","), [pnus]);
  const pnuCount = pnuKey ? pnuKey.split(",").length : 0;
  const enabled = pnuCount > 0 && pnuCount <= MAP_TREND_MAX_PNUS;
  const requestKey = `${pnuKey}|${minArea ?? ""}|${maxArea ?? ""}`;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .post<MapTrendResponse>(
          "/api/rising/map",
          { pnus: pnuKey.split(","), min_area: minArea ?? null, max_area: maxArea ?? null },
          { signal: controller.signal },
        )
        .then((res) => setResult({ key: requestKey, items: res.data.items }))
        .catch((err: unknown) => {
          if (isCancel(err)) return;
          console.warn("[useMapTrends] 추세 요약 조회 실패 — 마커는 기본 핀으로 표시", err);
          setResult({ key: requestKey, items: EMPTY });
        });
    }, MAP_TREND_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, pnuKey, minArea, maxArea, requestKey]);

  if (!enabled) return EMPTY;
  // 요청 진행 중에는 직전 결과를 유지해 배지가 깜빡이지 않게 한다(지도 이동 시 같은 단지 대부분 유지).
  return result?.items ?? EMPTY;
}
