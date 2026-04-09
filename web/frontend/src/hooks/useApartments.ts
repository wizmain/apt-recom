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

export function countActiveFilters(f: ApartmentFilters): number {
  let count = 0;
  if (f.minArea !== undefined || f.maxArea !== undefined) count++;
  if (f.minPrice !== undefined || f.maxPrice !== undefined) count++;
  if (f.minFloor !== undefined) count++;
  if (f.minHhld !== undefined || f.maxHhld !== undefined) count++;
  if (f.builtAfter !== undefined || f.builtBefore !== undefined) count++;
  return count;
}

export function useApartments() {
  const [apartments, setApartments] = useState<Apartment[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<ApartmentFilters>({});
  const boundsRef = useRef<MapBounds | undefined>(undefined);
  const keywordsRef = useRef<string[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchByKeywords = useCallback(async (keywords: string[]): Promise<Apartment[]> => {
    // 각 키워드별로 검색 후 합산 (중복 제거)
    const allResults: Apartment[] = [];
    const pnuSet = new Set<string>();
    for (const kw of keywords) {
      try {
        const res = await axios.get<Apartment[]>(`${API_BASE}/api/apartments/search`, { params: { q: kw } });
        for (const apt of res.data) {
          if (!pnuSet.has(apt.pnu)) {
            pnuSet.add(apt.pnu);
            allResults.push(apt);
          }
        }
      } catch (err) {
        console.error(`검색 실패 (${kw}):`, err);
      }
    }
    return allResults;
  }, []);

  const fetchApartments = useCallback(async (f: ApartmentFilters, bounds?: MapBounds, keywords?: string[]) => {
    try {
      setLoading(true);
      const kws = keywords ?? keywordsRef.current;

      if (kws.length > 0) {
        const results = await fetchByKeywords(kws);
        searchResultsRef.current = results;
        setApartments(results);
      } else {
        const params: Record<string, string> = {};
        const b = bounds || boundsRef.current;
        if (b) {
          params.sw_lat = String(b.sw.lat);
          params.sw_lng = String(b.sw.lng);
          params.ne_lat = String(b.ne.lat);
          params.ne_lng = String(b.ne.lng);
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
        const url = `${API_BASE}/api/apartments${query ? `?${query}` : ''}`;
        const res = await axios.get<Apartment[]>(url);
        setApartments(res.data);
      }
    } catch (err) {
      console.error('아파트 목록 불러오기 실패:', err);
    } finally {
      setLoading(false);
    }
  }, [fetchByKeywords]);

  // 검색 결과 캐시 (검색 후 지도 이동 시 합산용)
  const searchResultsRef = useRef<Apartment[]>([]);
  const isFirstBoundsRef = useRef(true);

  // 지도 영역 변경 시 호출 (첫 호출은 즉시, 이후 디바운스)
  const onBoundsChange = useCallback((bounds: MapBounds) => {
    boundsRef.current = bounds;
    const isFirst = isFirstBoundsRef.current;
    if (isFirst) isFirstBoundsRef.current = false;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    const delay = isFirst ? 0 : 300;
    debounceRef.current = setTimeout(async () => {
      try {
        setLoading(true);
        const params: Record<string, string> = {
          sw_lat: String(bounds.sw.lat), sw_lng: String(bounds.sw.lng),
          ne_lat: String(bounds.ne.lat), ne_lng: String(bounds.ne.lng),
        };
        // 현재 필터를 bounds 요청에 반영
        const f = filters;
        if (f.minArea !== undefined) params.min_area = String(f.minArea);
        if (f.maxArea !== undefined) params.max_area = String(f.maxArea);
        if (f.minPrice !== undefined) params.min_price = String(f.minPrice);
        if (f.maxPrice !== undefined) params.max_price = String(f.maxPrice);
        if (f.minFloor !== undefined) params.min_floor = String(f.minFloor);
        if (f.minHhld !== undefined) params.min_hhld = String(f.minHhld);
        if (f.maxHhld !== undefined) params.max_hhld = String(f.maxHhld);
        if (f.builtAfter !== undefined) params.built_after = String(f.builtAfter);
        if (f.builtBefore !== undefined) params.built_before = String(f.builtBefore);

        const query = new URLSearchParams(params).toString();
        const res = await axios.get<Apartment[]>(`${API_BASE}/api/apartments?${query}`);
        const boundsApts = res.data;

        if (searchResultsRef.current.length > 0) {
          // 검색 결과 + 현재 영역 합산 (중복 제거)
          const pnuSet = new Set(boundsApts.map(a => a.pnu));
          const merged = [...boundsApts, ...searchResultsRef.current.filter(a => !pnuSet.has(a.pnu))];
          setApartments(merged);
        } else {
          setApartments(boundsApts);
        }
      } catch (err) {
        console.error('아파트 목록 불러오기 실패:', err);
      } finally {
        setLoading(false);
      }
    }, delay);
  }, [filters]);

  // 키워드 추가
  const addKeyword = useCallback((kw: string) => {
    if (keywordsRef.current.includes(kw)) return;
    const next = [...keywordsRef.current, kw];
    keywordsRef.current = next;
    fetchApartments(filters, undefined, next);
  }, [filters, fetchApartments]);

  // 키워드 제거
  const removeKeyword = useCallback((kw: string) => {
    const next = keywordsRef.current.filter(k => k !== kw);
    keywordsRef.current = next;
    if (next.length === 0) {
      searchResultsRef.current = [];
      fetchApartments(filters, boundsRef.current, []);
    } else {
      fetchApartments(filters, undefined, next);
    }
  }, [filters, fetchApartments]);

  // 전체 키워드 클리어 (fetch 없이 state만 초기화, 다음 bounds 변경 시 자동 fetch)
  const clearKeywords = useCallback(() => {
    keywordsRef.current = [];
    searchResultsRef.current = [];
  }, []);

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

  return { apartments, loading, filters, applyFilters, clearFilters, onBoundsChange, addKeyword, removeKeyword, clearKeywords };
}
