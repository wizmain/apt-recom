interface KpiCardProps {
  title: string;
  value: string | number;
  icon: string;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  iconBg?: string;
}

export function KpiCard({
  title,
  value,
  icon,
  change,
  changeType = "neutral",
  iconBg = "bg-blue-50",
}: KpiCardProps) {
  const changeColor =
    changeType === "positive"
      ? "text-green-600"
      : changeType === "negative"
        ? "text-red-600"
        : "text-gray-500";

  return (
    <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
      <div className="flex justify-between items-start">
        <div>
          <div className="text-[11px] text-gray-400 font-medium mb-1">
            {title}
          </div>
          <div className="text-2xl font-extrabold text-slate-900">{value}</div>
        </div>
        <div
          className={`w-8 h-8 ${iconBg} rounded-lg flex items-center justify-center text-sm`}
        >
          {icon}
        </div>
      </div>
      {change && (
        <div className={`text-[11px] mt-1.5 ${changeColor}`}>{change}</div>
      )}
    </div>
  );
}
