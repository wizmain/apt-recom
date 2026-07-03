// src/app/explore/PresetTiles.tsx
"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import type { ExplorePreset } from "@/lib/explorePreset";
import { logEvent } from "@/lib/logEvent";

interface PresetTilesProps {
  presets: ExplorePreset[];
}

/**
 * 프리셋 → 홈 딥링크 (useBridgeParams 가 1회 소비해 추천 자동 실행).
 *
 * 반환 타입을 템플릿 리터럴(`/?${string}`)로 명시하는 이유: Next.js 16
 * typedRoutes 는 `Link href` 값의 리터럴 패턴으로 라우트 유효성을 검사한다.
 * 단순 `string` 반환이면 그 정보가 지워져 빌드 타입체크가 실패한다
 * (참고: RecommendCta.tsx 는 같은 이유로 router.push 호출부에 템플릿
 * 리터럴을 인라인한다).
 */
function presetHref(p: ExplorePreset): `/?${string}` {
  const params = new URLSearchParams({
    nudges: p.nudges.join(","),
    sigungu_code: p.sigunguCode,
    region_label: p.regionLabel,
  });
  return `/?${params.toString()}`;
}

export default function PresetTiles({ presets }: PresetTilesProps) {
  const viewLoggedRef = useRef(false);

  useEffect(() => {
    if (viewLoggedRef.current) return;
    viewLoggedRef.current = true;
    logEvent("explore_view", { preset_count: presets.length });
  }, [presets.length]);

  if (presets.length === 0) {
    return (
      <div className="mt-8 rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
        아직 준비된 추천 조합이 없습니다.
        <div className="mt-3">
          <Link href="/" className="text-blue-600 hover:underline">
            지도로 직접 찾아보기 →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
      {presets.map((p) => (
        <Link
          key={p.code}
          href={presetHref(p)}
          onClick={() => logEvent("explore_tile_click", { preset: p.code })}
          className="group rounded-2xl border border-gray-200 bg-white p-4 shadow-sm
                     transition-all hover:border-blue-300 hover:shadow-md"
        >
          <div className="flex items-start gap-3">
            <span className="text-2xl" aria-hidden>
              {p.emoji}
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-gray-900 group-hover:text-blue-700">
                {p.title}
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">{p.description}</p>
            </div>
          </div>
          <div className="mt-3 text-right text-xs font-medium text-blue-600">
            추천 보기 →
          </div>
        </Link>
      ))}
    </div>
  );
}
