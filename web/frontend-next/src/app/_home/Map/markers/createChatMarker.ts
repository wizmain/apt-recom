// src/app/_home/Map/markers/createChatMarker.ts
"use client";

/**
 * 챗봇 하이라이트 마커 — Marker + MarkerImage (빨간 SVG 핀).
 */
export function createChatMarker(
  position: kakao.maps.LatLng,
  title: string,
  onClick: () => void,
): kakao.maps.Marker {
  const svg = `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="38" viewBox="0 0 28 38"><path d="M14 0C6.3 0 0 6.3 0 14c0 9.8 14 24 14 24s14-14.2 14-24C28 6.3 21.7 0 14 0z" fill="#dc2626"/><circle cx="14" cy="13" r="6" fill="white"/></svg>`,
  )}`;
  const image = new window.kakao!.maps.MarkerImage(
    svg,
    new window.kakao!.maps.Size(28, 38),
    { offset: new window.kakao!.maps.Point(14, 38) },
  );
  const marker = new window.kakao!.maps.Marker({
    position,
    title,
    image,
    clickable: true,
  });
  window.kakao!.maps.event.addListener(marker, "click", onClick);
  return marker;
}
