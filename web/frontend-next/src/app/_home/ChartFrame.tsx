"use client";

import { useState, useEffect, useRef, type ReactNode } from 'react';

/**
 * Recharts ResponsiveContainer가 부모 크기 측정 실패 시 (width=-1, height=-1)
 * dev 콘솔에 경고를 출력하는 문제를 피하기 위한 래퍼.
 */
export default function ChartFrame({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        setReady(true);
        return true;
      }
      return false;
    };
    if (check()) return;
    const obs = new ResizeObserver(() => { if (check()) obs.disconnect(); });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={ref} className={className}>
      {ready ? children : null}
    </div>
  );
}
