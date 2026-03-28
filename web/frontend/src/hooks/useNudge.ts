import { useState, useCallback } from 'react';
import axios from 'axios';
import type { ScoredApartment, MapBounds } from '../types/apartment';
import type { ApartmentFilters } from './useApartments';
import { API_BASE } from '../config';

export function useNudge() {
  const [results, setResults] = useState<ScoredApartment[]>([]);
  const [loading, setLoading] = useState(false);
  const [defaultWeights, setDefaultWeights] = useState<Record<string, Record<string, number>>>({});

  const fetchWeights = useCallback(async () => {
    try {
      const res = await axios.get<Record<string, Record<string, number>>>(`${API_BASE}/api/nudge/weights`);
      setDefaultWeights(res.data);
      return res.data;
    } catch (err) {
      console.error('가중치 불러오기 실패:', err);
      return {};
    }
  }, []);

  const scoreApartments = useCallback(
    async (
      nudges: string[],
      weights: Record<string, Record<string, number>> | null,
      topN: number = 10,
      bounds?: MapBounds,
      keywords?: string[],
      filters?: ApartmentFilters,
    ) => {
      if (nudges.length === 0) {
        setResults([]);
        return;
      }
      try {
        setLoading(true);
        const body: Record<string, unknown> = {
          nudges,
          weights,
          top_n: topN,
        };
        if (bounds) {
          body.sw_lat = bounds.sw.lat;
          body.sw_lng = bounds.sw.lng;
          body.ne_lat = bounds.ne.lat;
          body.ne_lng = bounds.ne.lng;
        }
        if (keywords && keywords.length > 0) {
          body.keywords = keywords;
        }
        // Pass filters to nudge scoring
        if (filters) {
          if (filters.minArea) body.min_area = filters.minArea;
          if (filters.maxArea) body.max_area = filters.maxArea;
          if (filters.minPrice) body.min_price = filters.minPrice;
          if (filters.maxPrice) body.max_price = filters.maxPrice;
          if (filters.minFloor) body.min_floor = filters.minFloor;
          if (filters.minHhld) body.min_hhld = filters.minHhld;
          if (filters.maxHhld) body.max_hhld = filters.maxHhld;
          if (filters.builtAfter) body.built_after = filters.builtAfter;
          if (filters.builtBefore) body.built_before = filters.builtBefore;
        }
        const res = await axios.post<ScoredApartment[]>(`${API_BASE}/api/nudge/score`, body);
        setResults(res.data);
      } catch (err) {
        console.error('스코어링 실패:', err);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { results, loading, defaultWeights, scoreApartments, fetchWeights };
}
