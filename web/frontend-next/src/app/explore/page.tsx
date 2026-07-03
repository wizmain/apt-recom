// src/app/explore/page.tsx
import type { Metadata } from "next";
import { API_URL } from "@/lib/site";
import type { CodeItem } from "@/hooks/useCodes";
import { parseExplorePresets, type ExplorePreset } from "@/lib/explorePreset";
import PresetTiles from "./PresetTiles";

export const metadata: Metadata = {
  title: "라이프스타일 추천 둘러보기 | 집토리",
  description:
    "학군·출퇴근·가성비 등 지역 × 라이프스타일 조합을 고르면 바로 아파트 추천을 받아볼 수 있습니다.",
};

// 프리셋은 common_code(explore_preset) 서버 fetch — 1시간 재검증 캐시.
// 각 타일은 홈 딥링크(useBridgeParams 소비)이므로 이 페이지 자체가 SEO/공유 랜딩이 된다.
export const revalidate = 3600;

async function fetchPresets(): Promise<ExplorePreset[]> {
  try {
    const res = await fetch(`${API_URL}/api/codes/explore_preset`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    return parseExplorePresets((await res.json()) as CodeItem[]);
  } catch {
    // 백엔드 불가 시 빈 갤러리 안내 렌더 (빌드/프리렌더 실패 방지)
    return [];
  }
}

export default async function ExplorePage() {
  const presets = await fetchPresets();

  return (
    <main className="min-h-[100dvh] bg-gray-50 px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
          라이프스타일 추천 둘러보기
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          마음에 드는 조합을 고르면 바로 추천 결과를 보여드려요.
        </p>
        <PresetTiles presets={presets} />
      </div>
    </main>
  );
}
