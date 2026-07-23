import type { ContentPost } from "@/types/instagramContent";
import { buildMapCtaHref } from "@/lib/instagramContent";
import { ContentActions } from "./ContentActions";
import { ContentNav } from "../ContentNav";
import { CandidateCard } from "./sections/CandidateCard";
import { ComparisonTable } from "./sections/ComparisonTable";
import { ConditionChips } from "./sections/ConditionChips";
import { ContentHero } from "./sections/ContentHero";
import { MethodologyNote } from "./sections/MethodologyNote";
import { NarrativeSection } from "./sections/NarrativeSection";
import { RankingList } from "./sections/RankingList";

/**
 * 시리즈별 본문 = 캐러셀 장 구성과 1:1 (scripts/insta_cards/slides.py build_slides).
 * 비교형 계약(comparison 비-null, items≥2 등)은 lib/instagramContent 의
 * type guard 가 빌드 시점에 보장 — 여기서 방어 분기를 두지 않는다.
 */
function SeriesBody({ post }: { post: ContentPost }) {
  const { slug } = post;
  switch (post.series) {
    case "budget_choice":
    case "compare": {
      const headings =
        post.series === "budget_choice"
          ? (["후보 A", "후보 B"] as const)
          : (["지역 A 추천 1위", "지역 B 추천 1위"] as const);
      return (
        <>
          <CandidateCard slug={slug} heading={headings[0]} item={post.items[0]} />
          <CandidateCard slug={slug} heading={headings[1]} item={post.items[1]} />
          <ComparisonTable comparison={post.comparison!} />
          <NarrativeSection narrative={post.narrative} />
        </>
      );
    }
    case "lifestyle":
      return (
        <>
          <RankingList slug={slug} heading="추천 후보" items={post.items} />
          {post.items.slice(0, 3).map((item, i) => (
            <CandidateCard key={item.rank} slug={slug} heading={`추천 ${i + 1}`} item={item} />
          ))}
        </>
      );
    case "value":
      return (
        <>
          <RankingList slug={slug} heading="숨은 가성비 TOP 5" items={post.items} />
          <NarrativeSection narrative={post.narrative} />
        </>
      );
    case "trade_top":
      return (
        <>
          <RankingList slug={slug} heading="신고 최고가 TOP 5" items={post.items} />
          <RankingList
            slug={slug}
            heading="신고 급증 동네 TOP 5"
            items={post.secondary_items!}
          />
        </>
      );
  }
}

export function ContentView({ post }: { post: ContentPost }) {
  const ctas = post.map_ctas.map((cta) => ({
    id: cta.id,
    label: cta.label,
    href: buildMapCtaHref(post, cta),
  }));
  return (
    <article className="mx-auto max-w-xl px-4 pb-28 pt-6">
      <div className="mb-5">
        <ContentNav />
      </div>
      <ContentHero post={post} />
      <ConditionChips post={post} />
      <SeriesBody post={post} />
      <MethodologyNote post={post} />
      <ContentActions slug={post.slug} ctas={ctas} />
    </article>
  );
}
