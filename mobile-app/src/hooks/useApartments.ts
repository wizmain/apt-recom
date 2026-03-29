import { useState, useCallback, useRef } from 'react';
import type { Apartment, MapBounds, ApartmentFilters } from '../types/apartment';
import { api } from '../services/api';

export function useApartments() {
  const [apartments, setApartments] = useState<Apartment[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<ApartmentFilters>({});
  const [keywords, setKeywords] = useState<string[]>([]);
  const boundsRef = useRef<MapBounds | undefined>(undefined);
  const searchResultsRef = useRef<Apartment[]>([]);

  const fetchByKeywords = useCallback(async (kws: string[]): Promise<Apartment[]> => {
    const allResults: Apartment[] = [];
    const pnuSet = new Set<string>();
    for (const kw of kws) {
      try {
        const res = await api.get<Apartment[]>('/api/apartments/search', { params: { q: kw } });
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

  const fetchApartments = useCallback(async (f: ApartmentFilters, bounds?: MapBounds, kws?: string[]) => {
    try {
      setLoading(true);
      const currentKws = kws ?? keywords;

      if (currentKws.length > 0) {
        const results = await fetchByKeywords(currentKws);
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
        const res = await api.get<Apartment[]>(`/api/apartments${query ? `?${query}` : ''}`);
        setApartments(res.data);
      }
    } catch (err) {
      console.error('아파트 목록 불러오기 실패:', err);
    } finally {
      setLoading(false);
    }
  }, [keywords, fetchByKeywords]);

  const addKeyword = useCallback((kw: string) => {
    setKeywords(prev => {
      if (prev.includes(kw)) return prev;
      const next = [...prev, kw];
      fetchApartments(filters, undefined, next);
      return next;
    });
  }, [filters, fetchApartments]);

  const removeKeyword = useCallback((kw: string) => {
    setKeywords(prev => {
      const next = prev.filter(k => k !== kw);
      if (next.length === 0) {
        searchResultsRef.current = [];
        fetchApartments(filters, boundsRef.current, []);
      } else {
        fetchApartments(filters, undefined, next);
      }
      return next;
    });
  }, [filters, fetchApartments]);

  const clearKeywords = useCallback(() => {
    setKeywords([]);
    searchResultsRef.current = [];
    fetchApartments(filters, boundsRef.current, []);
  }, [filters, fetchApartments]);

  const applyFilters = useCallback((newFilters: ApartmentFilters) => {
    setFilters(newFilters);
    fetchApartments(newFilters);
  }, [fetchApartments]);

  const clearFilters = useCallback(() => {
    setFilters({});
    fetchApartments({});
  }, [fetchApartments]);

  const onBoundsChange = useCallback((bounds: MapBounds) => {
    boundsRef.current = bounds;
  }, []);

  return {
    apartments, loading, filters, keywords,
    applyFilters, clearFilters, onBoundsChange,
    addKeyword, removeKeyword, clearKeywords,
  };
}
