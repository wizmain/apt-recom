import { useState, useCallback, useRef } from 'react';
import axios from 'axios';
import type { Apartment, MapBounds } from '../types/apartment';
import { API_BASE } from '../config';

export interface ApartmentFilters {
  minArea?: number;
  maxArea?: number;
  minPrice?: number;
  maxPrice?: number;
  minFloor?: number;
  minHhld?: number;
  maxHhld?: number;
  builtAfter?: number;
  builtBefore?: number;
}

export function useApartments() {
  const [apartments, setApartments] = useState<Apartment[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<ApartmentFilters>({});
  const boundsRef = useRef<MapBounds | undefined>(undefined);
  const keywordRef = useRef<string>('');
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchApartments = useCallback(async (f: ApartmentFilters, bounds?: MapBounds, keyword?: string) => {
    try {
      setLoading(true);
      const params: Record<string, string> = {};

      const kw = keyword ?? keywordRef.current;

      // 검색 키워드가 있으면 키워드 기반, 없으면 bounds 기반
      if (kw) {
        params.q = kw;
      } else {
        const b = bounds || boundsRef.current;
        if (b) {
          params.sw_lat = String(b.sw.lat);
          params.sw_lng = String(b.sw.lng);
          params.ne_lat = String(b.ne.lat);
          params.ne_lng = String(b.ne.lng);
        }
      }

      // Filters
      if (f.minArea) params.min_area = String(f.minArea);
      if (f.maxArea) params.max_area = String(f.maxArea);
      if (f.minPrice) params.min_price = String(f.minPrice);
      if (f.maxPrice) params.max_price = String(f.maxPrice);
      if (f.minFloor) params.min_floor = String(f.minFloor);
      if (f.minHhld) params.min_hhld = String(f.minHhld);
      if (f.maxHhld) params.max_hhld = String(f.maxHhld);
      if (f.builtAfter) params.built_after = String(f.builtAfter);
      if (f.builtBefore) params.built_before = String(f.builtBefore);

      const query = new URLSearchParams(params).toString();
      const endpoint = kw ? '/api/apartments/search' : '/api/apartments';
      const url = `${API_BASE}${endpoint}${query ? `?${query}` : ''}`;
      const res = await axios.get<Apartment[]>(url);
      setApartments(res.data);
    } catch (err) {
      console.error('아파트 목록 불러오기 실패:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // 지도 영역 변경 시 호출 (디바운스) — 키워드 검색 중이면 스킵
  const onBoundsChange = useCallback((bounds: MapBounds) => {
    boundsRef.current = bounds;
    if (keywordRef.current) return; // 검색 키워드가 있으면 bounds 갱신 안 함
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchApartments(filters, bounds);
    }, 300);
  }, [filters, fetchApartments]);

  // 검색 키워드 변경
  const setKeyword = useCallback((kw: string) => {
    keywordRef.current = kw;
    if (kw) {
      // 키워드 검색: bounds 무시, 키워드로 조회
      fetchApartments(filters, undefined, kw);
    } else {
      // 키워드 해제: 현재 bounds로 복귀
      fetchApartments(filters, boundsRef.current, '');
    }
  }, [filters, fetchApartments]);

  // 필터 변경
  const applyFilters = useCallback((newFilters: ApartmentFilters) => {
    setFilters(newFilters);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchApartments(newFilters);
    }, 300);
  }, [fetchApartments]);

  const clearFilters = useCallback(() => {
    setFilters({});
    fetchApartments({});
  }, [fetchApartments]);

  return { apartments, loading, filters, applyFilters, clearFilters, onBoundsChange, setKeyword };
}
