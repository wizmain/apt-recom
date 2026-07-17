"use client";

import Link from "next/link";
import { logEvent } from "@/lib/logEvent";

type Cta = { id: string; label: string; href: `/?${string}` };

/**
 * 지도 CTA — 본문 inline(전체) + 하단 sticky(첫 번째 1개).
 * 클릭 시 content_map_cta_click 로깅 (fire-and-forget, 네비게이션 비차단).
 */
export function ContentActions({ slug, ctas }: { slug: string; ctas: Cta[] }) {
  if (ctas.length === 0) return null;
  const log = (ctaId: string, placement: "inline" | "sticky") =>
    logEvent("content_map_cta_click", { slug, cta_id: ctaId, placement });
  return (
    <>
      <section className="mt-8 space-y-2">
        {ctas.map((cta) => (
          <Link
            key={cta.id}
            href={cta.href}
            onClick={() => log(cta.id, "inline")}
            className="block rounded-xl bg-blue-600 px-4 py-3 text-center font-semibold text-white hover:bg-blue-700"
          >
            {cta.label}
          </Link>
        ))}
      </section>
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white/95 p-3 backdrop-blur">
        <Link
          href={ctas[0].href}
          onClick={() => log(ctas[0].id, "sticky")}
          className="mx-auto block max-w-xl rounded-xl bg-blue-600 px-4 py-3 text-center font-semibold text-white hover:bg-blue-700"
        >
          {ctas[0].label}
        </Link>
      </div>
    </>
  );
}
