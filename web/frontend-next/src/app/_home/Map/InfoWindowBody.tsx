// src/app/_home/Map/InfoWindowBody.tsx
"use client";

export type InfoWindowApt = {
  pnu: string;
  bld_nm: string;
};

export function InfoWindowBody({
  apt,
  onDetailOpen,
  onChatAnalyze,
  onCompareToggle,
  onClose,
}: {
  apt: InfoWindowApt;
  onDetailOpen: (pnu: string) => void;
  onChatAnalyze: (name: string, pnu: string) => void;
  onCompareToggle: (pnu: string, name: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="min-w-[180px] p-3 bg-white rounded-lg shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 truncate">
          {apt.bld_nm}
        </h3>
        <button
          onClick={onClose}
          aria-label="닫기"
          className="text-gray-400 hover:text-gray-600 flex-shrink-0"
        >
          ✕
        </button>
      </div>
      <div className="mt-2 flex flex-col gap-1 text-xs">
        <button
          onClick={() => onDetailOpen(apt.pnu)}
          className="px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
        >
          상세 보기
        </button>
        <button
          onClick={() => onChatAnalyze(apt.bld_nm, apt.pnu)}
          className="px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          AI 분석
        </button>
        <button
          onClick={() => onCompareToggle(apt.pnu, apt.bld_nm)}
          className="px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          비교에 추가
        </button>
      </div>
    </div>
  );
}
