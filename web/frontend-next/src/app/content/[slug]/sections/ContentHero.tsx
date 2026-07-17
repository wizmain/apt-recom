import type { ContentPost } from "@/types/instagramContent";

export function ContentHero({ post }: { post: ContentPost }) {
  return (
    <header>
      <p className="text-sm font-semibold text-emerald-600">{post.eyebrow}</p>
      <h1 className="mt-1 text-2xl font-extrabold text-gray-900">{post.hook}</h1>
      <p className="mt-2 text-gray-600">{post.summary}</p>
      {/* eslint-disable-next-line @next/next/no-img-element -- next/image 미도입(spec §2) */}
      <img
        src={post.cover_image}
        alt={post.cover_alt}
        width={1080}
        height={1080}
        loading="eager"
        className="mt-4 w-full rounded-2xl border border-gray-100"
      />
      <p className="mt-2 text-xs text-gray-500">데이터 기준일 {post.data_as_of}</p>
    </header>
  );
}
