"use client";

import { useState } from "react";
import type { RisingRegion, RisingSido } from "@/types/rising";
import { RegionGradeBadge } from "./GradeBadge";

interface RegionPanelProps {
  /** common_code rising_scope_sido (meta.sidos). 탭은 현재 면적대에 지역이 있는 시도만 보여준다. */
  sidos: RisingSido[];
  regions: RisingRegion[];
  regionCounts: Record<string, number>;
  sido: string | null;
  sggCodes: string[];
  onSidoChange: (sido: string | null) => void;
  onSggChange: (codes: string[]) => void;
}

/** 등급순(region_rank 오름차순), 등급 없는 지역은 맨 뒤. */
function sortByRegionRank(regions: RisingRegion[]): RisingRegion[] {
  return [...regions].sort(
    (a, b) =>
      (a.region_rank ?? Number.POSITIVE_INFINITY) -
      (b.region_rank ?? Number.POSITIVE_INFINITY),
  );
}

function tabClass(active: boolean): string {
  return `rounded-full px-3 py-1 text-xs font-medium ${
    active ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
  }`;
}

/** 지역 패널 — 데스크톱은 좌측 고정, 모바일(<768px)은 상단에서 펼치는 시트. */
export default function RegionPanel({
  sidos,
  regions,
  regionCounts,
  sido,
  sggCodes,
  onSidoChange,
  onSggChange,
}: RegionPanelProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const sidoCodesWithRegions = new Set(regions.map((r) => r.sido_code));
  const visibleSidos = sidos.filter((s) => sidoCodesWithRegions.has(s.code));
  const visible = sortByRegionRank(
    sido ? regions.filter((r) => r.sido_code === sido) : regions,
  );

  const toggle = (code: string) =>
    onSggChange(
      sggCodes.includes(code) ? sggCodes.filter((c) => c !== code) : [...sggCodes, code],
    );

  return (
    <aside className="rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        aria-expanded={sheetOpen}
        onClick={() => setSheetOpen((open) => !open)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-800 md:hidden"
      >
        <span>지역{sggCodes.length > 0 ? ` (${sggCodes.length}곳 선택)` : " 전체"}</span>
        <span aria-hidden>{sheetOpen ? "▲" : "▼"}</span>
      </button>
      <div className={`${sheetOpen ? "block" : "hidden"} px-4 pb-4 md:block md:pt-4`}>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="시도">
          <button type="button" onClick={() => onSidoChange(null)} className={tabClass(sido === null)}>
            전체
          </button>
          {visibleSidos.map(({ code, name }) => (
            <button
              key={code}
              type="button"
              onClick={() => onSidoChange(code)}
              className={tabClass(sido === code)}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
          <span>지역 가격 수준 등급순</span>
          <button
            type="button"
            disabled={sggCodes.length === 0}
            onClick={() => onSggChange([])}
            className="text-blue-600 disabled:text-gray-300"
          >
            선택 해제
          </button>
        </div>
        <ul className="mt-1 max-h-96 overflow-y-auto">
          {visible.map((region) => {
            const count = regionCounts[region.sigungu_code] ?? 0;
            const checked = sggCodes.includes(region.sigungu_code);
            return (
              <li key={region.sigungu_code} className={count === 0 ? "opacity-40" : ""}>
                <label className="flex cursor-pointer items-center gap-2 py-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(region.sigungu_code)}
                  />
                  <span className="flex-1 truncate text-gray-800">{region.sigungu_name}</span>
                  <RegionGradeBadge grade={region.region_grade} />
                  <span className="w-12 text-right text-xs tabular-nums text-gray-500">
                    {count.toLocaleString()}곳
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
