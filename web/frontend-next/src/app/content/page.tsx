import type { Metadata } from "next";
import Link from "next/link";
import { getPublishedPosts } from "@/lib/instagramContent";

export const metadata: Metadata = {
  title: "콘텐츠 — 카드뉴스로 보는 아파트 데이터",
  description: "인스타그램에 발행한 카드뉴스를 데이터 근거·기준일과 함께 봅니다.",
  alternates: { canonical: "/content" },
};

export default function ContentIndexPage() {
  const posts = getPublishedPosts();
  return (
    <main className="mx-auto max-w-xl px-4 py-8">
      <h1 className="text-2xl font-extrabold text-gray-900">콘텐츠</h1>
      <p className="mt-1 text-sm text-gray-500">
        인스타그램에 발행한 카드뉴스를 데이터 근거와 함께 봅니다.
      </p>
      {posts.length === 0 ? (
        <p className="mt-8 text-gray-500">아직 발행된 콘텐츠가 없습니다.</p>
      ) : (
        <ul className="mt-6 space-y-4">
          {posts.map((post) => (
            <li key={post.slug}>
              <Link
                href={`/content/${post.slug}`}
                className="flex gap-4 rounded-2xl border border-gray-100 p-3 hover:border-blue-300"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- next/image 미도입(spec §2) */}
                <img
                  src={post.cover_image}
                  alt={post.cover_alt}
                  width={96}
                  height={96}
                  loading="lazy"
                  className="h-24 w-24 shrink-0 rounded-xl object-cover"
                />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-emerald-600">{post.eyebrow}</p>
                  <h2 className="mt-0.5 font-bold text-gray-900">{post.title}</h2>
                  <p className="mt-1 line-clamp-2 text-sm text-gray-500">{post.summary}</p>
                  <p className="mt-1 text-xs text-gray-400">기준일 {post.data_as_of}</p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
