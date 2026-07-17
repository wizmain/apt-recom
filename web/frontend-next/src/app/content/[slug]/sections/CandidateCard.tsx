import type { ContentItem } from "@/types/instagramContent";
import { ApartmentLink } from "../ApartmentLink";

export function CandidateCard({
  slug,
  heading,
  item,
}: {
  slug: string;
  heading: string;
  item: ContentItem;
}) {
  return (
    <section className="mt-8 rounded-2xl border border-gray-100 p-4">
      <p className="text-sm font-semibold text-blue-600">{heading}</p>
      <h2 className="mt-1 text-xl font-bold">
        <ApartmentLink slug={slug} pnu={item.pnu} rank={item.rank} name={item.name} />
      </h2>
      {item.region && <p className="text-sm text-gray-500">{item.region}</p>}
      <dl className="mt-3 space-y-1.5">
        {item.metrics.map((m) => (
          <div key={m.label} className="flex justify-between text-sm">
            <dt className="text-gray-500">{m.label}</dt>
            <dd className="font-semibold text-gray-900">
              {m.value}
              {m.unit}
            </dd>
          </div>
        ))}
      </dl>
      {item.reasons.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-gray-700">
          {item.reasons.map((r) => (
            <li key={r}>· {r}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
