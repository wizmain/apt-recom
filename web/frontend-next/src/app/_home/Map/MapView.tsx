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
  regionFitNonce: number;
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
    regionFitNonce,
    onBoundsChange,
    onDetailOpen,
    onChatAnalyze,
    onCompareToggle,
  } = props;

  const containerRef = useRef<HTMLDivElement>(null);
  const ready = useKakaoReady();
  const { mapRef, clustererRef } = useMapInstance(containerRef, ready, onBoundsChange);

  // 마커 3 레이어: 기본(Marker + Clusterer), 순위(Marker image), 챗봇(Marker image)
  const rankedMarkersRef = useRef<kakao.maps.Marker[]>([]);
  const chatMarkersRef = useRef<kakao.maps.Marker[]>([]);
  const basicMarkersRef = useRef<kakao.maps.Marker[]>([]);
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

  // 순위 마커 — Marker + MarkerImage (클러스터러에 넣지 않고 개별 표시)
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    rankedMarkersRef.current.forEach((m) => m.setMap(null));
    rankedMarkersRef.current = [];
    scoredApartments.forEach((apt, idx) => {
      if (!apt.lat || !apt.lng) return;
      const rank = idx + 1;
      const marker = createRankedMarker(
        new k.LatLng(apt.lat, apt.lng),
        rank,
        `${rank}위 ${apt.bld_nm}`,
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      marker.setMap(mapRef.current);
      rankedMarkersRef.current.push(marker);
    });
    return () => {
      rankedMarkersRef.current.forEach((m) => m.setMap(null));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 매 렌더 생성 제외
  }, [scoredApartments, ready, mapRef]);

  // 챗봇 하이라이트 — Marker + MarkerImage (개별 표시)
  useEffect(() => {
    if (!mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    chatMarkersRef.current.forEach((m) => m.setMap(null));
    chatMarkersRef.current = [];
    chatHighlights.forEach((apt) => {
      const marker = createChatMarker(
        new k.LatLng(apt.lat, apt.lng),
        apt.bld_nm,
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      marker.setMap(mapRef.current);
      chatMarkersRef.current.push(marker);
    });
    return () => {
      chatMarkersRef.current.forEach((m) => m.setMap(null));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 매 렌더 생성 제외
  }, [chatHighlights, ready, mapRef]);

  // 일반 아파트 마커 — MarkerClusterer 에 등록 (스코어 모드에서는 숨김)
  useEffect(() => {
    if (!mapRef.current || !ready || !clustererRef.current) return;
    const clusterer = clustererRef.current;
    const k = window.kakao!.maps;
    clusterer.clear();
    basicMarkersRef.current = [];
    if (scoredApartments.length > 0) return; // 순위 모드: 기본 마커 숨김
    const markers: kakao.maps.Marker[] = [];
    apartments.forEach((apt) => {
      if (apt.lat == null || apt.lng == null) return;
      const marker = createBasicMarker(
        new k.LatLng(apt.lat, apt.lng),
        apt.bld_nm || "",
        () => showInfo({ pnu: apt.pnu, bld_nm: apt.bld_nm, lat: apt.lat, lng: apt.lng }),
      );
      markers.push(marker);
    });
    basicMarkersRef.current = markers;
    clusterer.addMarkers(markers);
    return () => {
      clusterer.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- showInfo 매 렌더 생성 제외
  }, [apartments, scoredApartments.length, ready, mapRef, clustererRef]);

  // focus 이동 — panTo + InfoWindow
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

  // 지역 필터 선택 시 — nonce 증가를 키로 해당 지역 아파트 전체로 fitBounds (1회).
  // apartments 는 nonce 와 함께 갱신되므로 최신값이 사용됨. 의존성에 포함하면
  // 필터 변경 등 다른 이유로 apartments 가 바뀔 때도 fit 발생하므로 의도적으로 제외.
  useEffect(() => {
    if (!regionFitNonce || !mapRef.current || !ready) return;
    const k = window.kakao!.maps;
    const bounds = new k.LatLngBounds();
    let count = 0;
    for (const apt of apartments) {
      if (apt.lat != null && apt.lng != null) {
        bounds.extend(new k.LatLng(apt.lat, apt.lng));
        count++;
      }
    }
    if (count > 0) mapRef.current.setBounds(bounds, 60);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- apartments 는 nonce 와 함께 갱신
  }, [regionFitNonce]);

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
