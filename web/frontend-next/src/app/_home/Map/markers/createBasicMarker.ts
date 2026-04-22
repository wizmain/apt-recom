// src/app/_home/Map/markers/createBasicMarker.ts
"use client";

/**
 * 일반 아파트 마커 (작은 회색 점).
 * CustomOverlay 로 DOM 요소 자체를 지도에 올린다 (Marker 아닌 이유: 초소형 + 인터랙션 제어).
 */
export function createBasicMarker(
  position: kakao.maps.LatLng,
  onClick: () => void,
): kakao.maps.CustomOverlay {
  const el = document.createElement("div");
  el.style.cssText =
    "width:10px;height:10px;border-radius:50%;background:#6B7280;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.2);cursor:pointer;";
  el.addEventListener("click", onClick);
  return new window.kakao!.maps.CustomOverlay({
    position,
    content: el,
    yAnchor: 0.5,
    clickable: true,
  });
}
