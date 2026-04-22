/**
 * 상세 페이지 섹션 공통 컴포넌트 — 모두 Server Component.
 *
 * `Section`: 제목 + 본문. 빈 본문이면 섹션 자체 렌더 생략(호출부 책임).
 * `DataList`: label/value 쌍 목록. null 항목 자동 제외, 전부 null 이면 null 반환.
 */

export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-base font-semibold text-gray-800">{title}</h2>
      {children}
    </section>
  );
}

export type DataItem = { label: string; value: string } | null | undefined;

export function DataList({ items }: { items: DataItem[] }) {
  const valid = items.filter((i): i is { label: string; value: string } => !!i);
  if (valid.length === 0) return null;
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border border-gray-200 bg-white p-4">
      {valid.map((it) => (
        <div key={it.label} className="text-sm">
          <dt className="text-gray-500">{it.label}</dt>
          <dd className="font-medium text-gray-900">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Empty({ text = "정보 없음" }: { text?: string }) {
  return <p className="text-sm text-gray-400">{text}</p>;
}

export function formatYyyymmdd(s: string | null | undefined): string | null {
  if (!s) return null;
  if (s.length === 8) return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`;
  return s;
}

export function formatPriceManwon(amount: number | null | undefined): string | null {
  if (amount == null) return null;
  if (amount >= 10000) {
    const ok = Math.floor(amount / 10000);
    const rest = amount % 10000;
    return rest > 0 ? `${ok}억 ${rest.toLocaleString()}만원` : `${ok}억원`;
  }
  return `${amount.toLocaleString()}만원`;
}

export function formatMeters(m: number | null | undefined): string | null {
  if (m == null) return null;
  if (m < 1000) return `${Math.round(m)}m`;
  return `${(m / 1000).toFixed(1)}km`;
}
