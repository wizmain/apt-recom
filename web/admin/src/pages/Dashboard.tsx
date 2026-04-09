import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import { KpiCard } from "../components/KpiCard";
import { ProgressBar } from "../components/ProgressBar";
import { StatusBadge } from "../components/StatusBadge";
import type {
  DashboardSummary,
  DashboardQuality,
  BatchHistoryItem,
  FeedbackItem,
} from "../types/admin";

export function Dashboard() {
  const { token, clearToken } = useAuth();
  const { get } = useAdminApi({ token, onUnauthorized: clearToken });

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [quality, setQuality] = useState<DashboardQuality | null>(null);
  const [batchHistory, setBatchHistory] = useState<BatchHistoryItem[]>([]);
  const [recentFeedback, setRecentFeedback] = useState<FeedbackItem[]>([]);
  const [trendData, setTrendData] = useState<{ period: string; total: number }[]>([]);

  useEffect(() => {
    get<DashboardSummary>("/dashboard/summary").then((d) => d && setSummary(d));
    get<DashboardQuality>("/dashboard/quality").then((d) => d && setQuality(d));
    get<{ history: BatchHistoryItem[] }>("/batch/history").then(
      (d) => d && setBatchHistory(d.history.slice(0, 4)),
    );
    get<{ data: FeedbackItem[] }>("/feedback/list", {
      page: 1,
      page_size: 5,
    }).then((d) => d && setRecentFeedback(d.data));
    get<{ data: { period: string; total: number }[] }>("/feedback/trend", {
      period: "monthly",
    }).then((d) => d && setTrendData(d.data));
  }, [get]);

  const tradeChange =
    summary && summary.yesterday_trades > 0
      ? Math.round(
          ((summary.today_trades - summary.yesterday_trades) /
            summary.yesterday_trades) *
            100,
        )
      : 0;

  const satisfactionChange = summary
    ? +(summary.satisfaction_rate - summary.prev_satisfaction_rate).toFixed(1)
    : 0;

  return (
    <div>
      <div className="flex justify-between items-center mb-5">
        <div>
          <h1 className="text-lg font-bold text-slate-900">운영 대시보드</h1>
          <span className="text-[11px] text-gray-400">
            {new Date().toLocaleString("ko-KR")} 기준
          </span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <KpiCard
          title="총 아파트"
          value={summary?.total_apartments.toLocaleString() ?? "-"}
          icon="🏢"
          iconBg="bg-blue-50"
          change={
            summary
              ? `${summary.new_apartments_week > 0 ? "+" : ""}${summary.new_apartments_week} 이번 주 거래`
              : undefined
          }
          changeType={
            summary && summary.new_apartments_week > 0 ? "positive" : "neutral"
          }
        />
        <KpiCard
          title="오늘 거래"
          value={summary?.today_trades.toLocaleString() ?? "-"}
          icon="📈"
          iconBg="bg-blue-50"
          change={
            tradeChange !== 0
              ? `${tradeChange > 0 ? "+" : ""}${tradeChange}% vs 어제`
              : undefined
          }
          changeType={
            tradeChange > 0
              ? "positive"
              : tradeChange < 0
                ? "negative"
                : "neutral"
          }
        />
        <KpiCard
          title="챗봇 만족도"
          value={summary ? `${summary.satisfaction_rate}%` : "-"}
          icon="⭐"
          iconBg="bg-amber-50"
          change={
            satisfactionChange !== 0
              ? `${satisfactionChange > 0 ? "+" : ""}${satisfactionChange}% vs 지난주`
              : undefined
          }
          changeType={
            satisfactionChange > 0
              ? "positive"
              : satisfactionChange < 0
                ? "negative"
                : "neutral"
          }
        />
        <KpiCard
          title="주소 커버리지"
          value={summary ? `${summary.coverage_pct}%` : "-"}
          icon="📍"
          iconBg="bg-green-50"
          change={
            summary ? `${summary.uncovered_count}건 미보충` : undefined
          }
          changeType="neutral"
        />
      </div>

      {/* Row 2: Batch + Feedback */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
        {/* Batch Status */}
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">
            배치 실행 현황
          </h2>
          {batchHistory.length === 0 ? (
            <p className="text-xs text-gray-400">
              배치 이력이 없거나 로컬 환경이 아닙니다.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {batchHistory.map((b) => (
                <div
                  key={b.filename}
                  className="flex justify-between items-center px-3 py-2 bg-gray-50 rounded-md text-xs"
                >
                  <div className="flex items-center gap-2">
                    <StatusBadge status={b.status} />
                    <span className="font-semibold">
                      {b.batch_type ?? "unknown"}
                    </span>
                  </div>
                  <span className="text-gray-500">
                    {b.started_at ?? "-"} · {b.total_records}건
                    {b.duration ? ` · ${b.duration}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Feedback */}
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">
            최근 피드백
          </h2>
          {recentFeedback.length === 0 ? (
            <p className="text-xs text-gray-400">피드백이 없습니다.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {recentFeedback.map((fb) => (
                <div
                  key={fb.id}
                  className={`flex gap-2 items-start px-3 py-2 rounded-md text-xs ${fb.rating === 1 ? "bg-gray-50" : "bg-red-50"}`}
                >
                  <span className="text-sm flex-shrink-0">
                    {fb.rating === 1 ? "👍" : "👎"}
                  </span>
                  <div className="min-w-0">
                    <div className="text-slate-700 line-clamp-1">
                      {fb.user_message}
                    </div>
                    <span className="text-gray-400 text-[10px]">
                      {fb.created_at
                        ? new Date(fb.created_at).toLocaleString("ko-KR")
                        : ""}
                      {fb.tags.length > 0 && (
                        <span className="text-red-500 ml-1">
                          {fb.tags.join(", ")}
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Row 3: Quality + Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        {/* Data Quality */}
        <div className="lg:col-span-2 bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">
            데이터 품질
          </h2>
          <div className="flex flex-col gap-2.5">
            {quality?.quality.map((q) => (
              <ProgressBar
                key={q.table}
                label={q.label}
                value={q.coverage_pct}
                rightLabel={`${q.total_records.toLocaleString()} (${q.coverage_pct}%)`}
              />
            ))}
          </div>
        </div>

        {/* Feedback Trend Chart */}
        <div className="lg:col-span-3 bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">
            피드백 추이 (월별)
          </h2>
          {trendData.length === 0 ? (
            <p className="text-xs text-gray-400">데이터 없음</p>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={trendData}>
                <XAxis
                  dataKey="period"
                  tickFormatter={(v: string) => {
                    const d = new Date(v);
                    return `${d.getMonth() + 1}월`;
                  }}
                  tick={{ fontSize: 10 }}
                />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(v) => [`${v}건`, "피드백"]}
                  labelFormatter={(v) => {
                    const d = new Date(String(v));
                    return `${d.getFullYear()}.${d.getMonth() + 1}월`;
                  }}
                />
                <Bar dataKey="total" fill="#93c5fd" radius={[3, 3, 0, 0]} />
                <Bar dataKey="likes" fill="#2563eb" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
