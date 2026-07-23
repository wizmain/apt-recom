"use client";

import Link from "next/link";
import { getPublishedPosts } from "@/lib/instagramContent";
import { logEvent } from "@/lib/logEvent";

/**
 * 대시보드 하단 콘텐츠 재순환 (B-3) — "이 데이터로 만든 이야기" 최신 2건.
 * posts.json 정적 import 기반이라 클라이언트에서도 네트워크 비용 0.
 */
const CARD_LIMIT = 2;

export function DashboardContentCards() {
  const posts = getPublishedPosts().slice(0, CARD_LIMIT);
  if (posts.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold text-gray-700">
        이 데이터로 만든 이야기
      </h2>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {posts.map((post) => (
          <Link
            key={post.slug}
            href={`/content/${post.slug}`}
            onClick={() =>
              logEvent("dashboard_content_click", { slug: post.slug })
            }
            className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3
                       transition-colors hover:border-blue-300"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- next/image 미도입(spec §2) */}
            <img
              src={post.cover_image}
              alt={post.cover_alt}
              width={56}
              height={56}
              loading="lazy"
              className="h-14 w-14 shrink-0 rounded-lg object-cover"
            />
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-emerald-600">
                {post.eyebrow}
              </span>
              <span className="block truncate text-sm font-semibold text-gray-900">
                {post.title}
              </span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
