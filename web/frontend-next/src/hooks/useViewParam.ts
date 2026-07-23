"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/lib/store";

/**
 * `/?view=dashboard` 쿼리 → 홈 대시보드 뷰 부트스트랩 (1회 소비).
 *
 * viewMode 는 store 내부 상태라 URL 로 직접 열 수 없어, 콘텐츠 페이지 등
 * 외부 화면에서 실거래 대시보드로 진입하는 링크가 불가능했다 — 이 훅이
 * 그 진입점을 만든다. useBridgeParams 와 같은 계약: 1회 소비(appliedRef),
 * 소비 후 replaceState 로 쿼리 제거, useSearchParams 는 Suspense 경계
 * (BridgeParams 래퍼) 안에서만 호출.
 *
 * nudges 딥링크(useBridgeParams)와 조합될 일은 없다 — 콘텐츠 CTA 는
 * 지도(nudges)로, 대시보드 링크는 view 단독으로만 생성된다.
 */
export function useViewParam(): void {
  const searchParams = useSearchParams();
  const switchView = useAppStore((s) => s.switchView);
  const appliedRef = useRef(false);

  useEffect(() => {
    if (appliedRef.current) return;
    if (searchParams.get("view") !== "dashboard") return;
    appliedRef.current = true;
    switchView("dashboard");
    window.history.replaceState(null, "", window.location.pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
