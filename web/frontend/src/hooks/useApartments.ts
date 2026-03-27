import { useState, useEffect } from 'react';
import axios from 'axios';
import type { Apartment } from '../types/apartment';

export function useApartments() {
  const [apartments, setApartments] = useState<Apartment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchApartments = async () => {
      try {
        setLoading(true);
        const res = await axios.get<Apartment[]>('/api/apartments');
        setApartments(res.data);
      } catch (err) {
        console.error('아파트 목록 불러오기 실패:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchApartments();
  }, []);

  return { apartments, loading };
}
