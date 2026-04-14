import { useState, useEffect, useRef, type ReactNode } from 'react';

/**
 * Recharts ResponsiveContainer가 부모 크기 측정 실패 시 (width=-1, height=-1)
 * dev 콘솔에 경고를 출력하는 문제를 피하기 위한 래퍼.
 *
 * 동작: ResizeObserver로 자기 자신의 크기를 관찰하다가
 * 실제 width·height가 모두 0 초과인 상태가 되면 비로소 children을 렌더.
 * 모달/탭 CSS 애니메이션이 끝난 뒤에도 안정적으로 동작.
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
