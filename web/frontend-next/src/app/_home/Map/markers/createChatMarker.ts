// src/app/_home/Map/markers/createChatMarker.ts
"use client";

/**
 * 챗봇 하이라이트 마커 (빨강). 지도 강조용.
 */
export function createChatMarker(
  position: kakao.maps.LatLng,
  onClick: () => void,
): kakao.maps.CustomOverlay {
  const svg = `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="38" viewBox="0 0 28 38"><path d="M14 0C6.3 0 0 6.3 0 14c0 9.8 14 24 14 24s14-14.2 14-24C28 6.3 21.7 0 14 0z" fill="#dc2626"/><circle cx="14" cy="13" r="6" fill="white"/></svg>`,
  )}`;
  const img = document.createElement("img");
  img.src = svg;
  img.style.cssText = "width:28px;height:38px;cursor:pointer;display:block;";
  img.addEventListener("click", onClick);
  return new window.kakao!.maps.CustomOverlay({
    position,
    content: img,
    yAnchor: 1,
    clickable: true,
  });
}
