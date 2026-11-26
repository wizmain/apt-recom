// src/app/_home/Map/InfoWindowTrend.tsx
"use client";

import Link from "next/link";
import type { MapTrend } from "@/types/rising";
import ChangeCell from "@/app/rising/ChangeCell";
import { ComplexGradeCell, RegionGradeBadge } from "@/app/rising/GradeBadge";
import { THIN_SAMPLE_TEXT, formatEok, isThinSample } from "@/app/rising/format";

/** 지도 팝업의 오르는 단지 추세 요약 (면적 필터와 겹치는 면적대 중 거래 최다 면적대 기준). */
export function InfoWindowTrend({ trend }: { trend: MapTrend }) {
  return (
    <div className="mt-2 rounded-md border border-gray-100 bg-gray-50 p-2 text-xs text-gray-700">
      <div className="mb-1 font-medium text-gray-500">{trend.area_band_name} 실거래 추세</div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-gray-500">3개월 중위</span>
        <span className="text-right">
          <span className="font-semibold tabular-nums text-gray-900">
            {trend.median_price_3m === null ? "—" : formatEok(trend.median_price_3m)}
          </span>
          <span className="ml-1 text-[11px] text-gray-400">
            {isThinSample(trend.trade_count_3m)
              ? THIN_SAMPLE_TEXT
              : `${trend.trade_count_3m ?? 0}건`}
          </span>
        </span>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-2">
        <div>
          <div className="text-gray-500">6개월</div>
          <ChangeCell pct={trend.change_6m_pct} matchedTypeCount={trend.matched_type_count_6m} />
        </div>
        <div>
          <div className="text-gray-500">12개월</div>
          <ChangeCell pct={trend.change_12m_pct} matchedTypeCount={trend.matched_type_count_12m} />
        </div>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-gray-500">지역 가격 등급</span>
        <RegionGradeBadge grade={trend.region_grade} />
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-gray-500">지역 내 단지 등급</span>
        <ComplexGradeCell item={trend} />
      </div>
      <Link href="/rising" className="mt-2 block text-right font-medium text-blue-600 hover:underline">
        오르는 단지에서 보기 →
      </Link>
    </div>
  );
}
