type Status = "success" | "warning" | "error" | "unknown";

interface StatusBadgeProps {
  status: Status;
  label?: string;
}

const STYLES: Record<Status, { bg: string; dot: string; text: string; defaultLabel: string }> = {
  success: { bg: "bg-green-50", dot: "bg-green-600", text: "text-green-800", defaultLabel: "성공" },
  warning: { bg: "bg-amber-50", dot: "bg-amber-500", text: "text-amber-800", defaultLabel: "경고" },
  error: { bg: "bg-red-50", dot: "bg-red-600", text: "text-red-800", defaultLabel: "실패" },
  unknown: { bg: "bg-gray-50", dot: "bg-gray-400", text: "text-gray-600", defaultLabel: "알 수 없음" },
};

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const s = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${s.bg} ${s.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {label ?? s.defaultLabel}
    </span>
  );
}
