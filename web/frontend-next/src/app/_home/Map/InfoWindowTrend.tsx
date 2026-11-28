// src/app/_home/Map/InfoWindowTrend.tsx
"use client";

import Link from "next/link";
import type { MapTrend } from "@/types/rising";
import ChangeCell from "@/app/rising/ChangeCell";
import { ComplexGradeCell, RegionGradeBadge } from "@/app/rising/GradeBadge";
import { formatEok } from "@/app/rising/format";

// 지도 전용 표본 규칙 — backend services/rising.py THIN_SAMPLE_MAX_TRADES(지도 화살표 숨김)와 같은 값.
// 가격흐름 목록·상세의 "표본 적음" 배지는 배치 주의 코드(3건 이하)로 따로 판정한다.
const MAP_THIN_SAMPLE_MAX_TRADES = 2;
const MAP_THIN_SAMPLE_TEXT = "표본 적음";

function isMapThinSample(tradeCount: number | null): boolean {
  return tradeCount !== null && tradeCount <= MAP_THIN_SAMPLE_MAX_TRADES;
}

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
            {isMapThinSample(trend.trade_count_3m)
              ? MAP_THIN_SAMPLE_TEXT
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
        가격흐름에서 보기 →
      </Link>
    </div>
  );
}
