// src/hooks/useUrlSyncedPnu.ts
"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";

const DEFAULT_DOCUMENT_TITLE = "집토리 - 라이프스타일 아파트 찾기";
const APT_PATH = /^\/apartment\/([0-9]{19})\/?$/;

function parsePnu(pathname: string): string | null {
  const m = APT_PATH.exec(pathname);
  return m ? m[1] : null;
}

/**
 * selectedPnu ↔ /apartment/:pnu URL 양방향 동기화.
 *
 * - 초기 mount + popstate: URL → store
 * - selectedPnu 변화: store → URL (pushState)
 * - selectedPnu=null 로 돌아갈 때 document.title 기본값 복구
 */
export function useUrlSyncedPnu() {
  const selectedPnu = useAppStore((s) => s.selectedPnu);
  const selectApartment = useAppStore((s) => s.selectApartment);

  // URL → store
  useEffect(() => {
    const sync = () => {
      const pnu = parsePnu(window.location.pathname);
      selectApartment(pnu);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
    // selectApartment 는 stable (Zustand action reference) → deps 고정
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // store → URL + title
  useEffect(() => {
    const nextPath = selectedPnu ? `/apartment/${selectedPnu}` : "/";
    if (window.location.pathname !== nextPath) {
      window.history.pushState(null, "", nextPath);
    }
    if (!selectedPnu) {
      document.title = DEFAULT_DOCUMENT_TITLE;
    }
  }, [selectedPnu]);
}
