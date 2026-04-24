/**
 * label/value 쌍 그리드 — null 항목 자동 제외, 전부 null 이면 null 반환.
 * Server/Client 경계 중립.
 */

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
