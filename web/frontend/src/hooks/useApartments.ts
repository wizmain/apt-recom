import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import type { Apartment } from '../types/apartment';
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
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<ApartmentFilters>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchApartments = useCallback(async (f: ApartmentFilters) => {
    try {
      setLoading(true);
      const params: Record<string, string> = {};
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
    } catch (err) {
      console.error('아파트 목록 불러오기 실패:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchApartments({});
  }, [fetchApartments]);

  // Filter change with debounce
  const applyFilters = useCallback((newFilters: ApartmentFilters) => {
    setFilters(newFilters);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchApartments(newFilters);
    }, 500);
  }, [fetchApartments]);

  const clearFilters = useCallback(() => {
    setFilters({});
    fetchApartments({});
  }, [fetchApartments]);

  return { apartments, loading, filters, applyFilters, clearFilters };
}
