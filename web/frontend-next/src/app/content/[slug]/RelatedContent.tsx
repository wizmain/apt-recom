import Link from "next/link";
import { getPublishedPosts } from "@/lib/instagramContent";

/**
 * 랜딩 하단 "다른 이야기" (B-4) — 현재 slug 제외 최신 발행 2건.
 * Server Component — posts.json 정적 import 기반, 네트워크 0.
 */
const RELATED_LIMIT = 2;

export function RelatedContent({ currentSlug }: { currentSlug: string }) {
  const related = getPublishedPosts()
    .filter((p) => p.slug !== currentSlug)
    .slice(0, RELATED_LIMIT);
  if (related.length === 0) return null;
  return (
    <section className="mt-10">
      <h2 className="text-lg font-bold text-gray-900">다른 이야기</h2>
      <ul className="mt-3 space-y-3">
        {related.map((post) => (
          <li key={post.slug}>
            <Link
              href={`/content/${post.slug}`}
              className="flex items-center gap-3 rounded-2xl border border-gray-100 p-3 hover:border-blue-300"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- next/image 미도입(spec §2) */}
              <img
                src={post.cover_image}
                alt={post.cover_alt}
                width={64}
                height={64}
                loading="lazy"
                className="h-16 w-16 shrink-0 rounded-xl object-cover"
              />
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-emerald-600">
                  {post.eyebrow}
                </span>
                <span className="block truncate font-semibold text-gray-900">
                  {post.title}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
