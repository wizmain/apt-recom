import type { ContentPost } from "@/types/instagramContent";

export function MethodologyNote({ post }: { post: ContentPost }) {
  return (
    <section className="mt-8 rounded-2xl bg-gray-50 p-4 text-sm">
      <h2 className="font-bold text-gray-900">이렇게 골랐습니다</h2>
      <ul className="mt-2 space-y-1 text-gray-600">
        {post.methodology.map((m) => (
          <li key={m}>· {m}</li>
        ))}
      </ul>
      <h2 className="mt-4 font-bold text-gray-900">읽을 때 주의할 점</h2>
      <ul className="mt-2 space-y-1 text-gray-600">
        {post.caveats.map((c) => (
          <li key={c}>· {c}</li>
        ))}
      </ul>
    </section>
  );
}
