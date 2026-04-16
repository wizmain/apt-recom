import type { LogRange, RangePreset } from "../types/admin";

interface Props {
  value: LogRange;
  onChange: (next: LogRange) => void;
}

const PRESETS: { key: Exclude<RangePreset, "custom">; label: string; days: number }[] = [
  { key: "24h", label: "24시간", days: 1 },
  { key: "7d", label: "7일", days: 7 },
  { key: "30d", label: "30일", days: 30 },
  { key: "90d", label: "90일", days: 90 },
];

/**
 * 기간 필터 바 — 프리셋 4종 + 커스텀 날짜 범위.
 * URL 쿼리 파라미터 동기화는 상위 페이지에서 담당.
 */
export function RangeFilterBar({ value, onChange }: Props) {
  const selectPreset = (preset: RangePreset) => {
    if (preset === "custom") {
      // 커스텀 전환 시 현재 표시되고 있는 기간으로 초기화
      const now = new Date();
      const from = new Date(now.getTime() - 7 * 86400_000);
      onChange({
        preset: "custom",
        from: from.toISOString().slice(0, 10),
        to: now.toISOString().slice(0, 10),
      });
    } else {
      onChange({ preset });
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <div className="flex gap-1 bg-white rounded-lg p-1 border border-gray-200">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            onClick={() => selectPreset(p.key)}
            className={`px-3 py-1 rounded text-xs transition-colors ${
              value.preset === p.key
                ? "bg-blue-600 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {p.label}
          </button>
        ))}
        <button
          onClick={() => selectPreset("custom")}
          className={`px-3 py-1 rounded text-xs transition-colors ${
            value.preset === "custom"
              ? "bg-blue-600 text-white"
              : "text-gray-600 hover:bg-gray-100"
          }`}
        >
          커스텀
        </button>
      </div>

      {value.preset === "custom" && (
        <div className="flex items-center gap-1 text-xs text-gray-600">
          <input
            type="date"
            value={value.from ?? ""}
            onChange={(e) => onChange({ ...value, from: e.target.value })}
            className="px-2 py-1 border border-gray-200 rounded"
          />
          <span>~</span>
          <input
            type="date"
            value={value.to ?? ""}
            onChange={(e) => onChange({ ...value, to: e.target.value })}
            className="px-2 py-1 border border-gray-200 rounded"
          />
        </div>
      )}
    </div>
  );
}

/**
 * LogRange 를 백엔드 쿼리 파라미터로 변환.
 */
export function rangeToParams(range: LogRange): Record<string, string | number> {
  if (range.preset === "custom") {
    const params: Record<string, string> = {};
    if (range.from) params.date_from = range.from;
    if (range.to) params.date_to = range.to;
    return params;
  }
  const presetDays: Record<Exclude<RangePreset, "custom">, number> = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
  };
  return { days: presetDays[range.preset] };
}
