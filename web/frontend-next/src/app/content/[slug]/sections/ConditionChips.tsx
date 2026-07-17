import type { ContentPost } from "@/types/instagramContent";

export function ConditionChips({ post }: { post: ContentPost }) {
  return (
    <section className="mt-6">
      <div className="flex flex-wrap gap-2">
        {post.conditions.map((c) => (
          <span
            key={`${c.label}-${c.value}`}
            className="rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-700"
          >
            <span className="text-gray-500">{c.label}</span> {c.value}
          </span>
        ))}
      </div>
      <p className="mt-2 text-xs text-emerald-700">{post.period_label}</p>
    </section>
  );
}
