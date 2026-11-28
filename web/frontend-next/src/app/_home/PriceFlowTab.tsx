'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRisingComplex } from '@/hooks/useRisingComplex';
import { useRisingDetail } from '@/hooks/useRisingDetail';
import { useAppStore } from '@/lib/store';
import type { RisingComplexBand, RisingComplexSummary } from '@/types/rising';
import BandPriceChart from '../rising/BandPriceChart';
import DetailMetrics from '../rising/DetailMetrics';
import SignalList from '../rising/SignalList';
import { MonthlyTable, RecentTradesTable } from '../rising/DetailTables';

/**
 * 상세 팝업 "가격흐름" 탭 — 오르는 단지 집계(면적대 중위가격·변화·등급)를 단지 단위로 보여 준다.
 * 지표는 요약 응답으로 바로 그리고, 차트·표만 면적대 상세(`/api/rising/{pnu}`)를 기다린다.
 */
const PRICE_FLOW_PATH = '/rising';
const BASIS_NOTICE = '가격분석 탭은 면적별 평균, 여기는 면적대 중위가격(직거래·이상 거래 제외) 기준입니다.';
const NOT_AGGREGATED_TEXT = '이 단지는 가격흐름 집계 대상이 아닙니다 (수도권 · 최근 실거래 기준).';
const NOT_READY_TEXT = '집계 준비 중입니다.';
const COMPARE_LINK_TEXT = '가격흐름에서 다른 단지와 비교 →';
const BAND_NOT_FOUND_TEXT = '이 면적대 거래 없음';
const LOADING_TEXT = '불러오는 중...';

function chipClass(active: boolean): string {
  return `rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap ${
    active ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
  }`;
}

function CompareLink() {
  return (
    <Link href={PRICE_FLOW_PATH} className="inline-block text-sm font-medium text-blue-600 hover:underline">
      {COMPARE_LINK_TEXT}
    </Link>
  );
}

function BandChips({
  bands,
  activeBand,
  onPick,
}: {
  bands: RisingComplexBand[];
  activeBand: string;
  onPick: (code: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto scrollbar-hide" role="group" aria-label="면적대">
      {bands.map((band) => (
        <button
          key={band.area_band}
          type="button"
          aria-pressed={band.area_band === activeBand}
          onClick={() => onPick(band.area_band)}
          className={chipClass(band.area_band === activeBand)}
        >
          {band.area_band_name}
        </button>
      ))}
    </div>
  );
}

/**
 * 고른 면적대가 이 단지에 없으면(다른 단지로 바뀐 직후 등) 첫 면적대로 돌아간다 —
 * 이전 단지의 선택이 남아 404 문구가 보이지 않게 하기 위함.
 */
function resolveActiveBand(summary: RisingComplexSummary, picked: string | null): RisingComplexBand | null {
  const { bands } = summary;
  return (
    bands.find((band) => band.area_band === picked) ??
    bands.find((band) => band.area_band === summary.default_band) ??
    bands[0] ??
    null
  );
}

function BandDetail({ pnu, band }: { pnu: string; band: RisingComplexBand }) {
  const { detail, loading, notFound, error } = useRisingDetail(pnu, band.area_band);
  return (
    <>
      <DetailMetrics item={band.item} region={band.region} />
      {loading && <p className="text-sm text-gray-400">{LOADING_TEXT}</p>}
      {notFound && <p className="text-sm text-gray-500">{BAND_NOT_FOUND_TEXT}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {detail && (
        <>
          <SignalList signals={detail.signals} />
          <BandPriceChart monthly={detail.monthly} />
          <MonthlyTable monthly={detail.monthly} />
          <RecentTradesTable trades={detail.recent_trades} />
        </>
      )}
    </>
  );
}

export default function PriceFlowTab({ pnu }: { pnu: string }) {
  const filters = useAppStore((s) => s.filters);
  const { summary, loading, error } = useRisingComplex(pnu, filters.min_area, filters.max_area);
  const [picked, setPicked] = useState<string | null>(null);

  if (loading) return <p className="py-12 text-center text-sm text-gray-400">{LOADING_TEXT}</p>;
  if (error || !summary) return <p className="py-12 text-center text-sm text-red-600">{error}</p>;
  if (summary.base_ym === null) {
    return <p className="py-12 text-center text-sm text-gray-500">{NOT_READY_TEXT}</p>;
  }
  const activeBand = resolveActiveBand(summary, picked);
  if (activeBand === null) {
    return (
      <div className="space-y-3 py-10 text-center">
        <p className="text-sm text-gray-500">{NOT_AGGREGATED_TEXT}</p>
        <CompareLink />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs leading-relaxed text-blue-800">
        {BASIS_NOTICE}
      </div>
      <BandChips bands={summary.bands} activeBand={activeBand.area_band} onPick={setPicked} />
      {/* key: 면적대가 바뀌면 상세 영역을 새로 그려 이전 면적대 차트가 남지 않게 한다 */}
      <BandDetail key={activeBand.area_band} pnu={summary.pnu} band={activeBand} />
      <CompareLink />
    </div>
  );
}
