import { useState, useEffect } from 'react';
import { API_BASE } from '../config';
import type { FeedbackStats as FeedbackStatsType } from '../types/feedback';

const TAG_LABELS: Record<string, string> = {
  inaccurate: '정보 부정확',
  too_long: '너무 길다',
  not_relevant: '원하는 답이 아님',
  score_wrong: '점수가 이상함',
  missing_info: '정보 부족',
  formatting: '가독성 나쁨',
};

interface FeedbackStatsProps {
  onClose: () => void;
}

export default function FeedbackStats({ onClose }: FeedbackStatsProps) {
  const [stats, setStats] = useState<FeedbackStatsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/chat/feedback/stats`);
        if (!res.ok) throw new Error('fetch failed');
        const data: FeedbackStatsType = await res.json();
        setStats(data);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  // Find max tag count for bar scaling
  const maxTagCount = stats
    ? Math.max(...Object.values(stats.dislike_tags), 1)
    : 1;

  const satisfactionColor =
    stats && stats.satisfaction_rate >= 70 ? 'bg-emerald-500' :
    stats && stats.satisfaction_rate >= 40 ? 'bg-blue-500' :
    'bg-red-500';

  return (
    <div className="flex flex-col h-full animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="뒤로가기"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h3 className="text-sm font-bold text-gray-900">피드백 통계</h3>
        <div className="w-6" /> {/* Spacer for centering */}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {loading && (
          <div className="flex items-center justify-center py-12">
            <svg className="w-5 h-5 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        )}

        {error && (
          <div className="text-center text-gray-400 text-sm py-12">
            통계를 불러올 수 없습니다.
          </div>
        )}

        {!loading && !error && stats && stats.total === 0 && (
          <div className="text-center text-gray-400 text-sm py-12">
            <p>아직 피드백이 없습니다.</p>
          </div>
        )}

        {!loading && !error && stats && stats.total > 0 && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-lg font-bold text-gray-900">{stats.total}</p>
                <p className="text-[10px] text-gray-500">전체</p>
              </div>
              <div className="bg-emerald-50 rounded-lg p-3 text-center">
                <p className="text-lg font-bold text-emerald-600">{stats.likes}</p>
                <p className="text-[10px] text-emerald-600">좋아요</p>
              </div>
              <div className="bg-red-50 rounded-lg p-3 text-center">
                <p className="text-lg font-bold text-red-500">{stats.dislikes}</p>
                <p className="text-[10px] text-red-500">아쉬워요</p>
              </div>
            </div>

            {/* Satisfaction rate */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-gray-700">만족도</p>
                <p className="text-xs font-bold text-gray-900">{stats.satisfaction_rate}%</p>
              </div>
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${satisfactionColor}`}
                  style={{ width: `${stats.satisfaction_rate}%` }}
                />
              </div>
            </div>

            {/* Dislike tags breakdown */}
            {Object.keys(stats.dislike_tags).length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-700">불만족 사유</p>
                <div className="space-y-1.5">
                  {Object.entries(stats.dislike_tags)
                    .sort(([, a], [, b]) => b - a)
                    .map(([tag, count]) => (
                      <div key={tag} className="space-y-0.5">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-gray-600">{TAG_LABELS[tag] || tag}</span>
                          <span className="text-[11px] font-medium text-gray-900">{count}건</span>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-red-400 rounded-full transition-all duration-500"
                            style={{ width: `${(count / maxTagCount) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
