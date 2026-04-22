import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { SITE_URL, ORGANIZATION_JSON_LD, WEBSITE_JSON_LD } from "@/lib/site";

/**
 * 루트 Metadata — 모든 페이지의 기본값. 개별 페이지에서 override 가능.
 * `metadataBase` 는 canonical/OG URL 의 기준점이며,
 * 배포 환경(Vercel)에서 NEXT_PUBLIC_SITE_URL 로 override 가능.
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "집토리 - 라이프스타일 아파트 찾기",
    template: "%s | 집토리",
  },
  description:
    "집토리는 라이프스타일 키워드로 대한민국 아파트를 찾아주는 서비스입니다. NUDGE 스코어링, 가격·안전 점수, 실거래가, 학군·시설 거리를 한 화면에서 비교하세요.",
  applicationName: "집토리",
  keywords: ["아파트", "부동산", "추천", "라이프스타일", "집토리", "apt-recom"],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: "집토리",
    locale: "ko_KR",
    url: "/",
    title: "집토리 - 라이프스타일 아파트 찾기",
    description:
      "라이프스타일 키워드로 맞춤 아파트 추천. NUDGE 스코어링과 실거래가·안전·학군 데이터를 한 번에.",
    images: [
      {
        url: "/og-image.jpg",
        width: 1200,
        height: 630,
        alt: "집토리 - 라이프스타일로 찾는 우리집",
        type: "image/jpeg",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "집토리 - 라이프스타일 아파트 찾기",
    description:
      "라이프스타일 키워드로 맞춤 아파트 추천. NUDGE 스코어링과 실거래가·안전·학군 데이터를 한 번에.",
    images: ["/og-image.jpg"],
  },
  icons: { icon: "/favicon.svg" },
};

const KAKAO_MAPS_APPKEY = process.env.NEXT_PUBLIC_KAKAO_MAPS_APPKEY;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        {/* agent 가 파싱하기 좋도록 JSON-LD 는 body 최상단 서버 렌더 */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_JSON_LD) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(WEBSITE_JSON_LD) }}
        />

        {/*
          Kakao Maps SDK — autoload=false 로 로드하고 Map 컴포넌트에서
          `kakao.maps.load()` 로 실제 사용 시점에 초기화한다.
          appkey 미설정 시 태그 자체를 생략 (지도 외 페이지 영향 없음).
        */}
        {KAKAO_MAPS_APPKEY ? (
          <Script
            src={`//dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_MAPS_APPKEY}&libraries=clusterer&autoload=false`}
            strategy="afterInteractive"
          />
        ) : null}

        {children}
      </body>
    </html>
  );
}
