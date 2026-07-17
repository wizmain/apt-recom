import { notFound } from "next/navigation";
import { Suspense } from "react";
import { getPublishedPost, getPublishedPosts } from "@/lib/instagramContent";
import { ContentView } from "./ContentView";
import { ContentViewLogger } from "./ContentViewLogger";

// 외부 fetch 0건 — 완전 정적 생성. apartment/[pnu](ISR)와 의도적으로 다른 선택:
// 본문은 발행 시점 스냅샷이므로 재검증이 필요 없다 (PRD §6-2).
export const dynamicParams = false;

export function generateStaticParams() {
  return getPublishedPosts().map((p) => ({ slug: p.slug }));
}

type PageParams = { slug: string };

export default async function ContentPostPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { slug } = await params;
  const post = getPublishedPost(slug);
  if (!post) notFound();
  return (
    <>
      <Suspense fallback={null}>
        <ContentViewLogger slug={post.slug} series={post.series} />
      </Suspense>
      <ContentView post={post} />
    </>
  );
}
