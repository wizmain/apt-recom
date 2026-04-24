"use client";

import { useState, useEffect } from 'react';
import { countActiveFilters } from '@/hooks/useApartments';
import { useAppStore } from '@/lib/store';
import type { FilterState } from '@/lib/store/searchSlice';

interface FilterPanelProps {
  isOpen: boolean;
  onClose: () => void;
  resultCount: number;
}

const AREA_OPTIONS = [
  { label: '전체', min: undefined, max: undefined },
  { label: '~40㎡ (소형)', min: undefined, max: 40 },
  { label: '40~60㎡ (중소형)', min: 40, max: 60 },
  { label: '60~85㎡ (중형)', min: 60, max: 85 },
  { label: '85~115㎡ (중대형)', min: 85, max: 115 },
  { label: '115㎡~ (대형)', min: 115, max: undefined },
];

const PRICE_OPTIONS = [
  { label: '전체', min: undefined, max: undefined },
  { label: '~3억', min: undefined, max: 30000 },
  { label: '3~5억', min: 30000, max: 50000 },
  { label: '5~7억', min: 50000, max: 70000 },
  { label: '7~10억', min: 70000, max: 100000 },
  { label: '10~15억', min: 100000, max: 150000 },
  { label: '15억~', min: 150000, max: undefined },
];

const FLOOR_OPTIONS = [
  { label: '전체', value: undefined },
  { label: '5층 이상', value: 5 },
  { label: '10층 이상', value: 10 },
  { label: '15층 이상', value: 15 },
  { label: '20층 이상', value: 20 },
  { label: '30층 이상', value: 30 },
];

const HHLD_OPTIONS = [
  { label: '전체', min: undefined, max: undefined },
  { label: '~100세대', min: undefined, max: 100 },
  { label: '100~300', min: 100, max: 300 },
  { label: '300~500', min: 300, max: 500 },
  { label: '500~1000', min: 500, max: 1000 },
  { label: '1000~', min: 1000, max: undefined },
];

const YEAR_OPTIONS = [
  { label: '전체', after: undefined, before: undefined },
  { label: '5년 이내', after: 2021, before: undefined },
  { label: '10년 이내', after: 2016, before: undefined },
  { label: '15년 이내', after: 2011, before: undefined },
  { label: '20년 이상', after: undefined, before: 2006 },
];

export default function FilterPanel({ isOpen, onClose, resultCount }: FilterPanelProps) {
  const filters = useAppStore((s) => s.filters);
  const applyFilters = useAppStore((s) => s.applyFilters);
  const clearFilters = useAppStore((s) => s.clearFilters);

  const [local, setLocal] = useState<FilterState>({});

  useEffect(() => {
    setLocal(filters);
  }, [filters]);

  const handleApply = () => {
    applyFilters(local);
    onClose();
  };

  const activeCount = countActiveFilters(local);

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/20 z-20" onClick={onClose} />}

      <div
        className="fixed left-0 right-0 z-30 transition-all duration-300 ease-in-out overflow-hidden top-24 sm:top-14"
        style={{ maxHeight: isOpen ? '80dvh' : 0, opacity: isOpen ? 1 : 0 }}
      >
        <div className="bg-white border-b border-gray-200 shadow-lg">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-gray-800">필터</span>
              {activeCount > 0 && (
                <span className="text-[10px] bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded-full font-bold">
                  {activeCount}개 적용
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">{resultCount.toLocaleString()}개 아파트</span>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
            </div>
          </div>

          {/* Filters */}
          <div className="px-4 py-3 max-h-[60dvh] sm:max-h-[380px] overflow-y-auto space-y-4">
            {/* 면적 */}
            <FilterSection title="면적">
              <ChipGroup
                options={AREA_OPTIONS.map(o => o.label)}
                selected={AREA_OPTIONS.findIndex(o => o.min === local.min_area && o.max === local.max_area)}
                onChange={(idx) => {
                  const o = AREA_OPTIONS[idx];
                  setLocal(p => ({ ...p, min_area: o.min, max_area: o.max }));
                }}
              />
            </FilterSection>

            {/* 가격 */}
            <FilterSection title="매매가">
              <ChipGroup
                options={PRICE_OPTIONS.map(o => o.label)}
                selected={PRICE_OPTIONS.findIndex(o => o.min === local.min_price && o.max === local.max_price)}
                onChange={(idx) => {
                  const o = PRICE_OPTIONS[idx];
                  setLocal(p => ({ ...p, min_price: o.min, max_price: o.max }));
                }}
              />
            </FilterSection>

            {/* 최고층 */}
            <FilterSection title="최고층">
              <ChipGroup
                options={FLOOR_OPTIONS.map(o => o.label)}
                selected={FLOOR_OPTIONS.findIndex(o => o.value === local.min_floor)}
                onChange={(idx) => {
                  setLocal(p => ({ ...p, min_floor: FLOOR_OPTIONS[idx].value }));
                }}
              />
            </FilterSection>

            {/* 세대수 */}
            <FilterSection title="세대수">
              <ChipGroup
                options={HHLD_OPTIONS.map(o => o.label)}
                selected={HHLD_OPTIONS.findIndex(o => o.min === local.min_hhld && o.max === local.max_hhld)}
                onChange={(idx) => {
                  const o = HHLD_OPTIONS[idx];
                  setLocal(p => ({ ...p, min_hhld: o.min, max_hhld: o.max }));
                }}
              />
            </FilterSection>

            {/* 준공연도 */}
            <FilterSection title="준공연도">
              <ChipGroup
                options={YEAR_OPTIONS.map(o => o.label)}
                selected={YEAR_OPTIONS.findIndex(o => o.after === local.built_after && o.before === local.built_before)}
                onChange={(idx) => {
                  const o = YEAR_OPTIONS[idx];
                  setLocal(p => ({ ...p, built_after: o.after, built_before: o.before }));
                }}
              />
            </FilterSection>
          </div>

          {/* Footer */}
          <div className="flex gap-2 px-4 py-2.5 border-t border-gray-100">
            <button onClick={() => { clearFilters(); setLocal({}); }}
              className="flex-1 py-1.5 px-3 rounded-lg border border-gray-300 text-gray-600 text-xs font-medium hover:bg-gray-50 cursor-pointer">
              초기화
            </button>
            <button onClick={handleApply}
              className="flex-1 py-1.5 px-3 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 cursor-pointer">
              적용 ({resultCount.toLocaleString()}개)
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="text-xs font-bold text-gray-700 mb-1.5 block">{title}</span>
      {children}
    </div>
  );
}

function ChipGroup({ options, selected, onChange }: { options: string[]; selected: number; onChange: (idx: number) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((label, idx) => (
        <button
          key={label}
          onClick={() => onChange(idx)}
          className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer
            ${idx === selected
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300'
            }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
