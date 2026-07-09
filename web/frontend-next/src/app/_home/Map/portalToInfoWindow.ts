// src/app/_home/Map/portalToInfoWindow.ts
"use client";

import { flushSync } from "react-dom";
import { createRoot, type Root } from "react-dom/client";
import type { ReactElement } from "react";

/**
 * Kakao InfoWindow 에 React 컴포넌트 마운트.
 * HTML string + onclick 패턴을 React 이벤트로 대체해 window 전역 콜백 제거.
 *
 * @returns cleanup 함수 (InfoWindow close + React root unmount)
 */
/** 기본 마커 핀 그래픽 높이(px) — 카드가 핀을 덮지 않도록 띄우는 간격. */
const MARKER_CLEARANCE_PX = 42;

export function openInfoWindow(
  map: kakao.maps.Map,
  position: kakao.maps.LatLng,
  content: ReactElement,
): () => void {
  const container = document.createElement("div");
  const root: Root = createRoot(container);
  // 마커 핀 그래픽이 가려지지 않도록 카드 하단에 핀 높이만큼 여백 확보.
  // (InfoWindow 는 꼬리 끝을 앵커에 붙여 위로 펼쳐지므로 핀을 항상 덮는다 —
  // "지도로 이동 시 마커가 안 보이는" 버그의 원인. CustomOverlay + yAnchor 1 로
  // 카드 바닥을 앵커에서 핀 높이만큼 띄워 결정적으로 해소.)
  container.style.paddingBottom = `${MARKER_CLEARANCE_PX}px`;
  const overlay = new window.kakao!.maps.CustomOverlay({
    position,
    content: container,
    zIndex: 10,
    xAnchor: 0.5,
    yAnchor: 1,
  });
  // 콘텐츠를 먼저 그린 뒤 지도에 올린다: React 18 createRoot.render 는 비동기라
  // 빈 컨테이너(높이 0) 상태로 올라가면 앵커 계산이 어긋난다. flushSync 는
  // lifecycle(useEffect) 안에서 무시되므로 마이크로태스크로 미뤄 순서를 보장.
  let closed = false;
  queueMicrotask(() => {
    if (closed) return;
    flushSync(() => root.render(content));
    overlay.setMap(map);
  });
  return () => {
    closed = true;
    overlay.setMap(null);
    queueMicrotask(() => {
      root.unmount();
      container.remove();
    });
  };
}
