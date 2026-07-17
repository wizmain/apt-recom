import type { ContentItem } from "@/types/instagramContent";
import { ApartmentLink } from "../ApartmentLink";

export function RankingList({
  slug,
  heading,
  items,
}: {
  slug: string;
  heading: string;
  items: ContentItem[];
}) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-bold text-gray-900">{heading}</h2>
      <ol className="mt-3 divide-y divide-gray-100 rounded-2xl border border-gray-100">
        {items.map((item) => (
          <li key={item.rank} className="flex items-start gap-3 p-3">
            <span className="mt-0.5 w-6 text-center text-lg font-extrabold text-blue-600">
              {item.rank}
            </span>
            <div className="min-w-0 flex-1">
              <ApartmentLink slug={slug} pnu={item.pnu} rank={item.rank} name={item.name} />
              {item.region && <p className="text-sm text-gray-500">{item.region}</p>}
            </div>
            <div className="text-right text-sm">
              {item.metrics.slice(0, 2).map((m) => (
                <p key={m.label}>
                  <span className="text-gray-500">{m.label}</span>{" "}
                  <span className="font-semibold text-emerald-700">
                    {m.value}
                    {m.unit}
                  </span>
                </p>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
