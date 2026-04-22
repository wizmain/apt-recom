// src/app/_home/Map/useKakaoReady.ts
"use client";

import { useEffect, useState } from "react";

/**
 * Kakao Maps SDK 준비 감지.
 * layout.tsx 의 <Script afterInteractive /> 가 window.kakao 를 붙인 뒤,
 * kakao.maps.load(cb) 공식 API 로 LatLng/MarkerClusterer 등 사용 가능 상태에 진입.
 */
export function useKakaoReady(): boolean {
  const [ready, setReady] = useState<boolean>(false);

  useEffect(() => {
    if (ready) return;
    // 이미 sdk 가 로드 + load callback 이 실행된 상태인지
    if (typeof window !== "undefined" && window.kakao?.maps?.LatLng) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 외부 SDK 준비 상태를 React state 로 동기화 (일회성)
      setReady(true);
      return;
    }
    // 아직 SDK 자체가 window 에 붙지 않은 상태 — 일정 간격으로 확인
    let cancelled = false;
    const check = () => {
      if (cancelled) return;
      const k = window.kakao;
      if (k?.maps?.load) {
        k.maps.load(() => {
          if (!cancelled) setReady(true);
        });
      } else {
        setTimeout(check, 100);
      }
    };
    check();
    return () => {
      cancelled = true;
    };
  }, [ready]);

  return ready;
}
