import { useEffect, useState, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import type { FeedbackItem, FeedbackTrendItem } from "../types/admin";

const PIE_COLORS = ["#ef4444", "#f97316", "#eab308", "#3b82f6", "#8b5cf6", "#6b7280"];

export function Feedback() {
  const { token, clearToken } = useAuth();
  const { get, loading } = useAdminApi({ token, onUnauthorized: clearToken });

  const [feedbacks, setFeedbacks] = useState<FeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [ratingFilter, setRatingFilter] = useState<number | null>(null);
  const [trend, setTrend] = useState<FeedbackTrendItem[]>([]);
  const [tagStats, setTagStats] = useState<{ name: string; value: number }[]>([]);

  const fetchFeedbacks = useCallback(() => {
    const params: Record<string, unknown> = { page, page_size: 10 };
    if (ratingFilter !== null) params.rating = ratingFilter;
    get<{
      data: FeedbackItem[];
      total: number;
      total_pages: number;
    }>("/feedback/list", params).then((d) => {
      if (d) {
        setFeedbacks(d.data);
        setTotal(d.total);
        setTotalPages(d.total_pages);
      }
    });
  }, [get, page, ratingFilter]);

  useEffect(() => {
    fetchFeedbacks();
  }, [fetchFeedbacks]);

  useEffect(() => {
    get<{ data: FeedbackTrendItem[] }>("/feedback/trend", {
      period: "weekly",
    }).then((d) => d && setTrend(d.data));

    // Tag stats from public API
    fetch(`/api/chat/feedback/stats`)
      .then((r) => r.json())
      .then((d) => {
        const tags = d.dislike_tags || {};
        setTagStats(
          Object.entries(tags).map(([name, value]) => ({
            name,
            value: value as number,
          })),
        );
      })
      .catch(() => {});
  }, [get]);

  return (
    <div>
      <h1 className="text-lg font-bold text-slate-900 mb-4">사용자 피드백</h1>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-4">
        {/* Trend */}
        <div className="lg:col-span-2 bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">
            만족도 추이 (주별)
          </h2>
          {trend.length === 0 ? (
            <p className="text-xs text-gray-400">데이터 없음</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={trend}>
                <XAxis
                  dataKey="period"
                  tickFormatter={(v: string) => {
                    const d = new Date(v);
                    return `${d.getMonth() + 1}/${d.getDate()}`;
                  }}
                  tick={{ fontSize: 10 }}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  formatter={(v) => [`${v}%`, "만족도"]}
                />
                <Line
                  type="monotone"
                  dataKey="satisfaction_rate"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Tag distribution */}
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-3">
            불만 태그 분포
          </h2>
          {tagStats.length === 0 ? (
            <p className="text-xs text-gray-400">데이터 없음</p>
          ) : (
            <div>
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie
                    data={tagStats}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={55}
                    innerRadius={30}
                  >
                    {tagStats.map((_, i) => (
                      <Cell
                        key={i}
                        fill={PIE_COLORS[i % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[10px]">
                {tagStats.map((t, i) => (
                  <span key={t.name} className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full inline-block"
                      style={{
                        background: PIE_COLORS[i % PIE_COLORS.length],
                      }}
                    />
                    {t.name} ({t.value})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Filter + List */}
      <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs text-gray-500">필터:</span>
          {[
            { label: "전체", value: null },
            { label: "👍 좋아요", value: 1 },
            { label: "👎 싫어요", value: -1 },
          ].map((f) => (
            <button
              key={String(f.value)}
              onClick={() => {
                setRatingFilter(f.value);
                setPage(1);
              }}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors ${
                ratingFilter === f.value
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
              }`}
            >
              {f.label}
            </button>
          ))}
          <span className="text-[11px] text-gray-400 ml-auto">
            총 {total}건
          </span>
        </div>

        {/* List */}
        <div className="flex flex-col gap-1.5">
          {loading ? (
            <p className="text-xs text-gray-400 py-4 text-center">로딩 중...</p>
          ) : feedbacks.length === 0 ? (
            <p className="text-xs text-gray-400 py-4 text-center">피드백 없음</p>
          ) : (
            feedbacks.map((fb) => (
              <div
                key={fb.id}
                className={`px-3 py-2.5 rounded-lg text-xs ${fb.rating === 1 ? "bg-gray-50" : "bg-red-50"}`}
              >
                <div className="flex items-start gap-2">
                  <span className="text-sm flex-shrink-0">
                    {fb.rating === 1 ? "👍" : "👎"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-slate-700 mb-0.5">
                      <span className="font-medium">Q:</span> {fb.user_message}
                    </div>
                    <div className="text-gray-500 line-clamp-2">
                      <span className="font-medium">A:</span>{" "}
                      {fb.assistant_message}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
                      {fb.created_at && (
                        <span>
                          {new Date(fb.created_at).toLocaleString("ko-KR")}
                        </span>
                      )}
                      {fb.tags.length > 0 && (
                        <span className="text-red-500">
                          {fb.tags.join(", ")}
                        </span>
                      )}
                      {fb.comment && (
                        <span className="text-blue-500">
                          "{fb.comment}"
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center gap-1 mt-3">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-2 py-1 rounded border border-gray-200 text-xs disabled:opacity-30 hover:bg-gray-100"
            >
              이전
            </button>
            <span className="px-3 py-1 text-xs text-gray-500">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-2 py-1 rounded border border-gray-200 text-xs disabled:opacity-30 hover:bg-gray-100"
            >
              다음
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
