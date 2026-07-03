"use client";

interface SearchCoachProps {
  visible: boolean;
  onDismiss: () => void;
}

/**
 * 검색 유도 인라인 코치 (E1).
 *
 * 비활성 nudge 칩을 눌렀을 때 기존 alert() 대신 검색창 아래에 노출되어
 * "지역을 먼저 고르면 추천이 켜진다"는 다음 행동을 안내한다.
 * 표시/숨김 판단은 부모(NudgeBar)가 소유 — 지역/키워드가 생기면 내려간다.
 */
export default function SearchCoach({ visible, onDismiss }: SearchCoachProps) {
  if (!visible) return null;

  return (
    <div
      role="status"
      className="absolute top-full left-0 mt-2 z-50 flex items-center gap-2
                 bg-blue-600 text-white text-xs rounded-lg shadow-lg px-3 py-2
                 whitespace-nowrap animate-fade-in"
    >
      <span aria-hidden>💡</span>
      <span>지역을 먼저 검색하면 라이프스타일 추천이 켜져요</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="안내 닫기"
        className="ml-1 text-white/80 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
