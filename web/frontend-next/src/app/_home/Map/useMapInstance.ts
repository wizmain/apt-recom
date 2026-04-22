// src/app/_home/Map/useMapInstance.ts
"use client";

import { useEffect, useRef } from "react";
import type { MapBounds } from "@/types/apartment";

const INIT_CENTER = { lat: 37.5665, lng: 126.978 };
const INIT_LEVEL = 6;

/**
 * Kakao Map 인스턴스·클러스터러·InfoWindow 를 container 에 초기화.
 * `onBoundsChange` 는 debounced 로 호출되지 않음 — 호출부(hook `useApartments`) 에서 debounce.
 */
export function useMapInstance(
  container: React.RefObject<HTMLDivElement | null>,
  ready: boolean,
  onBoundsChange: (bounds: MapBounds) => void,
) {
  const mapRef = useRef<kakao.maps.Map | null>(null);
  const clustererRef = useRef<kakao.maps.MarkerClusterer | null>(null);

  useEffect(() => {
    if (!ready || !container.current || mapRef.current) return;
    const k = window.kakao!.maps;
    const map = new k.Map(container.current, {
      center: new k.LatLng(INIT_CENTER.lat, INIT_CENTER.lng),
      level: INIT_LEVEL,
    });
    mapRef.current = map;

    const clusterer = new k.MarkerClusterer({
      map,
      averageCenter: true,
      minLevel: 5,
      disableClickZoom: false,
      styles: [
        {
          width: "40px",
          height: "40px",
          background: "rgba(37, 99, 235, 0.7)",
          borderRadius: "50%",
          color: "#fff",
          textAlign: "center",
          lineHeight: "40px",
          fontSize: "14px",
          fontWeight: "bold",
        },
      ],
    });
    clustererRef.current = clusterer;

    const emitBounds = () => {
      const b = map.getBounds();
      onBoundsChange({
        sw: { lat: b.getSouthWest().getLat(), lng: b.getSouthWest().getLng() },
        ne: { lat: b.getNorthEast().getLat(), lng: b.getNorthEast().getLng() },
      });
    };

    // 초기 1회
    emitBounds();
    k.event.addListener(map, "idle", emitBounds);
    // cleanup 은 map 을 destroy 하지 않음 — 페이지 unmount 시 GC 기대
  }, [ready, container, onBoundsChange]);

  return { mapRef, clustererRef };
}
