// src/app/_home/Map/markers/createRankedMarker.ts
"use client";

/**
 * 순위 컬러 마커 — Marker + MarkerImage (SVG 풍선, 1~3 위 특수색).
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
  title: string,
  onClick: () => void,
): kakao.maps.Marker {
  const color =
    (RANK_COLORS as Record<number, string>)[rank] ?? RANK_COLORS.default;
  const svg = `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z" fill="${color}"/><circle cx="15" cy="14" r="8" fill="white"/><text x="15" y="18" text-anchor="middle" font-size="12" font-weight="bold" fill="${color}">${rank}</text></svg>`,
  )}`;
  const image = new window.kakao!.maps.MarkerImage(
    svg,
    new window.kakao!.maps.Size(30, 40),
    { offset: new window.kakao!.maps.Point(15, 40) },
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
