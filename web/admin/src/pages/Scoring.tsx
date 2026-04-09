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
import type { ScoringWeights, ScoringDistribution } from "../types/admin";

const NUDGE_LABELS: Record<string, string> = {
  cost: "생활비",
  pet: "반려동물",
  commute: "출퇴근",
  newlywed: "신혼부부",
  education: "교육",
  senior: "시니어",
  investment: "투자",
  nature: "자연/공원",
  safety: "안전",
};

export function Scoring() {
  const { token, clearToken } = useAuth();
  const { get, request } = useAdminApi({ token, onUnauthorized: clearToken });

  const [weights, setWeights] = useState<ScoringWeights | null>(null);
  const [selectedNudge, setSelectedNudge] = useState("cost");
  const [distribution, setDistribution] = useState<ScoringDistribution | null>(null);
  const [editing, setEditing] = useState(false);
  const [editWeights, setEditWeights] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);

  const fetchWeights = () => {
    get<ScoringWeights>("/scoring/weights").then((d) => d && setWeights(d));
  };

  useEffect(() => {
    fetchWeights();
  }, [get]);

  useEffect(() => {
    get<ScoringDistribution>("/scoring/distribution", {
      nudge_id: selectedNudge,
    }).then((d) => d && setDistribution(d));
  }, [get, selectedNudge]);

  const nudgeIds = weights ? Object.keys(weights.nudge_weights) : [];

  return (
    <div>
      <h1 className="text-lg font-bold text-slate-900 mb-4">
        스코어링 / 가중치 관리
      </h1>

      {/* Nudge tabs */}
      <div className="flex flex-wrap gap-2 mb-4">
        {nudgeIds.map((id) => (
          <button
            key={id}
            onClick={() => setSelectedNudge(id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              selectedNudge === id
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
            }`}
          >
            {NUDGE_LABELS[id] ?? id}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Weights table */}
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-[13px] font-semibold text-slate-900">
              {NUDGE_LABELS[selectedNudge] ?? selectedNudge} 가중치
            </h2>
            {!editing ? (
              <button
                onClick={() => {
                  if (weights?.nudge_weights[selectedNudge]) {
                    setEditWeights({ ...weights.nudge_weights[selectedNudge] });
                    setEditing(true);
                  }
                }}
                className="px-2.5 py-1 rounded-lg text-[11px] text-blue-600 border border-blue-200 hover:bg-blue-50"
              >
                수정
              </button>
            ) : (
              <div className="flex gap-1">
                <button
                  onClick={async () => {
                    setSaving(true);
                    await request("put", "/scoring/weights", {
                      nudge_id: selectedNudge,
                      weights: editWeights,
                    });
                    setSaving(false);
                    setEditing(false);
                    fetchWeights();
                  }}
                  disabled={saving}
                  className="px-2.5 py-1 rounded-lg text-[11px] text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "저장 중..." : "저장"}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="px-2.5 py-1 rounded-lg text-[11px] text-gray-500 border border-gray-200 hover:bg-gray-50"
                >
                  취소
                </button>
              </div>
            )}
          </div>
          {weights && weights.nudge_weights[selectedNudge] ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">
                      시설 유형
                    </th>
                    <th className="px-3 py-2 text-right font-semibold text-gray-600">
                      가중치
                    </th>
                    <th className="px-3 py-2 text-right font-semibold text-gray-600">
                      최대거리(m)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(weights.nudge_weights[selectedNudge])
                    .sort(([, a], [, b]) => b - a)
                    .map(([subtype, weight]) => (
                      <tr
                        key={subtype}
                        className="border-b border-gray-100 hover:bg-gray-50"
                      >
                        <td className="px-3 py-2 text-gray-700">{subtype}</td>
                        <td className="px-3 py-2 text-right font-mono text-blue-600">
                          {editing ? (
                            <input
                              type="number"
                              step="0.001"
                              value={editWeights[subtype] ?? weight}
                              onChange={(e) =>
                                setEditWeights({
                                  ...editWeights,
                                  [subtype]: parseFloat(e.target.value) || 0,
                                })
                              }
                              className="w-20 px-1.5 py-0.5 border border-blue-300 rounded text-right text-xs"
                            />
                          ) : (
                            weight.toFixed(3)
                          )}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-gray-500">
                          {weights.max_distances[subtype]
                            ? `${weights.max_distances[subtype].toLocaleString()}m`
                            : "-"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-gray-400">데이터 없음</p>
          )}
        </div>

        {/* Distribution chart */}
        <div className="bg-white rounded-[10px] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[13px] font-semibold text-slate-900 mb-1">
            거리 분포 히스토그램
          </h2>
          {distribution && (
            <p className="text-[10px] text-gray-400 mb-3">
              주요 시설: {distribution.primary_subtype} · 중앙값:{" "}
              {distribution.stats.median_distance_m}m · 평균:{" "}
              {distribution.stats.avg_distance_m}m
            </p>
          )}
          {distribution && distribution.histogram.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={distribution.histogram}>
                <XAxis
                  dataKey="avg_distance_m"
                  tickFormatter={(v: number) =>
                    v >= 1000 ? `${(v / 1000).toFixed(1)}km` : `${Math.round(v)}m`
                  }
                  tick={{ fontSize: 9 }}
                />
                <YAxis tick={{ fontSize: 9 }} />
                <Tooltip
                  formatter={(v) => [`${Number(v).toLocaleString()}개`, "아파트"]}
                  labelFormatter={(v) => `~${Math.round(Number(v))}m`}
                />
                <Bar
                  dataKey="count"
                  fill="#93c5fd"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-gray-400">데이터 없음</p>
          )}

          {/* Stats summary */}
          {distribution && (
            <div className="grid grid-cols-4 gap-2 mt-3">
              {[
                { label: "총 아파트", value: distribution.stats.total.toLocaleString() },
                { label: "최소", value: `${distribution.stats.min_distance_m}m` },
                { label: "중앙값", value: `${distribution.stats.median_distance_m}m` },
                { label: "최대", value: `${distribution.stats.max_distance_m}m` },
              ].map((s) => (
                <div key={s.label} className="text-center">
                  <div className="text-[10px] text-gray-400">{s.label}</div>
                  <div className="text-xs font-semibold text-slate-700">
                    {s.value}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
