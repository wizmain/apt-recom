import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { KpiCard } from "../components/KpiCard";
import { RangeFilterBar } from "../components/RangeFilterBar";
import { useMcpUsage } from "../hooks/useMcpUsage";
import type {
  LogRange,
  McpClientNameStats,
  McpErrorRow,
  McpToolCallStats,
  McpUsage as McpUsageData,
  McpUsageDailyPoint,
} from "../types/admin";

// 오류율 경고 기준 (5% 초과 시 강조)
const ERROR_RATE_WARN = 0.05;

function formatMs(ms: number | null): string {
  return ms === null ? "-" : `${ms.toLocaleString()}ms`;
}

function formatPct(rate: number): string {
  return `${Math.round(rate * 1000) / 10}%`;
}

function formatDateTime(ts: string): string {
  return new Date(ts).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function McpUsage() {
  const [range, setRange] = useState<LogRange>({ preset: "7d" });
  const { usage, loading, error } = useMcpUsage(range);

  return (
    <div>
      <h1 className="text-lg font-bold text-gray-800 mb-1">MCP 사용량</h1>
      <p className="text-xs text-gray-400 mb-3">
        외부 MCP 클라이언트(api.apt-recom.kr/mcp/) 호출 기록. 사용자 수는 IP /24 대역 기준
        추정치입니다.
      </p>
      <RangeFilterBar value={range} onChange={setRange} />
      {usage && <ExcludedInternalNote count={usage.summary.count_excluded_internal} />}
      {error && <div className="text-sm text-red-500 mb-3">{error}</div>}
      <McpUsageBody usage={usage} loading={loading} />
    </div>
  );
}

function ExcludedInternalNote({ count }: { count: number }) {
  return (
    <p className="text-xs text-gray-400 mb-3">
      내부 점검 호출 {count.toLocaleString()}건 제외됨 (공통코드 mcp_internal_ua 의 User-Agent
      접두어 기준)
    </p>
  );
}

function McpUsageBody({ usage, loading }: { usage: McpUsageData | null; loading: boolean }) {
  if (loading && !usage) {
    return <div className="text-sm text-gray-400 py-10 text-center">로딩 중...</div>;
  }
  if (!usage) {
    return <div className="text-sm text-gray-400 py-10 text-center">데이터 없음</div>;
  }
  return (
    <div className="space-y-4">
      <SummaryCards usage={usage} />
      <DailyChart points={usage.daily} />
      <ToolStatsTable title="tool 별 호출" rows={usage.by_tool} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ClientNameTable rows={usage.by_client_name} />
        <ToolStatsTable title="클라이언트 종류별 호출 (User-Agent)" rows={usage.by_client_kind} />
      </div>
      <RecentErrors rows={usage.recent_errors} />
    </div>
  );
}

function SummaryCards({ usage }: { usage: McpUsageData }) {
  const s = usage.summary;
  const errorWarn = s.error_rate > ERROR_RATE_WARN;
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <KpiCard title="tool 호출" value={s.count_tool_calls.toLocaleString()} icon="🛠" />
      <KpiCard
        title="연결 (initialize)"
        value={s.count_connections.toLocaleString()}
        icon="🔌"
        iconBg="bg-indigo-50"
      />
      <KpiCard
        title="추정 사용자 (IP /24)"
        value={s.count_ip_prefixes.toLocaleString()}
        icon="👤"
        iconBg="bg-emerald-50"
      />
      <KpiCard
        title="오류율"
        value={formatPct(s.error_rate)}
        icon="⚠"
        iconBg={errorWarn ? "bg-red-50" : "bg-gray-50"}
        changeType={errorWarn ? "negative" : "neutral"}
        change={`${s.count_errors.toLocaleString()}건`}
      />
      <KpiCard
        title="응답 시간 (평균 / p95)"
        value={formatMs(s.avg_duration_ms)}
        icon="⏱"
        iconBg="bg-amber-50"
        change={`p95 ${formatMs(s.p95_duration_ms)}`}
      />
    </div>
  );
}

