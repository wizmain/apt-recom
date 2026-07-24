"use client";

import { createContext } from "react";

/**
 * 임베드(미니앱 WebView) 렌더 여부. true면 웹 전용 네비게이션(단지 링크 등)을 감춘다.
 * RSC 에서 Provider 는 client 경계여야 하므로 별도 client 모듈로 분리한다.
 */
export const EmbedContext = createContext(false);

export function EmbedProvider({
  embed,
  children,
}: {
  embed: boolean;
  children: React.ReactNode;
}) {
  return <EmbedContext.Provider value={embed}>{children}</EmbedContext.Provider>;
}
