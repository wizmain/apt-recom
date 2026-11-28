"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useRisingDetail } from "@/hooks/useRisingDetail";
import type { RisingRegion } from "@/types/rising";
import BandPriceChart from "./BandPriceChart";
import DetailMetrics from "./DetailMetrics";
import SignalList from "./SignalList";
import { MonthlyTable, RecentTradesTable } from "./DetailTables";

const NOT_FOUND_TEXT = "이 면적대 거래 없음";
const DETAIL_LINK_TEXT = "이 단지 자세히 보기";
const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

interface ComplexDetailPanelProps {
  pnu: string;
  areaBand: string;
  /** 면적대 표시명(예: "84㎡급"). */
  areaBandName: string;
  /** 단지가 속한 시군구×면적대 집계(지역 순위 표시용). */
  region: RisingRegion | null;
  onClose: () => void;
}

/** ESC 닫기 + 배경 스크롤 잠금 + Tab 포커스 가둠. 열릴 때 닫기 버튼으로 포커스 이동. */
function useModalBehavior(
  dialogRef: React.RefObject<HTMLDivElement | null>,
  onClose: () => void,
) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [dialogRef, onClose]);
}

/** 단지×면적대 상세 — 데스크톱 우측 드로어 / 모바일 전체 화면. */
export default function ComplexDetailPanel({
  pnu,
  areaBand,
  areaBandName,
  region,
  onClose,
}: ComplexDetailPanelProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const { detail, loading, notFound, error } = useRisingDetail(pnu, areaBand);
  useModalBehavior(dialogRef, onClose);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="단지 상세"
        className="relative flex h-full w-full flex-col bg-white shadow-xl md:max-w-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-gray-200 px-4 py-3">
          <div className="min-w-0">
            <p className="text-xs text-gray-500">
              {detail?.address ?? ""} · {areaBandName}
            </p>
            <h2 className="truncate text-lg font-bold text-gray-900">{detail?.name ?? ""}</h2>
          </div>
          <button
            type="button"
            data-autofocus
            onClick={onClose}
            aria-label="닫기"
            className="rounded-md px-2 py-1 text-xl leading-none text-gray-500 hover:bg-gray-100"
          >
            ×
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
          {loading && <p className="text-sm text-gray-400">불러오는 중...</p>}
          {notFound && <p className="text-sm text-gray-500">{NOT_FOUND_TEXT}</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {detail && (
            <>
              <DetailMetrics item={detail.item} region={region} />
              <SignalList signals={detail.signals} />
              <BandPriceChart monthly={detail.monthly} />
              <MonthlyTable monthly={detail.monthly} />
              <RecentTradesTable trades={detail.recent_trades} />
            </>
          )}
        </div>
        {detail && (
          <footer className="border-t border-gray-200 px-4 py-3">
            <Link
              href={`/apartment/${encodeURIComponent(pnu)}`}
              className="block rounded-lg bg-blue-600 py-2.5 text-center text-sm font-semibold text-white hover:bg-blue-700"
            >
              {DETAIL_LINK_TEXT}
            </Link>
          </footer>
        )}
      </div>
    </div>
  );
}
