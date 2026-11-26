// src/app/_home/Map/markers/createTrendMarker.ts
"use client";

import type { MapTrend } from "@/types/rising";
import { createBasicMarker } from "./createBasicMarker";

/**
 * 오르는 단지 추세 마커 — 6개월 변화가 상승/하락이면 핀 위에 배지(▲3.2% / ▼1.8%)를 얹는다.
 * 보합(±2%)·비교 부족·표본 적음·집계 없음은 기본 핀(createBasicMarker)과 같다.
 * 색은 오르는 단지 화면과 같은 계열(상승 초록 · 하락 빨강).
 */
const TREND_COLORS = { up: "#059669", down: "#DC2626" } as const;
const PIN_COLOR = "#3B82F6";
const ICON_WIDTH = 58;
const ICON_HEIGHT = 56;
const BADGE_HEIGHT = 18;

function trendBadgeSvg(direction: "up" | "down", changePct: number): string {
  const color = TREND_COLORS[direction];
  const label = `${direction === "up" ? "▲" : "▼"}${Math.abs(changePct).toFixed(1)}%`;
  const pinTop = BADGE_HEIGHT + 2;
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${ICON_WIDTH}" height="${ICON_HEIGHT}" viewBox="0 0 ${ICON_WIDTH} ${ICON_HEIGHT}">` +
      `<rect x="1" y="1" width="${ICON_WIDTH - 2}" height="${BADGE_HEIGHT - 2}" rx="8" fill="white" stroke="${color}" stroke-width="1.5"/>` +
      `<text x="${ICON_WIDTH / 2}" y="${BADGE_HEIGHT - 5}" text-anchor="middle" font-size="11" font-weight="700" font-family="sans-serif" fill="${color}">${label}</text>` +
      `<g transform="translate(${ICON_WIDTH / 2 - 12} ${pinTop})">` +
      `<path d="M12 0C5.4 0 0 5.4 0 12c0 8.4 12 24 12 24s12-15.6 12-24C24 5.4 18.6 0 12 0z" fill="${PIN_COLOR}" stroke="${color}" stroke-width="1.5"/>` +
      `<circle cx="12" cy="12" r="4.5" fill="white"/></g></svg>`,
  )}`;
}

export function createTrendMarker(
  position: kakao.maps.LatLng,
  title: string,
  trend: MapTrend | undefined,
  onClick: () => void,
): kakao.maps.Marker {
  const direction = trend?.direction;
  if (!trend || trend.change_6m_pct === null || (direction !== "up" && direction !== "down")) {
    return createBasicMarker(position, title, onClick);
  }
  const image = new window.kakao!.maps.MarkerImage(
    trendBadgeSvg(direction, trend.change_6m_pct),
    new window.kakao!.maps.Size(ICON_WIDTH, ICON_HEIGHT),
    { offset: new window.kakao!.maps.Point(ICON_WIDTH / 2, ICON_HEIGHT) },
  );
  const marker = new window.kakao!.maps.Marker({ position, title, image, clickable: true });
  window.kakao!.maps.event.addListener(marker, "click", onClick);
  return marker;
}
