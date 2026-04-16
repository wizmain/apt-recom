import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { ChatDetailModal } from "../components/ChatDetailModal";
import { DataTable } from "../components/DataTable";
import { KpiCard } from "../components/KpiCard";
import { RangeFilterBar, rangeToParams } from "../components/RangeFilterBar";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import type {
  ChatLogDetail,
  ChatLogRow,
  EventLogRow,
  LogOverview,
  LogPaginatedResponse,
  LogRange,
  LogTimelineResponse,
  RangePreset,
} from "../types/admin";

type TabKey = "overview" | "events" | "chats";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "개요" },
  { key: "events", label: "이벤트 로그" },
  { key: "chats", label: "채팅 로그" },
];

const EVENT_TYPE_OPTIONS = [
  "",
  "page_view",
  "search",
  "filter_change",
  "nudge_score",
  "detail_view",
];

const PAGE_SIZE = 20;

function parseRangeFromParams(p: URLSearchParams): LogRange {
  const preset = (p.get("preset") || "7d") as RangePreset;
  if (preset === "custom") {
    return {
      preset,
      from: p.get("from") || undefined,
      to: p.get("to") || undefined,
    };
  }
  return { preset };
}

function shortDevice(id: string | null): string {
  if (!id) return "-";
  return id.slice(0, 8);
}

