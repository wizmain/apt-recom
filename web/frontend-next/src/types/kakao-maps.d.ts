// src/types/kakao-maps.d.ts
export {};

declare global {
  interface Window {
    kakao?: typeof kakao;
  }
}

declare namespace kakao.maps {
  class LatLng {
    constructor(lat: number, lng: number);
    getLat(): number;
    getLng(): number;
  }

  class LatLngBounds {
    getSouthWest(): LatLng;
    getNorthEast(): LatLng;
  }

  interface MapOptions {
    center: LatLng;
    level?: number;
  }
  class Map {
    constructor(container: HTMLElement, options: MapOptions);
    getBounds(): LatLngBounds;
    setCenter(latlng: LatLng): void;
    getCenter(): LatLng;
    setLevel(level: number): void;
    getLevel(): number;
    panTo(latlng: LatLng): void;
  }

  interface MarkerOptions {
    position: LatLng;
    image?: MarkerImage;
    title?: string;
    clickable?: boolean;
  }
  class Marker {
    constructor(options: MarkerOptions);
    setMap(map: Map | null): void;
    getPosition(): LatLng;
  }

  interface MarkerImageOptions {
    offset?: Point;
  }
  class Point {
    constructor(x: number, y: number);
  }
  class Size {
    constructor(width: number, height: number);
  }
  class MarkerImage {
    constructor(src: string, size: Size, options?: MarkerImageOptions);
  }

  interface CustomOverlayOptions {
    position: LatLng;
    content: HTMLElement | string;
    yAnchor?: number;
    xAnchor?: number;
    zIndex?: number;
    clickable?: boolean;
  }
  class CustomOverlay {
    constructor(options: CustomOverlayOptions);
    setMap(map: Map | null): void;
  }

  interface InfoWindowOptions {
    position?: LatLng;
    content: HTMLElement | string;
    zIndex?: number;
    removable?: boolean;
  }
  class InfoWindow {
    constructor(options: InfoWindowOptions);
    open(map: Map, marker?: Marker): void;
    close(): void;
    setContent(content: HTMLElement | string): void;
    setPosition(pos: LatLng): void;
  }

  interface MarkerClustererOptions {
    map: Map;
    averageCenter?: boolean;
    minLevel?: number;
    gridSize?: number;
  }
  class MarkerClusterer {
    constructor(options: MarkerClustererOptions);
    addMarkers(markers: Marker[]): void;
    clear(): void;
    removeMarkers(markers: Marker[]): void;
  }

  namespace event {
    function addListener<T = unknown>(
      target: unknown,
      type: string,
      handler: (event?: T) => void,
    ): void;
    function removeListener<T = unknown>(
      target: unknown,
      type: string,
      handler: (event?: T) => void,
    ): void;
  }

  function load(callback: () => void): void;
}
