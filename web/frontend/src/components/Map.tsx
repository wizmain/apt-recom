import { useEffect, useRef } from 'react';
import type { Apartment, ScoredApartment, MapBounds } from '../types/apartment';
import { API_BASE } from '../config';

/* eslint-disable @typescript-eslint/no-explicit-any -- Kakao Maps SDK has no TypeScript types */
declare global {
  interface Window {
    kakao: any;
    __chatAnalyze?: (name: string, pnu: string) => void;
    __detailClick?: (pnu: string) => void;
    __compareToggle?: (pnu: string, name: string) => void;
    __closeInfoWindow?: () => void;
  }
}

interface MapProps {
  apartments: Apartment[];
  scoredResults: ScoredApartment[];
  onBoundsChange?: (bounds: MapBounds) => void;
  onMarkerClick?: (pnu: string) => void;
  onAnalyzeApartment?: (name: string, pnu: string) => void;
  onDetailClick?: (pnu: string) => void;
  onCompareToggle?: (pnu: string, name: string) => void;
  compareSelected?: string[];
  highlightApts?: { pnu: string; bld_nm: string; lat: number; lng: number; score?: number }[];
  chatFocusApts?: { lat: number; lng: number }[];
  focusPnu?: { pnu: string; lat: number; lng: number; name: string } | null;
  onFocusPnuHandled?: () => void;
  searchKeywords?: string[];
}

