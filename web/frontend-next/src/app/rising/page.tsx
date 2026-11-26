// src/app/rising/page.tsx
import type { Metadata } from "next";
import Disclaimer from "./Disclaimer";
import RisingView from "./_view";
import RisingTopBar from "./RisingTopBar";

export const metadata: Metadata = {
  // 루트 layout 의 title.template("%s | 집토리")가 접미사를 붙이므로 페이지명만 선언.
  title: "가격흐름",
  description:
    "면적대·예산별로 최근 6개월·12개월 실거래 중위가격이 오른 아파트 단지를 지역 흐름과 함께 비교해 보세요.",
  alternates: { canonical: "/rising" },
};

// 정적 셸 — 서버 fetch·searchParams·revalidate 없이 데이터는 클라이언트 훅으로만 받는다.
export default function RisingPage() {
  return (
    <>
    {/* 홈 대시보드와 같은 상단 바(고정) — 본문은 바 높이(h-12 / sm:h-14)만큼 내린다 */}
    <RisingTopBar />
    <main className="min-h-[100dvh] bg-gray-50 px-4 pb-8 pt-20 sm:px-6 sm:pt-22">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
          가격흐름
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          내 예산대에서 최근 실거래 가격이 오른 단지를 지역 흐름과 함께 찾아보세요.
        </p>
        <Disclaimer />
        <RisingView />
      </div>
    </main>
    </>
  );
}
