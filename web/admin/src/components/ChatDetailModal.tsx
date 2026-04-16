import { useEffect, useState } from "react";
import type { ChatLogDetail } from "../types/admin";
import { StatusBadge } from "./StatusBadge";

interface Props {
  detail: ChatLogDetail | null;
  loading: boolean;
  onClose: () => void;
}

/**
 * 채팅 로그 원문 모달 — user_message / assistant_message / tool_calls / context 전체 표시.
 * ESC 키 또는 배경 클릭으로 닫힘.
 */
export function ChatDetailModal({ detail, loading, onClose }: Props) {
  const [showTools, setShowTools] = useState(true);
  const [showContext, setShowContext] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-30 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl max-w-3xl w-full max-h-[85vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 sticky top-0 bg-white">
          <h3 className="text-sm font-bold text-gray-800">채팅 대화 원문</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-lg leading-none"
          >
            ×
          </button>
        </div>

        {loading || !detail ? (
          <div className="p-8 text-center text-sm text-gray-400">
            {loading ? "로딩 중..." : "데이터 없음"}
          </div>
        ) : (
          <div className="p-5 space-y-4 text-xs">
            {/* 헤더 메타 */}
            <div className="flex flex-wrap items-center gap-3 text-gray-500">
              <span>
                <span className="text-gray-400">device:</span>{" "}
                <code className="bg-gray-100 px-1 rounded">
                  {detail.device_id?.slice(0, 16) || "(null)"}
                </code>
              </span>
              <span>
                <span className="text-gray-400">time:</span>{" "}
                {detail.created_at
                  ? new Date(detail.created_at).toLocaleString("ko-KR")
                  : "-"}
              </span>
              <StatusBadge
                status={detail.terminated_early ? "warning" : "success"}
                label={detail.terminated_early ? "중단" : "정상 완료"}
              />
              <span>
                <span className="text-gray-400">tools:</span>{" "}
                {detail.tool_calls.length}
              </span>
            </div>

            {/* User 메시지 */}
            <section>
              <div className="text-[11px] font-semibold text-gray-500 uppercase mb-1">
                User
              </div>
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 whitespace-pre-wrap text-gray-800">
                {detail.user_message}
              </div>
            </section>

            {/* Assistant 메시지 */}
            <section>
              <div className="text-[11px] font-semibold text-gray-500 uppercase mb-1">
                Assistant
              </div>
              <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 whitespace-pre-wrap text-gray-800">
                {detail.assistant_message || "(빈 응답)"}
              </div>
            </section>

            {/* Tool Calls (접힘) */}
            {detail.tool_calls.length > 0 && (
              <section>
                <button
                  onClick={() => setShowTools((s) => !s)}
                  className="text-[11px] font-semibold text-gray-500 uppercase hover:text-blue-600"
                >
                  Tool Calls {showTools ? "▼" : "▶"}
                </button>
                {showTools && (
                  <pre className="mt-1 bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto text-[11px] text-gray-700">
                    {JSON.stringify(detail.tool_calls, null, 2)}
                  </pre>
                )}
              </section>
            )}

            {/* Context (접힘) */}
            {detail.context && Object.keys(detail.context).length > 0 && (
              <section>
                <button
                  onClick={() => setShowContext((s) => !s)}
                  className="text-[11px] font-semibold text-gray-500 uppercase hover:text-blue-600"
                >
                  Context {showContext ? "▼" : "▶"}
                </button>
                {showContext && (
                  <pre className="mt-1 bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto text-[11px] text-gray-700">
                    {JSON.stringify(detail.context, null, 2)}
                  </pre>
                )}
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
