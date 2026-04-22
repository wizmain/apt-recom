// src/app/_home/Map/MapView.tsx
"use client";

import { useEffect, useRef } from "react";
import type { Apartment, MapBounds, ScoredApartment } from "@/types/apartment";
import type { ChatHighlightApt } from "@/lib/store/chatSlice";
import type { FocusPnu } from "@/lib/store/mapSlice";
import { useKakaoReady } from "./useKakaoReady";
import { useMapInstance } from "./useMapInstance";
import { createBasicMarker } from "./markers/createBasicMarker";
import { createRankedMarker } from "./markers/createRankedMarker";
import { createChatMarker } from "./markers/createChatMarker";
import { InfoWindowBody } from "./InfoWindowBody";
import { openInfoWindow } from "./portalToInfoWindow";

export type MapViewProps = {
  apartments: Apartment[];
  scoredApartments: ScoredApartment[];
  chatHighlights: ChatHighlightApt[];
  focusPnu: FocusPnu | null;
  onBoundsChange: (bounds: MapBounds) => void;
  onDetailOpen: (pnu: string) => void;
  onChatAnalyze: (name: string, pnu: string) => void;
  onCompareToggle: (pnu: string, name: string) => void;
};

export function MapView(props: MapViewProps) {
  const {
    apartments,
    scoredApartments,
    chatHighlights,
    focusPnu,
    onBoundsChange,
    onDetailOpen,
    onChatAnalyze,
    onCompareToggle,
  } = props;

  const containerRef = useRef<HTMLDivElement>(null);
  const ready = useKakaoReady();
  const { mapRef } = useMapInstance(containerRef, ready, onBoundsChange);

  // 스코어드(순위) 마커 / 챗봇 하이라이트 / 일반 마커 3레이어 관리
  const rankedOverlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);
  const chatOverlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);
  const basicOverlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);
  const closeInfoRef = useRef<(() => void) | null>(null);

  const showInfo = (apt: { pnu: string; bld_nm: string; lat: number; lng: number }) => {
    if (!mapRef.current) return;
    closeInfoRef.current?.();
    const k = window.kakao!.maps;
    const position = new k.LatLng(apt.lat, apt.lng);
    closeInfoRef.current = openInfoWindow(
      mapRef.current,
      position,
      <InfoWindowBody
        apt={{ pnu: apt.pnu, bld_nm: apt.bld_nm }}
        onDetailOpen={(pnu) => {
          closeInfoRef.current?.();
          closeInfoRef.current = null;
          onDetailOpen(pnu);
        }}
        onChatAnalyze={(name, pnu) => {
          closeInfoRef.current?.();
          closeInfoRef.current = null;
          onChatAnalyze(name, pnu);
        }}
        onCompareToggle={(pnu, name) => onCompareToggle(pnu, name)}
        onClose={() => {
          closeInfoRef.current?.();
          closeInfoRef.current = null;
        }}
      />,
    );
  };

  // 순위 마커 갱신 (scoredApartments 우선)
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    rankedOverlaysRef.current.forEach((o) => o.setMap(null));
    rankedOverlaysRef.current = [];
    scoredApartments.forEach((apt, idx) => {
      if (!apt.lat || !apt.lng) return;
      const rank = idx + 1;
      const ov = createRankedMarker(
        new k.LatLng(apt.lat, apt.lng),
        rank,
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      ov.setMap(mapRef.current);
      rankedOverlaysRef.current.push(ov);
    });
    return () => {
      rankedOverlaysRef.current.forEach((o) => o.setMap(null));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 는 매 렌더 생성되므로 제외 (안정적 참조 우회)
  }, [scoredApartments, ready, mapRef]);

  // 챗봇 하이라이트 마커
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    chatOverlaysRef.current.forEach((o) => o.setMap(null));
    chatOverlaysRef.current = [];
    chatHighlights.forEach((apt) => {
      const ov = createChatMarker(
        new k.LatLng(apt.lat, apt.lng),
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      ov.setMap(mapRef.current);
      chatOverlaysRef.current.push(ov);
    });
    return () => {
      chatOverlaysRef.current.forEach((o) => o.setMap(null));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 매 렌더 생성 제외
  }, [chatHighlights, ready, mapRef]);

  // 일반 아파트 마커 (스코어·챗봇이 없으면 기본 표시)
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    basicOverlaysRef.current.forEach((o) => o.setMap(null));
    basicOverlaysRef.current = [];
    if (scoredApartments.length > 0) return; // 순위 모드에서는 숨김
    apartments.forEach((apt) => {
      const ov = createBasicMarker(
        new k.LatLng(apt.lat, apt.lng),
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      ov.setMap(mapRef.current);
      basicOverlaysRef.current.push(ov);
    });
    return () => {
      basicOverlaysRef.current.forEach((o) => o.setMap(null));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 매 렌더 생성 제외
  }, [apartments, scoredApartments.length, ready, mapRef]);

  // focus 이동
  useEffect(() => {
    if (!mapRef.current || !ready || !focusPnu) return;
    const k = window.kakao!.maps;
    mapRef.current.panTo(new k.LatLng(focusPnu.lat, focusPnu.lng));
    showInfo({
      pnu: focusPnu.pnu,
      bld_nm: focusPnu.name,
      lat: focusPnu.lat,
      lng: focusPnu.lng,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 매 렌더 생성 제외
  }, [focusPnu, ready, mapRef]);

  return (
    <div ref={containerRef} className="w-full h-full">
      {!ready ? (
        <div className="flex items-center justify-center h-full text-gray-500 text-sm">
          지도를 불러오는 중...
        </div>
      ) : null}
    </div>
  );
}
