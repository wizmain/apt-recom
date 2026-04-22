// src/app/_home/Map/markers/createRankedMarker.ts
"use client";

/**
 * 순위 컬러 마커 (1~3위 특별 색상, 나머지 파란색). 풍선 모양 SVG.
 */
const RANK_COLORS = {
  1: "#EF4444",
  2: "#F97316",
  3: "#EC4899",
  default: "#3B82F6",
} as const;

export function createRankedMarker(
  position: kakao.maps.LatLng,
  rank: number,
  onClick: () => void,
): kakao.maps.CustomOverlay {
  const color =
    (RANK_COLORS as Record<number, string>)[rank] ?? RANK_COLORS.default;
  const svg = `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z" fill="${color}"/><circle cx="15" cy="14" r="8" fill="white"/><text x="15" y="18" text-anchor="middle" font-size="12" font-weight="bold" fill="${color}">${rank}</text></svg>`,
  )}`;
  const img = document.createElement("img");
  img.src = svg;
  img.style.cssText = "width:30px;height:40px;cursor:pointer;display:block;";
  img.addEventListener("click", onClick);
  return new window.kakao!.maps.CustomOverlay({
    position,
    content: img,
    yAnchor: 1,
    clickable: true,
  });
}
