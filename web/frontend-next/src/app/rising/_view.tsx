"use client";

import { useCallback, useRef, useState } from "react";
import { useRising } from "@/hooks/useRising";
import type { RisingFilters } from "@/types/rising";
import ComplexDetailPanel from "./ComplexDetailPanel";
import ComplexListControls from "./ComplexListControls";
import ComplexTable from "./ComplexTable";
import { formatBaseMonth } from "./format";
import RegionPanel from "./RegionPanel";
import RisingFilterBar from "./RisingFilterBar";

/** 첫 응답 전 페이지네이션 계산용(서버 page_size 와 동일). */
const DEFAULT_PAGE_SIZE = 20;

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

/** 필터 상태 보유 + 데이터 조회. 하위 컴포넌트는 props 로만 데이터를 받는다. */
export default function RisingView() {
  const [filters, setFilters] = useState<RisingFilters>(INITIAL_FILTERS);
  const { meta, list, loading, error } = useRising(filters);
  const [selected, setSelected] = useState<{ pnu: string; sigunguCode: string } | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  const openDetail = (pnu: string, trigger: HTMLElement) => {
    const item = list?.items.find((candidate) => candidate.pnu === pnu);
    triggerRef.current = trigger;
    setSelected({ pnu, sigunguCode: item?.sigungu_code ?? "" });
  };

  /** 닫으면 열었던 행/카드로 포커스를 돌려준다. */
  const closeDetail = useCallback(() => {
    setSelected(null);
    triggerRef.current?.focus();
  }, []);

  /** page 이외의 필터가 바뀌면 1페이지로 되돌린다. */
  const updateFilters = (patch: Partial<RisingFilters>) =>
    setFilters((prev) => ({ ...prev, page: 1, ...patch }));

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
  if (!meta) {
    return <p className="mt-6 text-sm text-gray-400">불러오는 중...</p>;
  }

  return (
    <section className="mt-6 space-y-4">
      <RisingFilterBar
        bands={meta.bands}
        areaBand={filters.areaBand}
        budgetMin={filters.budgetMin}
        budgetMax={filters.budgetMax}
        onAreaBandChange={(code) => updateFilters({ areaBand: code })}
        onBudgetChange={({ min, max }) => updateFilters({ budgetMin: min, budgetMax: max })}
      />
      {meta.base_ym != null && (
        <p className="text-xs text-gray-500">{formatBaseMonth(meta.base_ym)} 계약까지</p>
      )}
      <div className="grid gap-4 md:grid-cols-[280px_1fr] md:items-start">
        <RegionPanel
          regions={meta.regions[filters.areaBand] ?? []}
          regionCounts={list?.region_counts ?? {}}
          sido={filters.sido}
          sggCodes={filters.sggCodes}
          onSidoChange={(sido) => updateFilters({ sido, sggCodes: [] })}
          onSggChange={(sggCodes) => updateFilters({ sggCodes })}
        />
        <div className="min-w-0 space-y-3">
          <ComplexListControls
            sort={filters.sort}
            query={filters.query}
            onSortChange={(sort) => updateFilters({ sort })}
            onQueryChange={(query) => updateFilters({ query })}
          />
          {list && (
            <p className="text-sm text-gray-700">
              {list.total_count.toLocaleString()}개 단지 · {list.region_count}개 지역
            </p>
          )}
          <ComplexTable
            items={list?.items ?? []}
            page={filters.page}
            pageSize={list?.page_size ?? DEFAULT_PAGE_SIZE}
            totalCount={list?.total_count ?? 0}
            loading={loading}
            onPageChange={(page) => updateFilters({ page })}
            onSelect={openDetail}
          />
        </div>
      </div>
      {selected && (
        <ComplexDetailPanel
          pnu={selected.pnu}
          areaBand={filters.areaBand}
          areaBandName={meta.bands.find((band) => band.code === filters.areaBand)?.name ?? ""}
          region={
            (meta.regions[filters.areaBand] ?? []).find(
              (region) => region.sigungu_code === selected.sigunguCode,
            ) ?? null
          }
          onClose={closeDetail}
        />
      )}
    </section>
  );
}
