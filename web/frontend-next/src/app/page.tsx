import type { Metadata } from "next";
import { HomeShell } from "./_home/HomeShell";

// 홈 canonical 은 여기(페이지 레벨)서 선언한다 — 루트 layout 에 두면 Next
// metadata 얕은 병합으로 canonical 미선언 페이지가 홈 canonical 을 상속해
// "홈의 중복"으로 색인 제외되는 사고가 난다 (/explore 실사례, 2026-07-10).
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function HomePage() {
  return (
    <>
      {/* 홈 본문이 전부 클라이언트(지도 셸)라 크롤러/LLM 이 읽을 SSR 텍스트가
          없다 — 접근성 표준 sr-only 패턴으로 h1 + 서비스 요약을 서버 렌더.
          시각적 사용자에겐 보이지 않고 스크린리더·크롤러에만 전달된다. */}
      <div className="sr-only">
        <h1>집토리 — 라이프스타일 기반 아파트 추천</h1>
        <p>
          집토리는 국토교통부 실거래가, K-APT 관리비, 학군, 안전, 시설 접근성
          데이터를 바탕으로 대한민국 아파트를 추천·비교·분석하는 서비스입니다.
          가성비·신혼육아·학군·시니어 등 라이프스타일 키워드를 고르면 NUDGE
          점수로 단지를 추천하고, 실거래가·관리비·학군·안전 정보를 한 화면에서
          비교할 수 있습니다.
        </p>
      </div>
      <HomeShell />
    </>
  );
}
