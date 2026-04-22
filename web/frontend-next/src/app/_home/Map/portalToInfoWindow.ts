// src/app/_home/Map/portalToInfoWindow.ts
"use client";

import { createRoot, type Root } from "react-dom/client";
import type { ReactElement } from "react";

/**
 * Kakao InfoWindow 에 React 컴포넌트 마운트.
 * HTML string + onclick 패턴을 React 이벤트로 대체해 window 전역 콜백 제거.
 *
 * @returns cleanup 함수 (InfoWindow close + React root unmount)
 */
export function openInfoWindow(
  map: kakao.maps.Map,
  position: kakao.maps.LatLng,
  content: ReactElement,
): () => void {
  const container = document.createElement("div");
  const root: Root = createRoot(container);
  root.render(content);
  const iw = new window.kakao!.maps.InfoWindow({
    position,
    content: container,
    zIndex: 10,
  });
  iw.open(map);
  return () => {
    iw.close();
    queueMicrotask(() => root.unmount());
  };
}
