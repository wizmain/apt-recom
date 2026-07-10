import type { Metadata } from "next";
import { HomeShell } from "./_home/HomeShell";

// 홈 canonical 은 여기(페이지 레벨)서 선언한다 — 루트 layout 에 두면 Next
// metadata 얕은 병합으로 canonical 미선언 페이지가 홈 canonical 을 상속해
// "홈의 중복"으로 색인 제외되는 사고가 난다 (/explore 실사례, 2026-07-10).
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function HomePage() {
  return <HomeShell />;
}
