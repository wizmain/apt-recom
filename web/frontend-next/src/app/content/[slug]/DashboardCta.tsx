"use client";

import Link from "next/link";
import { logEvent } from "@/lib/logEvent";

/**
 * trade_top 랜딩 보조 CTA (B-2) — 거래 콘텐츠의 자연스러운 다음 행선지인
 * 실거래 대시보드로 연결한다. map_ctas 계약(trade_top 은 빈 배열 — 가짜
 * 넛지 의도 금지)은 그대로 두고, 시리즈 한정 정적 링크로만 제공.
 */
export function DashboardCta({ slug }: { slug: string }) {
  return (
    <Link
      href="/?view=dashboard&from=content_cta"
      onClick={() => logEvent("content_dashboard_cta_click", { slug })}
      className="mt-8 flex items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50
                 p-4 transition-colors hover:border-blue-400"
    >
      <span className="text-2xl" aria-hidden>
        📊
      </span>
      <span className="min-w-0">
        <span className="block font-semibold text-gray-900">
          이번 주 전체 거래 흐름이 궁금하다면
        </span>
        <span className="block text-sm text-gray-600">
          실거래 대시보드에서 지역별 거래량·중위가 추이 보기 →
        </span>
      </span>
    </Link>
  );
}
