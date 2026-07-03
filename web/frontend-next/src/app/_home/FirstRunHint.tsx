// src/app/_home/FirstRunHint.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { logEvent } from "@/lib/logEvent";

const HINT_DONE_KEY = "apt_first_run_hint_done";

interface FirstRunHintProps {
  /** 지도 모드 && 검색/지역/넛지 아무것도 없는 첫 상태일 때만 true */
  active: boolean;
}

/**
 * 첫 실행 빈 상태 힌트 (E2).
 *
 * 검색도 추천도 없는 첫 화면에서 다음 행동(① 지역 검색 → ② 라이프스타일 선택)을
 * 안내하고 /explore 갤러리로의 지름길을 제공한다.
 *
 * 1회성 정책: ✕ 클릭 또는 사용자가 진행(active=false 전환)하면 localStorage 에
 * 완료 마킹 — 재방문 사용자에게 노이즈가 되지 않도록 다시 뜨지 않는다.
 * (localStorage 접근 실패 시 이 세션에서만 숨김 유지)
 */
export default function FirstRunHint({ active }: FirstRunHintProps) {
  // SSR/hydration 안전: 기본 숨김으로 시작 → mount 후 localStorage 판정
  const [done, setDone] = useState(true);
  const shownLoggedRef = useRef(false);

  useEffect(() => {
    try {
      setDone(localStorage.getItem(HINT_DONE_KEY) === "1");
    } catch {
      setDone(false);
    }
  }, []);

  const markDone = () => {
    setDone(true);
    try {
      localStorage.setItem(HINT_DONE_KEY, "1");
    } catch {
      // private mode 등 저장 실패 — 세션 내 숨김만 유지
    }
  };

  // 사용자가 진행(검색·추천 시작)하면 힌트의 역할이 끝난 것 — 영구 마킹
  useEffect(() => {
    if (!active && !done) markDone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const visible = active && !done;

  useEffect(() => {
    if (visible && !shownLoggedRef.current) {
      shownLoggedRef.current = true;
      logEvent("first_run_hint_shown");
    }
  }, [visible]);

  if (!visible) return null;

  return (
    // role="status" 미부여: 상시 안내 배너로 시각 전용 처리 — SearchCoach(즉각 피드백)와
    // 동시 노출 시 스크린리더 이중 알림을 막기 위해 라이브영역은 SearchCoach 쪽에만 둔다.
    <div
      className="fixed bottom-20 sm:bottom-8 left-1/2 -translate-x-1/2 z-10
                 flex items-center gap-3 rounded-full bg-gray-900/90 text-white
                 px-4 py-2.5 text-xs sm:text-sm shadow-lg backdrop-blur-sm
                 whitespace-nowrap animate-fade-in"
    >
      <span>
        <b>① 지역 검색</b> → <b>② 라이프스타일 선택</b>으로 추천을 받아보세요
      </span>
      <Link
        href="/explore"
        className="font-semibold text-amber-300 hover:text-amber-200"
      >
        추천 조합 둘러보기 →
      </Link>
      <button
        type="button"
        onClick={markDone}
        aria-label="힌트 닫기"
        className="text-white/70 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
