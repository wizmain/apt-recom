// src/app/_home/DetailModalClient.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { ApartmentDetail, TradesResponse } from "@/types/apartment";
import { BasicInfo } from "./detail-sections/BasicInfo";
import { LifeScores } from "./detail-sections/LifeScores";
import { PriceInfo } from "./detail-sections/PriceInfo";
import { School } from "./detail-sections/School";
import { Facilities } from "./detail-sections/Facilities";
import { Safety } from "./detail-sections/Safety";
import { Population } from "./detail-sections/Population";
import { RecentTrades } from "./detail-sections/RecentTrades";

export function DetailModalClient({ pnu }: { pnu: string }) {
  const clearSelection = useAppStore((s) => s.clearSelection);
  const [detail, setDetail] = useState<ApartmentDetail | null>(null);
  const [trades, setTrades] = useState<TradesResponse>({ trades: [], rents: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- pnu 변화 시 로딩 상태 리셋
    setLoading(true);
    setLoadError(false);
    Promise.all([
      api.get<ApartmentDetail>(`/api/apartment/${pnu}`),
      api.get<TradesResponse>(`/api/apartment/${pnu}/trades`),
    ])
      .then(([d, t]) => {
        if (cancelled) return;
        setDetail(d.data);
        setTrades(t.data ?? { trades: [], rents: [] });
        if (d.data?.basic?.bld_nm) {
          document.title = `집토리 - ${d.data.basic.bld_nm}`;
        }
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("DetailModalClient fetch failed", err);
        setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pnu]);

  const close = useCallback(() => {
    clearSelection();
  }, [clearSelection]);

  const handleBackdrop = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) close();
    },
    [close],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in"
      onClick={handleBackdrop}
    >
      <div className="relative w-full max-w-4xl h-[95dvh] sm:h-[85vh] mx-2 sm:mx-4 bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-start justify-between px-4 pt-4 pb-2 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900 truncate">
            {loadError
              ? "아파트 정보 없음"
              : (detail?.basic?.bld_nm ?? "로딩 중...")}
          </h2>
          <button
            onClick={close}
            className="ml-4 p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        {loadError ? (
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="text-4xl">🏚️</div>
              <p className="text-sm text-gray-500">
                요청하신 단지의 상세 정보를 불러오지 못했습니다.
              </p>
              <button
                onClick={close}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
              >
                닫기
              </button>
            </div>
          </div>
        ) : loading || !detail ? (
          <div className="flex-1 flex items-center justify-center h-64 text-gray-500 text-sm">
            데이터를 불러오는 중...
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-6">
            <BasicInfo basic={detail.basic} kapt={detail.kapt_info} />
            <PriceInfo basic={detail.basic} />
            <LifeScores scores={detail.scores} />
            <School school={detail.school} />
            <Facilities summary={detail.facility_summary} />
            <Safety safety={detail.safety} />
            <Population population={detail.population} />
            <RecentTrades trades={trades} />
          </div>
        )}
      </div>
    </div>
  );
}
