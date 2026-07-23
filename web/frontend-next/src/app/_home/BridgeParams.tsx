"use client";

import { useBridgeParams } from "@/hooks/useBridgeParams";
import { useViewParam } from "@/hooks/useViewParam";

/**
 * useBridgeParams(내부 useSearchParams)를 Suspense 경계 안으로 격리하는 래퍼.
 *
 * next build 프리렌더 단계에서 useSearchParams 는 CSR bailout 을 유발한다
 * (missing-suspense-with-csr-bailout). HomeShell 최상단에서 직접 호출하면
 * 페이지 "/" 전체 프리렌더가 실패하므로, 이 컴포넌트만 <Suspense> 로 감싸
 * 훅 호출을 서브트리로 격리하고 나머지 페이지의 프리렌더를 유지한다.
 *
 * 렌더 출력은 없다(부트스트랩 side-effect 전용).
 */
export function BridgeParams(): null {
  useBridgeParams();
  useViewParam(); // /?view=dashboard — 대시보드 뷰 부트스트랩 (콘텐츠 네비 진입점)
  return null;
}