export default function Map({ apartments, scoredResults, onBoundsChange, onMarkerClick, onAnalyzeApartment, onDetailClick, onCompareToggle, compareSelected = [], highlightApts, chatFocusApts, focusPnu, onFocusPnuHandled, searchKeywords }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const clustererRef = useRef<any>(null);
  const highlightMarkersRef = useRef<any[]>([]);
  const infoWindowRef = useRef<any>(null);
  const openMarkerRef = useRef<any>(null);  // 현재 팝업이 열린 마커 추적
  const isInitializedRef = useRef(false);

  // 콜백을 ref로 저장 (의존성 문제 방지)
  const onBoundsChangeRef = useRef(onBoundsChange);
  const onMarkerClickRef = useRef(onMarkerClick);
  const onAnalyzeApartmentRef = useRef(onAnalyzeApartment);
  const onDetailClickRef = useRef(onDetailClick);
  const onCompareToggleRef = useRef(onCompareToggle);
  const compareSelectedRef = useRef(compareSelected);

  useEffect(() => {
    onBoundsChangeRef.current = onBoundsChange;
    onMarkerClickRef.current = onMarkerClick;
    onAnalyzeApartmentRef.current = onAnalyzeApartment;
    onDetailClickRef.current = onDetailClick;
    onCompareToggleRef.current = onCompareToggle;
    compareSelectedRef.current = compareSelected;
  });

  // 이전 scoredResults의 첫 번째 PNU를 추적 (같으면 panTo 안 함)
  const prevFirstPnuRef = useRef<string | null>(null);

  function buildPopupHtml(displayName: string, pnu: string, hhldCnt?: number, score?: number) {
    const escapedName = displayName.replace(/'/g, "\\'").replace(/\d+위\s*/, '');
    const isCompared = compareSelectedRef.current.includes(pnu);
    const compareFull = compareSelectedRef.current.length >= 2 && !isCompared;
    const btnStyle = 'padding:5px 10px;font-size:11px;border:none;border-radius:4px;cursor:pointer;white-space:nowrap;';
    return `
      <div style="padding:10px 14px;font-size:13px;min-width:280px;max-width:calc(100vw - 40px);position:relative;">
        <button onclick="window.__closeInfoWindow()"
          style="position:absolute;top:4px;right:6px;background:none;border:none;cursor:pointer;font-size:16px;color:#999;line-height:1;"
          title="닫기">&times;</button>
        <strong style="display:block;margin-right:18px;">${displayName}</strong>
        ${hhldCnt != null ? `<span style="color:#666;font-size:12px;">${hhldCnt}세대</span><br/>` : ''}
        ${score != null ? `<span style="color:#2563eb;font-weight:bold;font-size:12px;">${score.toFixed(1)}점</span><br/>` : ''}
        <div style="display:flex;gap:5px;margin-top:8px;">
          <button onclick="window.__detailClick('${pnu}')"
            style="${btnStyle}background:#f3f4f6;color:#374151;">
            📋 상세보기
          </button>
          <button onclick="window.__chatAnalyze('${escapedName}', '${pnu}')"
            style="${btnStyle}background:#2563eb;color:#fff;">
            💬 챗봇 분석
          </button>
          <button onclick="window.__compareToggle('${pnu}', '${escapedName}')"
            style="${btnStyle}background:${isCompared ? '#dc2626' : '#7c3aed'};color:#fff;${compareFull ? 'opacity:0.4;pointer-events:none;' : ''}">
            ${isCompared ? '✕ 비교해제' : '⚖ 비교담기'}
          </button>
        </div>
      </div>
    `;
  }

  // Global handlers for InfoWindow button clicks
  useEffect(() => {
    window.__chatAnalyze = (name: string, pnu: string) => {
      onAnalyzeApartmentRef.current?.(name, pnu);
    };
    window.__detailClick = (pnu: string) => {
      onDetailClickRef.current?.(pnu);
      infoWindowRef.current?.close();
    };
    window.__compareToggle = (pnu: string, name: string) => {
      onCompareToggleRef.current?.(pnu, name);
    };
    window.__closeInfoWindow = () => {
      infoWindowRef.current?.close();
      openMarkerRef.current = null;
    };
    return () => {
      delete window.__chatAnalyze;
      delete window.__detailClick;
      delete window.__compareToggle;
      delete window.__closeInfoWindow;
    };
  }, []);

  // 지도 초기화 (한번만)
  useEffect(() => {
    if (!containerRef.current || isInitializedRef.current) return;
    if (!window.kakao) return;

    const initMap = () => {
      if (!containerRef.current || isInitializedRef.current) return;
      isInitializedRef.current = true;

      const map = new window.kakao.maps.Map(containerRef.current, {
        center: new window.kakao.maps.LatLng(37.5666, 126.9784),  // 서울시청
        level: 5,  // 구 단위 줌 (마커 로딩 속도 개선)
      });
      mapRef.current = map;

      clustererRef.current = new window.kakao.maps.MarkerClusterer({
        map,
        averageCenter: true,
        minLevel: 5,
        disableClickZoom: false,
        styles: [{
          width: '40px', height: '40px',
          background: 'rgba(37, 99, 235, 0.7)',
          borderRadius: '50%',
          color: '#fff',
          textAlign: 'center',
          lineHeight: '40px',
          fontSize: '14px',
          fontWeight: 'bold',
        }],
      });

      infoWindowRef.current = new window.kakao.maps.InfoWindow({ zIndex: 10 });

      // bounds 전달 헬퍼
      const emitBounds = () => {
        const bounds = map.getBounds();
        const sw = bounds.getSouthWest();
        const ne = bounds.getNorthEast();
        onBoundsChangeRef.current?.({
          sw: { lat: sw.getLat(), lng: sw.getLng() },
          ne: { lat: ne.getLat(), lng: ne.getLng() },
        });
      };

      // 지도 이동/줌 시 bounds 전달
      window.kakao.maps.event.addListener(map, 'idle', emitBounds);

      // 초기 로딩: 지도 생성 직후 현재 영역 마커 로딩
      setTimeout(emitBounds, 100);
    };

    if (window.kakao.maps && window.kakao.maps.LatLng) {
      initMap();
    } else {
      window.kakao.maps.load(initMap);
    }
  }, []);

  // 아파트 마커 (클러스터링)
  useEffect(() => {
    if (!mapRef.current || !clustererRef.current) return;

    clustererRef.current.clear();

    const markers = apartments
      .filter(apt => apt.lat != null && apt.lng != null)
      .map(apt => {
        const marker = new window.kakao.maps.Marker({
          position: new window.kakao.maps.LatLng(apt.lat, apt.lng),
          title: apt.bld_nm || '',
        });

        window.kakao.maps.event.addListener(marker, 'click', () => {
          if (openMarkerRef.current === marker) {
            infoWindowRef.current?.close();
            openMarkerRef.current = null;
          } else {
            infoWindowRef.current?.setContent(buildPopupHtml(apt.bld_nm || '이름없음', apt.pnu, apt.total_hhld_cnt || 0));
            infoWindowRef.current?.open(mapRef.current, marker);
            openMarkerRef.current = marker;
          }
        });

        return marker;
      });

    clustererRef.current.addMarkers(markers);
  }, [apartments]);

  // 스코어 결과 하이라이트
  useEffect(() => {
    if (!mapRef.current) return;

    // 기존 하이라이트 제거
    highlightMarkersRef.current.forEach(m => m.setMap(null));
    highlightMarkersRef.current = [];

    if (scoredResults.length === 0) {
      prevFirstPnuRef.current = null;
      return;
    }

    // 순위별 색상 마커 (1위=빨강, 2위=주황, 3위=파랑, 나머지=초록)
    const rankColors = ['%23dc2626', '%23ea580c', '%23e11d48', '%23be123c', '%23be123c'];
    const makeRankMarker = (rank: number) => {
      const color = rankColors[rank] || '%2316a34a';
      const svg = `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z" fill="${decodeURIComponent(color)}"/><circle cx="15" cy="14" r="8" fill="white"/><text x="15" y="18" text-anchor="middle" font-size="12" font-weight="bold" fill="${decodeURIComponent(color)}">${rank + 1}</text></svg>`)}`;
      return new window.kakao.maps.MarkerImage(
        svg,
        new window.kakao.maps.Size(30, 40),
        { offset: new window.kakao.maps.Point(15, 40) },
      );
    };

    scoredResults.slice(0, 5).forEach((apt, idx) => {
      const marker = new window.kakao.maps.Marker({
        map: mapRef.current,
        position: new window.kakao.maps.LatLng(apt.lat, apt.lng),
        title: apt.bld_nm,
        image: makeRankMarker(idx),
        zIndex: 3,
      });

      window.kakao.maps.event.addListener(marker, 'click', () => {
        if (openMarkerRef.current === marker) {
          infoWindowRef.current?.close();
          openMarkerRef.current = null;
          return;
        }
        infoWindowRef.current?.setContent(
          buildPopupHtml(`${idx + 1}위 ${apt.bld_nm}`, apt.pnu, undefined, apt.score)
        );
        infoWindowRef.current?.open(mapRef.current, marker);
        openMarkerRef.current = marker;
      });

      highlightMarkersRef.current.push(marker);
    });

    // 결과가 바뀌었을 때 전체 결과가 보이도록 fitBounds
    const resultKey = scoredResults.slice(0, 5).map(a => a.pnu).join(',');
    if (resultKey !== prevFirstPnuRef.current) {
      prevFirstPnuRef.current = resultKey;

      const bounds = new window.kakao.maps.LatLngBounds();
      scoredResults.slice(0, 5).forEach(apt => {
        if (apt.lat != null && apt.lng != null) {
          bounds.extend(new window.kakao.maps.LatLng(apt.lat, apt.lng));
        }
      });
      mapRef.current.setBounds(bounds, 100);
    }
  }, [scoredResults]);

  // 검색어 변경 시 해당 지역 아파트로 fitBounds (모든 키워드 합산)
  const prevSearchRef = useRef<string>('');
  useEffect(() => {
    const key = (searchKeywords || []).join(',');
    if (!mapRef.current || !key || key === prevSearchRef.current) return;
    prevSearchRef.current = key;

    // 각 키워드별 검색 후 합산 fitBounds
    const keywords = searchKeywords || [];
    Promise.all(
      keywords.map(kw =>
        fetch(`${API_BASE}/api/apartments/search?q=${encodeURIComponent(kw)}`)
          .then(res => res.json())
          .catch(() => [])
      )
    ).then((results: Array<Array<{ lat: number; lng: number }>>) => {
      if (!window.kakao?.maps || !mapRef.current) return;
      const bounds = new window.kakao.maps.LatLngBounds();
      let count = 0;
      for (const data of results) {
        for (const apt of data) {
          if (apt.lat != null && apt.lng != null) {
            bounds.extend(new window.kakao.maps.LatLng(apt.lat, apt.lng));
            count++;
          }
        }
      }
      if (count > 0) {
        mapRef.current.setBounds(bounds, 100);
      }
    });
  }, [searchKeywords]);

  // Chat highlight — highlightApts 좌표 데이터로 직접 마커 생성
  const chatHighlightRef = useRef<any[]>([]);
  useEffect(() => {
    if (!mapRef.current) return;

    // Remove old chat highlights
    chatHighlightRef.current.forEach(m => m.setMap(null));
    chatHighlightRef.current = [];

    if (!highlightApts || highlightApts.length === 0) return;

    const chatSvg = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="28" height="38" viewBox="0 0 28 38"><path d="M14 0C6.3 0 0 6.3 0 14c0 9.8 14 24 14 24s14-14.2 14-24C28 6.3 21.7 0 14 0z" fill="%23dc2626"/><circle cx="14" cy="13" r="6" fill="white"/></svg>')}`;
    const chatMarkerImage = new window.kakao.maps.MarkerImage(
      chatSvg,
      new window.kakao.maps.Size(28, 38),
      { offset: new window.kakao.maps.Point(14, 38) },
    );

    highlightApts.forEach(apt => {
      if (apt.lat == null || apt.lng == null) return;
      const marker = new window.kakao.maps.Marker({
        map: mapRef.current,
        position: new window.kakao.maps.LatLng(apt.lat, apt.lng),
        title: apt.bld_nm,
        image: chatMarkerImage,
        zIndex: 5,
      });
      window.kakao.maps.event.addListener(marker, 'click', () => {
        if (openMarkerRef.current === marker) {
          infoWindowRef.current?.close();
          openMarkerRef.current = null;
        } else {
          infoWindowRef.current?.setContent(buildPopupHtml(apt.bld_nm, apt.pnu));
          infoWindowRef.current?.open(mapRef.current, marker);
          openMarkerRef.current = marker;
        }
      });
      chatHighlightRef.current.push(marker);
    });
  }, [highlightApts]);

  // Chat focus — fitBounds to chat result apartments
  useEffect(() => {
    if (!mapRef.current || !chatFocusApts || chatFocusApts.length === 0) return;

    const bounds = new window.kakao.maps.LatLngBounds();
    chatFocusApts.forEach(a => {
      if (a.lat != null && a.lng != null) {
        bounds.extend(new window.kakao.maps.LatLng(a.lat, a.lng));
      }
    });
    mapRef.current.setBounds(bounds, 80);
  }, [chatFocusApts]);

  // 특정 아파트로 포커스 (결과 카드 클릭 시)
  useEffect(() => {
    if (!mapRef.current || !focusPnu) return;

    // 지도 이동
    const pos = new window.kakao.maps.LatLng(focusPnu.lat, focusPnu.lng);
    mapRef.current.setLevel(3); // 가까이 줌
    mapRef.current.panTo(pos);

    // 팝업 표시
    setTimeout(() => {
      const content = buildPopupHtml(focusPnu.name, focusPnu.pnu);
      infoWindowRef.current?.setContent(content);
      // 임시 마커에 팝업 열기
      const tempMarker = new window.kakao.maps.Marker({ position: pos });
      infoWindowRef.current?.open(mapRef.current, tempMarker);
      openMarkerRef.current = tempMarker;
      onFocusPnuHandled?.();
    }, 300);
  }, [focusPnu, onFocusPnuHandled]);

  return (
    <div
      ref={containerRef}
      className="w-full h-full"
      style={{ minHeight: '300px' }}
    />
  );
}
