import { useState, useCallback, useRef } from 'react';
import type { Apartment, MapBounds, SelectedRegion } from '../types/apartment';
import { api } from '../lib/api';

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

/** 필터 값을 URL 파라미터로 직렬화 (규칙 일원화) */
function filterParams(f: ApartmentFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (f.minArea !== undefined) params.min_area = String(f.minArea);
  if (f.maxArea !== undefined) params.max_area = String(f.maxArea);
  if (f.minPrice !== undefined) params.min_price = String(f.minPrice);
  if (f.maxPrice !== undefined) params.max_price = String(f.maxPrice);
  if (f.minFloor !== undefined) params.min_floor = String(f.minFloor);
  if (f.minHhld !== undefined) params.min_hhld = String(f.minHhld);
  if (f.maxHhld !== undefined) params.max_hhld = String(f.maxHhld);
  if (f.builtAfter !== undefined) params.built_after = String(f.builtAfter);
  if (f.builtBefore !== undefined) params.built_before = String(f.builtBefore);
  return params;
}

/** 지역 필터를 URL 파라미터로 직렬화 */
function regionParams(region: SelectedRegion | null): Record<string, string> {
  if (!region) return {};
  return region.type === 'emd'
    ? { bjd_code: region.code }
    : { sigungu_code: region.code };
}

