'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { TOP_BAR_LINKS } from './topBarLinks';

/**
 * 휴대폰 폭(sm 미만) 전용 "⋯" 메뉴 — 상단 바 오른쪽 링크(둘러보기·콘텐츠·가이드)를 하나로 묶는다.
 * 360px 화면에서 상단 바가 넘쳐 링크가 화면 밖으로 밀리던 문제(가격흐름 바로가기 추가로 악화) 대응.
 */
export default function TopBarMoreMenu() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 바깥 클릭·ESC 로 닫기
  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative ml-auto flex-shrink-0 sm:hidden">
      <button
        type="button"
        aria-label="더보기"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center px-2 py-1.5 rounded-full text-xs font-bold leading-none
                   text-gray-600 border border-gray-300 hover:border-blue-400 hover:text-blue-600"
      >
        ⋯
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 w-40 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
        >
          {TOP_BAR_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              role="menuitem"
              title={link.title}
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              <span aria-hidden>{link.emoji}</span>
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