function DailyChart({ points }: { points: McpUsageDailyPoint[] }) {
  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <div className="text-sm font-semibold text-gray-700 mb-2">일별 추이 (KST)</div>
      {points.length === 0 ? (
        <div className="text-xs text-gray-400 py-10 text-center">데이터 없음</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={points}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="day" tickFormatter={(v: string) => v.slice(5)} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="linear" dataKey="count_tool_calls" stroke="#3b82f6" name="tool 호출" dot={false} />
            <Line type="linear" dataKey="count_connections" stroke="#6366f1" name="연결" dot={false} />
            <Line type="linear" dataKey="count_ip_prefixes" stroke="#10b981" name="추정 사용자" dot={false} />
            <Line type="linear" dataKey="count_errors" stroke="#ef4444" name="오류" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function TableCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg p-4 shadow-sm overflow-x-auto">
      <div className="text-sm font-semibold text-gray-700 mb-2">{title}</div>
      {children}
    </div>
  );
}

function EmptyRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-6 text-center text-gray-300">
        없음
      </td>
    </tr>
  );
}

const TH = "py-1.5 px-2 font-medium text-gray-400 whitespace-nowrap";
const TD = "py-1.5 px-2 tabular-nums whitespace-nowrap";

function ToolStatsTable({ title, rows }: { title: string; rows: McpToolCallStats[] }) {
  return (
    <TableCard title={title}>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 text-left">
            <th className={TH}>이름</th>
            <th className={`${TH} text-right`}>호출</th>
            <th className={`${TH} text-right`}>오류율</th>
            <th className={`${TH} text-right`}>추정 사용자</th>
            <th className={`${TH} text-right`}>평균</th>
            <th className={`${TH} text-right`}>p95</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <EmptyRow colSpan={6} />}
          {rows.map((r) => (
            <tr key={r.name} className="border-b border-gray-50">
              <td className="py-1.5 px-2 text-gray-700 whitespace-nowrap">{r.name}</td>
              <td className={`${TD} text-right`}>{r.count_calls.toLocaleString()}</td>
              <td className={`${TD} text-right ${r.error_rate > ERROR_RATE_WARN ? "text-red-600" : ""}`}>
                {formatPct(r.error_rate)}
              </td>
              <td className={`${TD} text-right`}>{r.count_ip_prefixes.toLocaleString()}</td>
              <td className={`${TD} text-right`}>{formatMs(r.avg_duration_ms)}</td>
              <td className={`${TD} text-right`}>{formatMs(r.p95_duration_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableCard>
  );
}

function ClientNameTable({ rows }: { rows: McpClientNameStats[] }) {
  return (
    <TableCard title="연결 클라이언트 (clientInfo.name)">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 text-left">
            <th className={TH}>클라이언트</th>
            <th className={`${TH} text-right`}>연결</th>
            <th className={`${TH} text-right`}>추정 사용자</th>
            <th className={`${TH} text-right`}>최근 연결</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <EmptyRow colSpan={4} />}
          {rows.map((r) => (
            <tr key={r.name} className="border-b border-gray-50">
              <td className="py-1.5 px-2 text-gray-700 whitespace-nowrap">{r.name}</td>
              <td className={`${TD} text-right`}>{r.count_connections.toLocaleString()}</td>
              <td className={`${TD} text-right`}>{r.count_ip_prefixes.toLocaleString()}</td>
              <td className={`${TD} text-right text-gray-500`}>{formatDateTime(r.last_connected_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableCard>
  );
}

function RecentErrors({ rows }: { rows: McpErrorRow[] }) {
  return (
    <TableCard title="최근 오류">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 text-left">
            <th className={TH}>시각</th>
            <th className={TH}>tool</th>
            <th className={TH}>클라이언트</th>
            <th className={TH}>오류</th>
            <th className={TH}>인자</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <EmptyRow colSpan={5} />}
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-gray-50 align-top">
              <td className={`${TD} text-gray-500 whitespace-nowrap`}>{formatDateTime(r.created_at)}</td>
              <td className="py-1.5 px-2 text-gray-700">{r.tool_name}</td>
              <td className="py-1.5 px-2 text-gray-500">{r.client_kind ?? "-"}</td>
              <td className="py-1.5 px-2 text-red-600 break-all">{r.error_message ?? "-"}</td>
              <td className="py-1.5 px-2 text-gray-500 font-mono break-all">
                {JSON.stringify(r.arguments)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableCard>
  );
}
