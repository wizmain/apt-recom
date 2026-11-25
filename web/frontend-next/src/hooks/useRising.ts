"use client";

import { useEffect, useState } from "react";
import { api, isCancel } from "@/lib/api";
import type {
  RisingFilters,
  RisingListResponse,
  RisingMeta,
} from "@/types/rising";

/** 검색어 입력 중 요청 스팸 방지 지연(ms). */
const QUERY_DEBOUNCE_MS = 250;
const LOAD_ERROR_MESSAGE = "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";

interface ListResult {
  requestKey: string;
  list: RisingListResponse | null;
  error: string | null;
}

/** 디바운스된 값 — 지연 시간 동안 값이 안 바뀌면 반영. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/** 필터 → 쿼리스트링. sgg 는 반복 키(sgg=a&sgg=b)로 직렬화한다. */
function buildListParams(filters: RisingFilters, query: string): URLSearchParams {
  const params = new URLSearchParams({
    area_band: filters.areaBand,
    budget_min: String(filters.budgetMin),
    budget_max: String(filters.budgetMax),
    sort: filters.sort,
    page: String(filters.page),
  });
  if (filters.sido) params.set("sido", filters.sido);
  for (const code of filters.sggCodes) params.append("sgg", code);
  const trimmed = query.trim();
  if (trimmed) params.set("q", trimmed);
  return params;
}

/**
 * 오르는 단지 메타(1회) + 필터에 맞는 목록 조회.
 * 필터가 바뀌면 이전 요청을 취소하고, 검색어만 250ms 디바운스한다.
 */
export function useRising(filters: RisingFilters) {
  const [meta, setMeta] = useState<RisingMeta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [result, setResult] = useState<ListResult | null>(null);

  const debouncedQuery = useDebouncedValue(filters.query, QUERY_DEBOUNCE_MS);
  const { areaBand, budgetMin, budgetMax, sido, sggCodes, sort, page } = filters;
  const sggKey = sggCodes.join(",");

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<RisingMeta>("/api/rising/meta", { signal: controller.signal })
      .then((res) => setMeta(res.data))
      .catch((err: unknown) => {
        if (!isCancel(err)) setMetaError(LOAD_ERROR_MESSAGE);
      });
    return () => controller.abort();
  }, []);

  const params = buildListParams(
    { areaBand, budgetMin, budgetMax, sido, sggCodes, query: "", sort, page },
    debouncedQuery,
  ).toString();
  // sggKey 는 sggCodes 배열 참조가 매 렌더 바뀌어도 effect 가 재실행되지 않게 하는 안정 키.
  const requestKey = `${params}|${sggKey}`;

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<RisingListResponse>("/api/rising", {
        params: new URLSearchParams(params),
        signal: controller.signal,
      })
      .then((res) => setResult({ requestKey, list: res.data, error: null }))
      .catch((err: unknown) => {
        if (isCancel(err)) return;
        setResult({ requestKey, list: null, error: LOAD_ERROR_MESSAGE });
      });
    return () => controller.abort();
  }, [params, requestKey]);

  const settled = result?.requestKey === requestKey;
  return {
    meta,
    // 필터 전환 중에는 직전 목록을 유지해 화면이 깜빡이지 않게 한다.
    list: result?.list ?? null,
    loading: !settled,
    error: (settled ? result.error : null) ?? metaError,
  };
}
