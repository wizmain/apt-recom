import { useEffect, useState } from "react";
import { useAdminApi } from "../hooks/useAdminApi";
import { useAuth } from "../hooks/useAuth";
import { StatusBadge } from "../components/StatusBadge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import type { BatchHistoryItem, BatchLogDetail } from "../types/admin";

const BATCH_TYPES = [
  { id: "trade", label: "거래 데이터" },
  { id: "quarterly", label: "시설 (분기)" },
  { id: "annual", label: "인구/범죄 (연간)" },
  { id: "mgmt_cost", label: "관리비" },
];

export function BatchMonitor() {
  const { token, clearToken } = useAuth();
  const { get, request, error } = useAdminApi({ token, onUnauthorized: clearToken });

  const [history, setHistory] = useState<BatchHistoryItem[]>([]);
  const [logDetail, setLogDetail] = useState<BatchLogDetail | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  // 수동 실행
  const [triggerType, setTriggerType] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [running, setRunning] = useState(false);
  const [triggerResult, setTriggerResult] = useState<{
    status: string;
    stdout: string;
    stderr: string;
  } | null>(null);

  const fetchHistory = () => {
    get<{ history: BatchHistoryItem[] }>("/batch/history")
      .then((d) => d && setHistory(d.history))
      .catch(() => setUnavailable(true));
  };

  useEffect(() => {
    fetchHistory();
  }, [get]);

  useEffect(() => {
    if (error?.includes("로컬 환경") || error?.includes("503")) {
      setUnavailable(true);
    }
  }, [error]);

  const openLog = (filename: string) => {
    get<BatchLogDetail>(`/batch/logs/${filename}`).then(
      (d) => d && setLogDetail(d),
    );
  };

  const handleTrigger = async () => {
    if (!triggerType) return;
    setRunning(true);
    setTriggerResult(null);
    const res = await request<{
      status: string;
      stdout: string;
      stderr: string;
      exit_code: number;
    }>("post", "/batch/trigger", {
      batch_type: triggerType,
      dry_run: dryRun,
    });
    setRunning(false);
    setTriggerType(null);
    if (res) {
      setTriggerResult(res);
      fetchHistory();
    }
  };

  if (unavailable) {
    return (
      <div>
        <h1 className="text-lg font-bold text-slate-900 mb-4">배치 모니터링</h1>
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
          배치 모니터링은 로컬 환경에서만 사용 가능합니다. (Railway 배포 환경에서는 비활성화)
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-lg font-bold text-slate-900">배치 모니터링</h1>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="rounded"
            />
            dry-run
          </label>
          {BATCH_TYPES.map((bt) => (
            <button
              key={bt.id}
              onClick={() => setTriggerType(bt.id)}
              disabled={running}
              className="px-3 py-1.5 bg-amber-500 text-white rounded-lg text-xs font-medium hover:bg-amber-600 disabled:opacity-50"
            >
              {bt.label} 실행
            </button>
          ))}
        </div>
      </div>

      {/* Trigger result */}
      {triggerResult && (
        <div
          className={`rounded-lg p-3 mb-4 text-xs ${
            triggerResult.status === "success"
              ? "bg-green-50 border border-green-200"
              : "bg-red-50 border border-red-200"
          }`}
        >
          <div className="flex justify-between items-center mb-1">
            <span className="font-semibold">
              {triggerResult.status === "success" ? "실행 완료" : "실행 실패"}
            </span>
            <button
              onClick={() => setTriggerResult(null)}
              className="text-gray-400 hover:text-gray-600"
            >
              닫기
            </button>
          </div>
          {triggerResult.stdout && (
            <pre className="bg-white rounded p-2 mt-1 text-[10px] text-gray-700 max-h-40 overflow-auto whitespace-pre-wrap font-mono">
              {triggerResult.stdout}
            </pre>
          )}
          {triggerResult.stderr && (
            <pre className="bg-white rounded p-2 mt-1 text-[10px] text-red-600 max-h-20 overflow-auto whitespace-pre-wrap font-mono">
              {triggerResult.stderr}
            </pre>
          )}
        </div>
      )}

      {/* Running indicator */}
      {running && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-xs text-blue-800 flex items-center gap-2">
          <span className="animate-spin inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full" />
          배치 실행 중... (시간이 걸릴 수 있습니다)
        </div>
      )}

      {/* History table */}
      <div className="bg-white rounded-[10px] shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">타입</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">상태</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">시작 시각</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">소요 시간</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">처리 건수</th>
              <th className="px-4 py-2.5 text-left font-semibold text-gray-600">로그</th>
            </tr>
          </thead>
          <tbody>
            {history.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  배치 실행 이력이 없습니다.
                </td>
              </tr>
            ) : (
              history.map((b) => (
                <tr key={b.filename} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-semibold">
                    {b.batch_type ?? "unknown"}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={b.status} />
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {b.started_at ?? "-"}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {b.duration ?? "-"}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {b.total_records > 0 ? b.total_records.toLocaleString() : "-"}
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => openLog(b.filename)}
                      className="text-blue-600 hover:underline"
                    >
                      상세
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Log detail modal */}
      {logDetail && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[80vh] flex flex-col">
            <div className="flex justify-between items-center px-4 py-3 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-slate-900">
                {logDetail.filename}{" "}
                <span className="text-gray-400 font-normal">
                  ({(logDetail.size_bytes / 1024).toFixed(1)} KB)
                </span>
              </h3>
              <button
                onClick={() => setLogDetail(null)}
                className="text-gray-400 hover:text-red-500 text-lg"
              >
                ✕
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-4 text-[11px] text-gray-700 bg-gray-50 font-mono whitespace-pre-wrap">
              {logDetail.content}
            </pre>
          </div>
        </div>
      )}

      {/* Confirm dialog */}
      <ConfirmDialog
        open={!!triggerType}
        title="배치 수동 실행"
        message={`${BATCH_TYPES.find((t) => t.id === triggerType)?.label ?? triggerType} 배치를 ${dryRun ? "dry-run 모드로" : "실제로"} 실행하시겠습니까?${!dryRun ? "\n\n⚠️ dry-run이 해제되어 있습니다. 실제 데이터가 변경됩니다." : ""}`}
        confirmLabel={dryRun ? "Dry-run 실행" : "실제 실행"}
        onConfirm={handleTrigger}
        onCancel={() => setTriggerType(null)}
      />
    </div>
  );
}
