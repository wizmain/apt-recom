// src/hooks/useBridgeParams.ts
"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/lib/store";
import { useCodes } from "@/hooks/useCodes";
import type { FilterState } from "@/lib/store/searchSlice";
import { FILTER_KEYS } from "@/lib/instagramContent";
import { logEvent } from "@/lib/logEvent";

/**
 * 쿼리파라미터 → store 부트스트랩 훅.
 * 콘텐츠 딥링크: FilterState 9키 + content_slug/content_cta 소비.
 *
 * 단지 상세(SSR) → 홈 딥링크(`/?nudges=...&sigungu_code=...&region_label=...`) 로 진입할 때,
 * 쿼리파라미터를 1회 소비해 store(`selectedNudges`, `selectedRegion`)를 초기화한다.
 * 이후 기존 `useNudge` 가 변화를 감지해 자동으로 추천을 실행한다.
 *
 * 가드 조건:
 * - 경로가 `/` (selectedPnu === null, useUrlSyncedPnu 와 충돌 방지)
 * - `nudges` 파라미터가 존재할 때만 동작
 * - nudge 코드(common_code group='nudge')가 로드된 뒤에만 적용. 미로딩 상태에서
 *   화이트리스트 필터를 돌리면 정상 코드까지 모두 걸러져 추천이 비는 회귀가 생김.
 * - 유효 코드 화이트리스트로 필터(변조/오타된 딥링크의 깨진 코드를 store 에 주입 방지).
 * - 소비 후 history.replaceState 로 쿼리 제거 (뒤로가기/공유 시 재실행 방지).
 * - 적용은 마운트 생명주기 동안 1회만 (appliedRef).
 *
 * 제약:
 * - useEffect 내에서 API 직접 호출 금지 — store 액션(`selectRegion`, `setSelectedNudges`)만 호출.
 * - `selectRegion` 은 async 이지만 부트스트랩 목적이므로 fire-and-forget 처리.
 * - SSR 안전: "use client" 로 클라이언트 전용 렌더링. window 접근은 useEffect 내부에서만.
 */
export function useBridgeParams(): void {
  const searchParams = useSearchParams();
  const selectedPnu = useAppStore((s) => s.selectedPnu);
  const applyFilters = useAppStore((s) => s.applyFilters);
  const selectRegion = useAppStore((s) => s.selectRegion);
  const setSelectedNudges = useAppStore((s) => s.setSelectedNudges);
  const { codes, loading } = useCodes("nudge");
  const appliedRef = useRef(false);

  useEffect(() => {
    // 1회만 적용 — 쿼리 제거 후 재렌더/재실행 방지.
    if (appliedRef.current) return;
    // 가드: selectedPnu 가 있으면 상세 페이지 컨텍스트이므로 동작하지 않음.
    if (selectedPnu !== null) return;

    const nudgesParam = searchParams.get("nudges");
    if (!nudgesParam) return;

    // 유효 코드가 로드되기 전에는 적용 보류. 로드 완료(loading=false)되면
    // deps 변화로 effect 가 재실행되어 적용된다.
    if (loading) return;

    const validCodes = codes.map((c) => c.code);
    const nudges = nudgesParam
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && validCodes.includes(s));

    // 소비 확정 — 유효/무효 여부와 무관하게 쿼리는 1회 정리하고 재실행을 막는다.
    appliedRef.current = true;
    window.history.replaceState(null, "", window.location.pathname);

    // 유효 프리셋이 하나도 없으면(변조/오타 링크) 부트스트랩 생략.
    if (nudges.length === 0) return;

    const sigCode = searchParams.get("sigungu_code");
    const regionLabel = searchParams.get("region_label");

    // 콘텐츠 딥링크 필터 소비 — FilterState 9키 allowlist, Number.isFinite 통과 값만.
    // 적용 순서 중요: applyFilters → selectRegion(내부 fetchApartments) → setSelectedNudges.
    // 필터를 먼저 넣지 않으면 최초 아파트 조회가 필터 없이 나간다 (PRD §7).
    const filters: FilterState = {};
    for (const key of FILTER_KEYS) {
      const raw = searchParams.get(key);
      if (raw === null) continue;
      const num = Number(raw);
      if (!Number.isFinite(num)) continue;
      filters[key as keyof FilterState] = num;
    }
    const filterCount = Object.keys(filters).length;
    if (filterCount > 0) applyFilters(filters);

    // 지역 세팅 (sigungu_code 가 있는 경우만)
    if (sigCode) {
      const label = regionLabel ?? sigCode;
      void selectRegion({ type: "sigungu", code: sigCode, label });
    }

    // nudge 프리셋 일괄 세팅 — 유효 코드 화이트리스트로 한 번 더 방어.
    setSelectedNudges(nudges, validCodes);

    // 콘텐츠 유입 도달 측정 — content_slug 가 있을 때만 (store 미주입, 로깅 전용).
    const contentSlug = searchParams.get("content_slug");
    if (contentSlug) {
      logEvent("content_map_arrival", {
        content_slug: contentSlug,
        content_cta: searchParams.get("content_cta") ?? undefined,
        nudge_count: nudges.length,
        filter_count: filterCount,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);
  // deps: [loading] — 코드 로드 완료 시 1회 적용. searchParams 를 deps 에 넣지 않는 이유는
  // 쿼리 제거(replaceState) 후 재실행을 피하기 위함이며, 재실행 방지는 appliedRef 가 보장한다.
}
