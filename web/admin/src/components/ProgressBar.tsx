interface ProgressBarProps {
  label: string;
  value: number; // 0~100
  rightLabel?: string;
}

export function ProgressBar({ label, value, rightLabel }: ProgressBarProps) {
  const color =
    value >= 95
      ? "bg-green-600"
      : value >= 85
        ? "bg-blue-600"
        : value >= 70
          ? "bg-amber-500"
          : "bg-red-500";

  const textColor =
    value >= 95
      ? "text-green-600"
      : value >= 85
        ? "text-blue-600"
        : value >= 70
          ? "text-amber-500"
          : "text-red-500";

  return (
    <div>
      <div className="flex justify-between text-[11px] mb-1">
        <span className="text-slate-600">{label}</span>
        <span className={`font-semibold ${textColor}`}>
          {rightLabel ?? `${value}%`}
        </span>
      </div>
      <div className="h-1.5 bg-gray-200 rounded-full">
        <div
          className={`h-full ${color} rounded-full transition-all duration-300`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  );
}
