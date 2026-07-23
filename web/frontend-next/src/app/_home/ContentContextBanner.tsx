"use client";

import Link from "next/link";
import { useAppStore } from "@/lib/store";

/**
 * 콘텐츠 딥링크 유입 컨텍스트 배너 (B-1) — 지도 상단 1회성.
 *
 * 인스타 카드에서 유입된 사용자가 "링크가 제대로 열렸는지" 즉시 확인할 수
 * 있게 유입 콘텐츠 제목을 보여주고 원문 복귀 경로를 제공한다. 닫으면
 * store 에서 제거 — 쿼리는 이미 소비·제거됐으므로 새로고침에도 재노출 없음.
 */
export function ContentContextBanner() {
  const banner = useAppStore((s) => s.contentBanner);
  const clear = useAppStore((s) => s.clearContentBanner);
  if (!banner) return null;
  return (
    <div
      className="absolute inset-x-2 top-2 z-20 flex items-center gap-2 rounded-xl
                 border border-blue-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur"
      role="status"
    >
      <span aria-hidden>📰</span>
      <p className="min-w-0 flex-1 truncate text-xs sm:text-sm text-gray-700">
        『{banner.title}』 조건으로 보는 중
      </p>
      <Link
        href={`/content/${banner.slug}`}
        className="shrink-0 text-xs sm:text-sm font-medium text-blue-600 hover:underline"
      >
        원문 보기
      </Link>
      <button
        type="button"
        aria-label="컨텍스트 배너 닫기"
        onClick={clear}
        className="shrink-0 px-1 text-gray-400 hover:text-gray-600"
      >
        ✕
      </button>
    </div>
  );
}
