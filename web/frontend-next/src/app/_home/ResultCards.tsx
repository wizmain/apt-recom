"use client";

import type { ScoredApartment } from '@/types/apartment';

interface ResultCardsProps {
  results: ScoredApartment[];
  loading: boolean;
  onSelect: (pnu: string) => void;
}

const RANK_BADGE = ['🏆', '🥈', '🥉'];

export default function ResultCards({ results, loading, onSelect }: ResultCardsProps) {
  if (results.length === 0 && !loading) return null;

  return (
    <div
      className={`
        fixed bottom-0 left-0 right-0 z-10 bg-white/95 backdrop-blur-sm
        shadow-[0_-2px_10px_rgba(0,0,0,0.08)]
        transition-all duration-300 ease-in-out
        ${results.length > 0 || loading ? 'translate-y-0 opacity-100' : 'translate-y-full opacity-0'}
      `}
    >
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12" cy="12" r="10"
                stroke="currentColor" strokeWidth="4" fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            추천 아파트를 찾고 있습니다...
          </div>
        </div>
      ) : (
        <div className="flex gap-2 sm:gap-3 px-3 sm:px-4 py-2 sm:py-3 overflow-x-auto scrollbar-hide">
          {results.map((apt, idx) => (
            <div
              key={apt.pnu}
              onClick={() => onSelect(apt.pnu)}
              className="flex-shrink-0 w-36 sm:w-48 bg-white rounded-xl border border-gray-200
                         p-2.5 sm:p-3 cursor-pointer hover:shadow-md hover:border-blue-300
                         transition-all duration-200"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-lg">
                  {idx < 3 ? RANK_BADGE[idx] : `${idx + 1}위`}
                </span>
                <span className="text-xl font-bold text-blue-600">
                  {apt.score.toFixed(1)}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-gray-800 truncate">
                {apt.bld_nm}
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                {apt.sigungu_code} · {apt.total_hhld_cnt}세대
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
