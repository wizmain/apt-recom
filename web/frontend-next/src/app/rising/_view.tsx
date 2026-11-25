"use client";

import { useState } from "react";
import { useRising } from "@/hooks/useRising";
import type { RisingFilters } from "@/types/rising";

const INITIAL_FILTERS: RisingFilters = {
  areaBand: "84",
  budgetMin: 3,
  budgetMax: 10,
  sido: null,
  sggCodes: [],
  query: "",
  sort: "change_6m",
  page: 1,
};

/** 202609 → "2026.09" */
function formatBaseYm(baseYm: number): string {
  const text = String(baseYm);
  return `${text.slice(0, 4)}.${text.slice(4)}`;
}

/** 필터 상태 보유 + 데이터 조회. 목록 영역은 Task 6 에서 필터·표 컴포넌트로 교체된다. */
export default function RisingView() {
  const [filters] = useState<RisingFilters>(INITIAL_FILTERS);
  const { meta, list, loading, error } = useRising(filters);

  if (error) {
    return <p className="mt-6 text-sm text-red-600">{error}</p>;
  }
  if (meta && meta.base_ym === null) {
    return (
      <p className="mt-6 rounded-lg bg-white p-6 text-center text-sm text-gray-500">
        집계 준비 중입니다.
      </p>
    );
  }

  return (
    <section className="mt-6">
      {meta?.base_ym != null && (
        <p className="text-xs text-gray-500">
          {formatBaseYm(meta.base_ym)} 계약까지
        </p>
      )}
      {loading && !list && (
        <p className="mt-4 text-sm text-gray-400">불러오는 중...</p>
      )}
      {list && (
        <div className="mt-2">
          <p className="text-sm text-gray-700">
            {list.total_count.toLocaleString()}개 단지 · {list.region_count}개 지역
          </p>
          <ul className="mt-2 text-sm text-gray-600">
            {list.items.map((item) => (
              <li key={item.pnu}>{item.name}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
