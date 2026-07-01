"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { buildDetailPreset } from "@/lib/detailPreset";

/** LifeScores.tsx 의 LABELS 와 동일한 nudge 코드 → 라벨 매핑. 새 사전을 만들지 않음. */
const NUDGE_LABELS: Record<string, string> = {
  cost: "가성비",
  pet: "반려동물",
  commute: "출퇴근",
  newlywed: "신혼부부",
  education: "교육",
  senior: "시니어",
  investment: "투자",
  nature: "자연친화",
  safety: "안전",
};

interface RecommendCtaProps {
  pnu: string;
  bldNm: string;
  scores: Record<string, number> | null | undefined;
  sigunguCode: string | null | undefined;
  regionLabel: string | null | undefined;
}

/**
 * 단지 상세 → 라이프스타일 추천 전환 CTA.
 *
 * - Server Component 인 `_view.tsx` 조립자에서 사용하므로 Client Component 로 분리.
 * - scores 에서 buildDetailPreset 으로 상위 nudge 추출.
 * - 상위 nudge 가 없으면 렌더 생략.
 * - 노출 시 `detail_recommend_cta_view` 이벤트 전송 (fire-and-forget).
 * - 클릭 시 `detail_recommend_cta_click` 이벤트 전송 후 홈 딥링크로 이동.
 * - 이벤트 전송 실패가 CTA/네비게이션을 막지 않음.
 */
export function RecommendCta({
  pnu,
  bldNm,
  scores,
  sigunguCode,
  regionLabel,
}: RecommendCtaProps) {
  const preset = buildDetailPreset(scores ?? null);

  // 상위 nudge 가 없으면 CTA 미노출
  if (preset.nudges.length === 0) return null;

  const nudgeCsv = preset.nudges.join(",");
  const topNudgeLabels = preset.nudges.map((code) => NUDGE_LABELS[code] ?? code);

  return (
    <CtaContent
      pnu={pnu}
      bldNm={bldNm}
      sigunguCode={sigunguCode ?? null}
      regionLabel={regionLabel ?? null}
      nudgeCsv={nudgeCsv}
      topNudgeLabels={topNudgeLabels}
      presetNudges={preset.nudges}
    />
  );
}

interface CtaContentProps {
  pnu: string;
  bldNm: string;
  sigunguCode: string | null;
  regionLabel: string | null;
  nudgeCsv: string;
  topNudgeLabels: string[];
  presetNudges: string[];
}

/**
 * 이벤트 전송 + UI + 네비게이션을 담당하는 내부 Client 컴포넌트.
 * `buildDetailPreset`(순수 함수)은 바깥(`RecommendCta`)에서 실행 후 결과를 props 로 전달.
 */
function CtaContent({
  pnu,
  bldNm,
  sigunguCode,
  regionLabel,
  nudgeCsv,
  topNudgeLabels,
  presetNudges,
}: CtaContentProps) {
  const router = useRouter();

  // 노출 이벤트 — 마운트 1회 전송, fire-and-forget.
  useEffect(() => {
    void api
      .post("/api/events", {
        event_type: "detail_recommend_cta_view",
        payload: { pnu, top_nudges: nudgeCsv.split(",") },
      })
      .catch(() => {
        /* 이벤트 전송 실패는 무시 */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleClick = () => {
    // 클릭 이벤트 전송 — fire-and-forget.
    void api
      .post("/api/events", {
        event_type: "detail_recommend_cta_click",
        payload: {
          pnu,
          preset_nudges: presetNudges,
          sigungu_code: sigunguCode,
        },
      })
      .catch(() => {
        /* 이벤트 전송 실패는 무시 */
      });

    // 홈 딥링크 — 쿼리파라미터로 store 부트스트랩 컨텍스트 전달.
    const params = new URLSearchParams({ nudges: nudgeCsv });
    if (sigunguCode) params.set("sigungu_code", sigunguCode);
    if (regionLabel) params.set("region_label", regionLabel);
    router.push(`/?${params.toString()}`);
  };

  const strengthText = topNudgeLabels.join(" · ");

  return (
    <section className="mt-8 rounded-2xl border border-violet-200 bg-violet-50 px-5 py-5">
      <p className="text-xs text-violet-500 font-medium mb-1">
        이 단지의 강점: {strengthText}
      </p>
      <h2 className="text-base font-bold text-gray-900 mb-3">
        {bldNm}와 비슷한 라이프스타일 아파트 추천받기
      </h2>
      <button
        type="button"
        onClick={handleClick}
        className="w-full rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white hover:bg-violet-700 active:bg-violet-800 transition-colors"
      >
        비슷한 라이프스타일 추천 받기
      </button>
    </section>
  );
}
