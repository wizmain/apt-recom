import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { SITE_URL } from "@/lib/site";
import { getPublishedPost, getPublishedPosts } from "@/lib/instagramContent";
import { ContentView } from "./ContentView";
import { ContentViewLogger } from "./ContentViewLogger";

// 외부 fetch 0건 — posts.json 이 서버 번들에 포함되어 렌더는 항상 결정적이다.
// spec §6-2 는 완전 SSG(dynamicParams=false)였으나, 운영(OpenNext Cloudflare)이
// incrementalCache 미구성이라 동적 라우트의 프리렌더 HTML 을 서빙하지 못해
// 404 가 났다 (2026-07-17 배포 실측). apartment/[pnu]와 동일한 검증된 ISR
// 패턴으로 전환 — 미발행 slug 는 getPublishedPost null → notFound() 로 동일하게 404.
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
  if (!post)
    return { title: "콘텐츠를 찾을 수 없습니다", robots: { index: false } };
  return {
    title: post.title,
    description: post.summary,
    alternates: { canonical: `/content/${post.slug}` },
    openGraph: {
      title: post.title,
      description: post.summary,
      url: `/content/${post.slug}`,
      type: "article",
      publishedTime: post.published_at ?? undefined,
      images: [
        {
          url: post.cover_image,
          width: 1080,
          height: 1080,
          alt: post.cover_alt,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: post.title,
      description: post.summary,
      images: [post.cover_image],
    },
  };
}

export default async function ContentPostPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { slug } = await params;
  const post = getPublishedPost(slug);
  if (!post) notFound();

  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "Article",
      headline: post.title,
      description: post.summary,
      datePublished: post.published_at,
      image: `${SITE_URL}${post.cover_image}`,
      mainEntityOfPage: `${SITE_URL}/content/${post.slug}`,
    },
    {
      "@context": "https://schema.org",
      "@type": "ItemList",
      itemListElement: post.items.map((item) => ({
        "@type": "ListItem",
        position: item.rank,
        name: item.name,
        ...(item.pnu ? { url: `${SITE_URL}/apartment/${item.pnu}` } : {}),
      })),
    },
  ];

  return (
    <>
      <script
        type="application/ld+json"
        // JSON-LD XSS 이스케이프 (Next.js 가이드) — 데이터 유래 문자열의 "<" 무해화
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c"),
        }}
      />
      <Suspense fallback={null}>
        <ContentViewLogger key={post.slug} slug={post.slug} series={post.series} />
      </Suspense>
      <ContentView post={post} />
    </>
  );
}
