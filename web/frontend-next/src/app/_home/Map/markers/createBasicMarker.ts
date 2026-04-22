// src/app/_home/Map/markers/createBasicMarker.ts
"use client";

/**
 * 일반 아파트 마커 — Kakao 기본 Marker (파란 핀).
 * MarkerClusterer 에 등록되어 줌 아웃 시 클러스터링된다.
 */
export function createBasicMarker(
  position: kakao.maps.LatLng,
  title: string,
  onClick: () => void,
): kakao.maps.Marker {
  const marker = new window.kakao!.maps.Marker({
    position,
    title,
    clickable: true,
  });
  window.kakao!.maps.event.addListener(marker, "click", onClick);
  return marker;
}
