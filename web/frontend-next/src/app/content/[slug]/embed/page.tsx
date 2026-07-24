import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getPublishedPost, getPublishedPosts } from "@/lib/instagramContent";
import { ContentView } from "../ContentView";

// 일반 상세(page.tsx)와 동일한 검증된 ISR 패턴 — 정적 프리렌더 + 미발행 slug 404.
export const revalidate = 3600;
export const dynamicParams = true;

export function generateStaticParams() {
  return getPublishedPosts().map((p) => ({ slug: p.slug }));
}

type PageParams = { slug: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<PageParams>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = getPublishedPost(slug);
  // 임베드는 미니앱 WebView 전용 — 중복 콘텐츠 방지로 noindex.
  if (!post) return { title: "콘텐츠를 찾을 수 없습니다", robots: { index: false } };
  return { title: post.title, description: post.summary, robots: { index: false } };
}

export default async function ContentEmbedPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { slug } = await params;
  const post = getPublishedPost(slug);
  if (!post) notFound();
  return <ContentView post={post} embed />;
}
