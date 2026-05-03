"use client";

import { useEffect } from "react";
import { registerWebMcpTools } from "@/lib/webmcp";

/**
 * WebMCP tool 등록 — 페이지 로드 시 navigator.modelContext.registerTool() 호출.
 *
 * AbortController.signal 로 cleanup. 미지원 브라우저에서는 no-op.
 * Root layout 에 한 번만 마운트해 모든 라우트에서 활성화.
 */
export default function WebMcpRegistry() {
  useEffect(() => {
    const controller = new AbortController();
    registerWebMcpTools(controller.signal);
    return () => controller.abort();
  }, []);
  return null;
}