export function useApartments() {
  const [apartments, setApartments] = useState<Apartment[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<ApartmentFilters>({});
  const [selectedRegion, setSelectedRegion] = useState<SelectedRegion | null>(null);
  // 지역 선택/변경으로 새 아파트 목록이 도착한 순간을 Map에 알리는 nonce
  const [regionFitNonce, setRegionFitNonce] = useState(0);
  const selectedRegionRef = useRef<SelectedRegion | null>(null);
  const boundsRef = useRef<MapBounds | undefined>(undefined);
  const keywordsRef = useRef<string[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const filtersRef = useRef<ApartmentFilters>({});
  // 단지명 검색 결과 캐시 (name 매칭 키워드 전용)
  const searchResultsRef = useRef<Apartment[]>([]);
  const isFirstBoundsRef = useRef(true);

  /** 단지명 키워드로 검색 (/apartments/search 사용) */
  const fetchByNameKeywords = useCallback(async (keywords: string[]): Promise<Apartment[]> => {
    const allResults: Apartment[] = [];
    const pnuSet = new Set<string>();
    for (const kw of keywords) {
      try {
        const res = await api.get<{ results: Apartment[] } | Apartment[]>(
          `/api/apartments/search`,
          { params: { q: kw } },
        );
        const list = Array.isArray(res.data) ? res.data : res.data.results || [];
        for (const apt of list) {
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

  /** /apartments 호출 (공통) */
  const fetchApartmentsRaw = useCallback(async (
    f: ApartmentFilters,
    region: SelectedRegion | null,
    bounds?: MapBounds,
  ): Promise<Apartment[]> => {
    const params: Record<string, string> = {
      ...filterParams(f),
      ...regionParams(region),
    };
    // 지역 필터가 있으면 bounds 무시 (서버도 동일 정책)
    if (!region && bounds) {
      params.sw_lat = String(bounds.sw.lat);
      params.sw_lng = String(bounds.sw.lng);
      params.ne_lat = String(bounds.ne.lat);
      params.ne_lng = String(bounds.ne.lng);
    }
    const query = new URLSearchParams(params).toString();
    const res = await api.get<Apartment[]>(
      `/api/apartments${query ? `?${query}` : ''}`,
    );
    return res.data;
  }, []);

  /** 현재 상태 기반 재조회 (지역/단지명/bounds 우선순위 반영) */
  const refetch = useCallback(async (
    f: ApartmentFilters,
    region: SelectedRegion | null,
    bounds: MapBounds | undefined,
    nameKeywords: string[],
  ) => {
    try {
      setLoading(true);
      // 1. 지역 필터가 있으면 최우선 (단지명 검색 결과는 병합)
      if (region) {
        const regionApts = await fetchApartmentsRaw(f, region);
        if (nameKeywords.length > 0 && searchResultsRef.current.length > 0) {
          const pnuSet = new Set(regionApts.map(a => a.pnu));
          const merged = [
            ...regionApts,
            ...searchResultsRef.current.filter(a => !pnuSet.has(a.pnu)),
          ];
          setApartments(merged);
        } else {
          setApartments(regionApts);
        }
        return regionApts;
      }
      // 2. 단지명 키워드 검색
      if (nameKeywords.length > 0) {
        const results = await fetchByNameKeywords(nameKeywords);
        searchResultsRef.current = results;
        setApartments(results);
        return;
      }
      // 3. bounds 기반 조회
      const boundsApts = await fetchApartmentsRaw(f, null, bounds);
      setApartments(boundsApts);
    } catch (err) {
      console.error('아파트 목록 불러오기 실패:', err);
    } finally {
      setLoading(false);
    }
  }, [fetchApartmentsRaw, fetchByNameKeywords]);

  /** 지도 영역 변경 시 호출 */
  const onBoundsChange = useCallback((bounds: MapBounds) => {
    boundsRef.current = bounds;
    const isFirst = isFirstBoundsRef.current;
    if (isFirst) isFirstBoundsRef.current = false;

    // 지역 필터가 있으면 bounds 변경 무시 (결과 고정)
    if (selectedRegionRef.current) return;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    const delay = isFirst ? 0 : 300;
    debounceRef.current = setTimeout(() => {
      refetch(filtersRef.current, null, bounds, keywordsRef.current);
    }, delay);
  }, [refetch]);

  /** 지역 필터 선택 */
  const selectRegion = useCallback(async (region: SelectedRegion) => {
    setSelectedRegion(region);
    selectedRegionRef.current = region;
    await refetch(filtersRef.current, region, boundsRef.current, keywordsRef.current);
    // apartments 업데이트 후 Map이 fitBounds 하도록 nonce 증가
    setRegionFitNonce(n => n + 1);
  }, [refetch]);

  /** 지역 필터 해제 */
  const clearRegion = useCallback(() => {
    setSelectedRegion(null);
    selectedRegionRef.current = null;
    refetch(filtersRef.current, null, boundsRef.current, keywordsRef.current);
  }, [refetch]);

  /** 단지명 키워드 추가 */
  const addKeyword = useCallback((kw: string) => {
    keywordsRef.current = [kw];
    searchResultsRef.current = [];
    refetch(filtersRef.current, selectedRegionRef.current, boundsRef.current, [kw]);
  }, [refetch]);

  /** 단지명 키워드 제거 */
  const removeKeyword = useCallback((kw: string) => {
    const next = keywordsRef.current.filter(k => k !== kw);
    keywordsRef.current = next;
    if (next.length === 0) searchResultsRef.current = [];
    refetch(filtersRef.current, selectedRegionRef.current, boundsRef.current, next);
  }, [refetch]);

  /** 전체 키워드 클리어 */
  const clearKeywords = useCallback(() => {
    keywordsRef.current = [];
    searchResultsRef.current = [];
  }, []);

  /** 필터 변경 */
  const applyFilters = useCallback((newFilters: ApartmentFilters) => {
    setFilters(newFilters);
    filtersRef.current = newFilters;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      refetch(newFilters, selectedRegionRef.current, boundsRef.current, keywordsRef.current);
      // 필터 변경 로깅 — debounce 300ms 끝에 1회, 빈 값은 제외. 실패는 흡수.
      const sanitized: Record<string, number> = {};
      for (const [k, v] of Object.entries(newFilters)) {
        if (typeof v === 'number' && !Number.isNaN(v)) sanitized[k] = v;
      }
      api.post('/api/log/event', {
        event_type: 'filter_change',
        event_name: null,
        payload: sanitized,
      }).catch(() => { /* ignore */ });
    }, 300);
  }, [refetch]);

  const clearFilters = useCallback(() => {
    setFilters({});
    filtersRef.current = {};
    refetch({}, selectedRegionRef.current, boundsRef.current, keywordsRef.current);
  }, [refetch]);

  return {
    apartments,
    loading,
    filters,
    selectedRegion,
    regionFitNonce,
    applyFilters,
    clearFilters,
    onBoundsChange,
    selectRegion,
    clearRegion,
    addKeyword,
    removeKeyword,
    clearKeywords,
  };
}
