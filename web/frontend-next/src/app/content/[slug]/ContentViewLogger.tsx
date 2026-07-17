"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { logEvent } from "@/lib/logEvent";

/**
 * content_view 1회 로깅 (mount 기준, 렌더 출력 없음).
 * useSearchParams 는 프리렌더에서 CSR bailout 을 유발하므로 page.tsx 에서
 * <Suspense fallback={null}> 로 격리해 사용한다 (_home/BridgeParams.tsx 선례).
 * UTM 은 허용 키(utm_source·utm_campaign)만 읽고 전체 URL/referrer 는 전송하지 않는다.
 */
export function ContentViewLogger({
  slug,
  series,
}: {
  slug: string;
  series: string;
}): null {
  const searchParams = useSearchParams();
  const loggedRef = useRef(false);
  useEffect(() => {
    if (loggedRef.current) return;
    loggedRef.current = true;
    logEvent("content_view", {
      slug,
      series,
      utm_source: searchParams.get("utm_source") ?? undefined,
      utm_campaign: searchParams.get("utm_campaign") ?? undefined,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}
