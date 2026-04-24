"use client";

import { useState } from "react";

/**
 * 코드 스니펫 + 클립보드 복사 버튼.
 *
 * 가이드 페이지에서 MCP 클라이언트 설정(JSON/CLI/Python) 을 한 번에 복사해
 * 설정 파일이나 터미널에 붙여넣을 수 있도록 하는 Client Component.
 *
 * 의도적으로 fallback 을 두지 않는다 — HTTPS 환경에서만 배포되고 최신 브라우저는
 * navigator.clipboard 를 모두 지원. 실패하면 사용자가 수동 선택-복사 하면 된다.
 */

interface CodeBlockProps {
  code: string;
  /** 상단 좌측에 표시할 라벨 (파일명·CLI 등). */
  label?: string;
  /** 접근성용 aria-label. 생략 시 "{label} 복사" 또는 "코드 복사" 사용. */
  ariaLabel?: string;
}

export default function CodeBlock({ code, label, ariaLabel }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 사용자가 페이지에서 직접 블록 선택 후 Ctrl/Cmd+C 로 복사 가능.
    }
  };

  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-gray-800 bg-gray-900">
      {label && (
        <div className="flex items-center justify-between border-b border-gray-800 px-3 py-1.5 text-xs text-gray-400">
          <span>{label}</span>
        </div>
      )}
      <div className="relative">
        <pre className="overflow-x-auto px-4 py-3 text-sm leading-relaxed text-gray-100">
          <code>{code}</code>
        </pre>
        <button
          type="button"
          onClick={handleCopy}
          aria-label={ariaLabel || (label ? `${label} 복사` : "코드 복사")}
          className="absolute right-2 top-2 rounded-md border border-gray-700 bg-gray-800/80 px-2 py-1
                     text-xs font-medium text-gray-200 transition-colors hover:bg-gray-700 cursor-pointer"
        >
          {copied ? "복사됨" : "복사"}
        </button>
      </div>
    </div>
  );
}
