import { useState, useEffect } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';

interface CodeItem {
  code: string;
  name: string;
  extra: string;
  sort_order: number;
}

type CodeMap = Record<string, string>;

// 모듈 레벨 캐시 (앱 생명주기 동안 1회 로드)
const cache: Record<string, CodeItem[]> = {};

async function fetchCodes(group: string): Promise<CodeItem[]> {
  if (cache[group]) return cache[group];
  const res = await axios.get<CodeItem[]>(`${API_BASE}/api/codes/${group}`);
  cache[group] = res.data;
  return res.data;
}

export function useCodes(group: string): { codes: CodeItem[]; codeMap: CodeMap; loading: boolean } {
  const [codes, setCodes] = useState<CodeItem[]>(cache[group] || []);
  const [loading, setLoading] = useState(!cache[group]);

  useEffect(() => {
    if (cache[group]) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- cache hit, no re-render loop
      setCodes(cache[group]);
      setLoading(false);
      return;
    }
    fetchCodes(group).then(data => {
      setCodes(data);
      setLoading(false);
    });
  }, [group]);

  const codeMap: CodeMap = {};
  for (const c of codes) {
    codeMap[c.code] = c.name;
  }

  return { codes, codeMap, loading };
}

export function useMultipleCodes(...groups: string[]): { data: Record<string, CodeItem[]>; maps: Record<string, CodeMap>; loading: boolean } {
  const [data, setData] = useState<Record<string, CodeItem[]>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all(groups.map(g => fetchCodes(g))).then(results => {
      const d: Record<string, CodeItem[]> = {};
      groups.forEach((g, i) => { d[g] = results[i]; });
      setData(d);
      setLoading(false);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups.join(',')]);

  const maps: Record<string, CodeMap> = {};
  for (const g of groups) {
    maps[g] = {};
    for (const c of (data[g] || [])) {
      maps[g][c.code] = c.name;
    }
  }

  return { data, maps, loading };
}