function formatTime(ts: string | null): string {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Logs() {
  const { token, clearToken } = useAuth();
  const { get, loading } = useAdminApi({ token, onUnauthorized: clearToken });

  const [searchParams, setSearchParams] = useSearchParams();
  const tab = (searchParams.get("tab") as TabKey) || "overview";
  const range = useMemo(() => parseRangeFromParams(searchParams), [searchParams]);
  const eventTypeFilter = searchParams.get("type") || "";
  const deviceFilter = searchParams.get("device") || "";
  const terminatedOnly = searchParams.get("terminated") === "1";
  const page = Number(searchParams.get("page") || "1");

  // 데이터 state
  const [overview, setOverview] = useState<LogOverview | null>(null);
  const [timeline, setTimeline] = useState<LogTimelineResponse | null>(null);
  const [events, setEvents] = useState<LogPaginatedResponse<EventLogRow> | null>(null);
  const [chats, setChats] = useState<LogPaginatedResponse<ChatLogRow> | null>(null);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [chatDetail, setChatDetail] = useState<ChatLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const rangeParams = useMemo(() => rangeToParams(range), [range]);

  // URL 업데이트 헬퍼 — 기존 파라미터 유지하며 부분 갱신
  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams);
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const changeTab = (t: TabKey) => updateParams({ tab: t, page: "1" });

  const changeRange = (r: LogRange) => {
    updateParams({
      preset: r.preset,
      from: r.preset === "custom" ? r.from || null : null,
      to: r.preset === "custom" ? r.to || null : null,
      page: "1",
    });
  };

  // ── overview + timeline ──
  useEffect(() => {
    if (tab !== "overview") return;
    get<LogOverview>("/log-analytics/overview", rangeParams).then((d) => {
      if (d) setOverview(d);
    });
    get<LogTimelineResponse>("/log-analytics/timeline", {
      ...rangeParams,
      granularity: "day",
    }).then((d) => {
      if (d) setTimeline(d);
    });
  }, [tab, rangeParams, get]);

  // ── events ──
  useEffect(() => {
    if (tab !== "events") return;
    const params: Record<string, unknown> = {
      ...rangeParams,
      page,
      page_size: PAGE_SIZE,
    };
    if (deviceFilter) params.device_id = deviceFilter;
    if (eventTypeFilter) params.event_type = eventTypeFilter;
    get<LogPaginatedResponse<EventLogRow>>("/log-analytics/events", params).then(
      (d) => d && setEvents(d),
    );
  }, [tab, rangeParams, page, deviceFilter, eventTypeFilter, get]);

  // ── chats ──
  useEffect(() => {
    if (tab !== "chats") return;
    const params: Record<string, unknown> = {
      ...rangeParams,
      page,
      page_size: PAGE_SIZE,
    };
    if (deviceFilter) params.device_id = deviceFilter;
    if (terminatedOnly) params.terminated_only = true;
    get<LogPaginatedResponse<ChatLogRow>>("/log-analytics/chats", params).then(
      (d) => d && setChats(d),
    );
  }, [tab, rangeParams, page, deviceFilter, terminatedOnly, get]);

  // ── chat detail modal 열기: effect 대신 이벤트 핸들러에서 setState ──
  const openChatDetail = useCallback(
    async (id: number) => {
      setSelectedChatId(id);
      setDetailLoading(true);
      setChatDetail(null);
      const d = await get<ChatLogDetail>(`/log-analytics/chats/${id}`);
      setChatDetail(d);
      setDetailLoading(false);
    },
    [get],
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-extrabold text-slate-900">로그 분석</h1>
        <div className="text-xs text-gray-400">
          익명 device_id 기반 · 90일 보관
        </div>
      </div>

      <RangeFilterBar value={range} onChange={changeRange} />

      {/* 탭 */}
      <div className="flex gap-1 mb-4 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => changeTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <OverviewTab overview={overview} timeline={timeline} loading={loading} />
      )}

      {tab === "events" && (
        <EventsTab
          data={events}
          loading={loading}
          deviceFilter={deviceFilter}
          eventTypeFilter={eventTypeFilter}
          page={page}
          onDeviceChange={(v) => updateParams({ device: v || null, page: "1" })}
          onEventTypeChange={(v) => updateParams({ type: v || null, page: "1" })}
          onPageChange={(p) => updateParams({ page: String(p) })}
        />
      )}

      {tab === "chats" && (
        <ChatsTab
          data={chats}
          loading={loading}
          deviceFilter={deviceFilter}
          terminatedOnly={terminatedOnly}
          page={page}
          onDeviceChange={(v) => updateParams({ device: v || null, page: "1" })}
          onTerminatedChange={(v) =>
            updateParams({ terminated: v ? "1" : null, page: "1" })
          }
          onPageChange={(p) => updateParams({ page: String(p) })}
          onRowClick={(row) => openChatDetail(row.id)}
        />
      )}

      {selectedChatId !== null && (
        <ChatDetailModal
          detail={chatDetail}
          loading={detailLoading}
          onClose={() => {
            setSelectedChatId(null);
            setChatDetail(null);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Overview tab
// ─────────────────────────────────────────────────────────────

function OverviewTab({
  overview,
  timeline,
  loading,
}: {
  overview: LogOverview | null;
  timeline: LogTimelineResponse | null;
  loading: boolean;
}) {
  if (loading && !overview) {
    return <div className="text-sm text-gray-400 py-10 text-center">로딩 중...</div>;
  }
  if (!overview) {
    return <div className="text-sm text-gray-400 py-10 text-center">데이터 없음</div>;
  }

  const terminatedPct = Math.round(overview.terminated_rate * 1000) / 10;

  return (
    <div className="space-y-4">
      {/* KPI 5개 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard title="DAU" value={overview.dau.toLocaleString()} icon="👤" />
        <KpiCard
          title="7일 활성 디바이스"
          value={overview.wau_devices.toLocaleString()}
          icon="📱"
          iconBg="bg-indigo-50"
        />
        <KpiCard
          title="총 이벤트"
          value={overview.total_events.toLocaleString()}
          icon="📊"
          iconBg="bg-emerald-50"
        />
        <KpiCard
          title="채팅 세션"
          value={overview.chat_sessions.toLocaleString()}
          icon="💬"
          iconBg="bg-amber-50"
        />
        <KpiCard
          title="채팅 중단율"
          value={`${terminatedPct}%`}
          icon="⚠"
          iconBg={terminatedPct > 20 ? "bg-red-50" : "bg-gray-50"}
          changeType={terminatedPct > 20 ? "negative" : "neutral"}
          change={`${overview.chat_sessions}건 중`}
        />
      </div>

      {/* 미니 리스트 3개 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <MiniListCard
          title="상위 검색어 Top 3"
          items={overview.top_keywords.map((k) => ({
            label: k.keyword,
            count: k.count,
          }))}
        />
        <MiniListCard
          title="인기 넛지 조합 Top 3"
          items={overview.top_nudge_combos.map((n) => ({
            label: n.combo.join(" + "),
            count: n.count,
          }))}
        />
        <MiniListCard
          title="상세조회 Top 5 아파트"
          items={overview.top_apt_details.map((a) => ({
            label: a.bld_nm || a.pnu,
            count: a.count,
          }))}
        />
      </div>

      {/* 타임라인 차트 */}
      <div className="bg-white rounded-lg p-4 shadow-sm">
        <div className="text-sm font-semibold text-gray-700 mb-2">일별 추이</div>
        {timeline && timeline.points.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={timeline.points}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="ts"
                tickFormatter={(v) =>
                  new Date(v).toLocaleDateString("ko-KR", {
                    month: "2-digit",
                    day: "2-digit",
                  })
                }
                tick={{ fontSize: 11 }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(v) => new Date(v as string).toLocaleDateString("ko-KR")}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="events"
                stroke="#3b82f6"
                name="이벤트"
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="unique_devices"
                stroke="#10b981"
                name="고유 디바이스"
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="chats"
                stroke="#f59e0b"
                name="채팅"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-xs text-gray-400 py-10 text-center">데이터 없음</div>
        )}
      </div>
    </div>
  );
}

function MiniListCard({
  title,
  items,
}: {
  title: string;
  items: { label: string; count: number }[];
}) {
  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <div className="text-xs text-gray-400 font-medium mb-2">{title}</div>
      {items.length === 0 ? (
        <div className="text-xs text-gray-300 py-4 text-center">없음</div>
      ) : (
        <ol className="space-y-1">
          {items.map((it, i) => (
            <li
              key={`${it.label}-${i}`}
              className="flex items-center justify-between text-xs"
            >
              <span className="text-gray-700 flex-1 truncate pr-2">
                <span className="text-gray-400 mr-1">{i + 1}.</span>
                {it.label}
              </span>
              <span className="text-blue-600 font-semibold tabular-nums">
                {it.count.toLocaleString()}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Events tab
// ─────────────────────────────────────────────────────────────

interface EventsTabProps {
  data: LogPaginatedResponse<EventLogRow> | null;
  loading: boolean;
  deviceFilter: string;
  eventTypeFilter: string;
  page: number;
  onDeviceChange: (v: string) => void;
  onEventTypeChange: (v: string) => void;
  onPageChange: (p: number) => void;
}

function EventsTab({
  data,
  loading,
  deviceFilter,
  eventTypeFilter,
  page,
  onDeviceChange,
  onEventTypeChange,
  onPageChange,
}: EventsTabProps) {
  const [deviceInput, setDeviceInput] = useState(deviceFilter);

  const rows: Record<string, unknown>[] = (data?.items || []).map((r) => ({
    ...r,
    time: formatTime(r.created_at),
    device_short: shortDevice(r.device_id),
  }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          placeholder="device_id 필터"
          value={deviceInput}
          onChange={(e) => setDeviceInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onDeviceChange(deviceInput)}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs flex-1 min-w-48 max-w-72"
        />
        <button
          onClick={() => onDeviceChange(deviceInput)}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700"
        >
          적용
        </button>
        <select
          value={eventTypeFilter}
          onChange={(e) => onEventTypeChange(e.target.value)}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs bg-white"
        >
          {EVENT_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {t || "(전체)"}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        columns={[
          { key: "time", label: "시각" },
          { key: "device_short", label: "device" },
          { key: "event_type", label: "type" },
          { key: "event_name", label: "name" },
          { key: "payload_preview", label: "payload" },
        ]}
        data={rows}
        total={data?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        totalPages={data?.total_pages ?? 0}
        onPageChange={onPageChange}
        loading={loading}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Chats tab
// ─────────────────────────────────────────────────────────────

interface ChatsTabProps {
  data: LogPaginatedResponse<ChatLogRow> | null;
  loading: boolean;
  deviceFilter: string;
  terminatedOnly: boolean;
  page: number;
  onDeviceChange: (v: string) => void;
  onTerminatedChange: (v: boolean) => void;
  onPageChange: (p: number) => void;
  onRowClick: (row: ChatLogRow) => void;
}

function ChatsTab({
  data,
  loading,
  deviceFilter,
  terminatedOnly,
  page,
  onDeviceChange,
  onTerminatedChange,
  onPageChange,
  onRowClick,
}: ChatsTabProps) {
  const [deviceInput, setDeviceInput] = useState(deviceFilter);

  const rows: Record<string, unknown>[] = (data?.items || []).map((r) => ({
    ...r,
    time: formatTime(r.created_at),
    device_short: shortDevice(r.device_id),
  }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder="device_id 필터"
          value={deviceInput}
          onChange={(e) => setDeviceInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onDeviceChange(deviceInput)}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs flex-1 min-w-48 max-w-72"
        />
        <button
          onClick={() => onDeviceChange(deviceInput)}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700"
        >
          적용
        </button>
        <label className="flex items-center gap-1.5 text-xs text-gray-600 ml-2">
          <input
            type="checkbox"
            checked={terminatedOnly}
            onChange={(e) => onTerminatedChange(e.target.checked)}
          />
          중단된 대화만
        </label>
      </div>

      <DataTable
        columns={[
          { key: "time", label: "시각" },
          { key: "device_short", label: "device" },
          { key: "user_message_preview", label: "Q" },
          { key: "assistant_message_preview", label: "A" },
          { key: "tool_call_count", label: "tools" },
          { key: "terminated_early", label: "상태" },
        ]}
        data={rows}
        total={data?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        totalPages={data?.total_pages ?? 0}
        onPageChange={onPageChange}
        loading={loading}
        onRowClick={(row) => onRowClick(row as unknown as ChatLogRow)}
        renderCell={(row, key) => {
          if (key === "terminated_early") {
            return (
              <StatusBadge
                status={row.terminated_early ? "warning" : "success"}
                label={row.terminated_early ? "중단" : "완료"}
              />
            );
          }
          return undefined;
        }}
      />
    </div>
  );
}

export default Logs;
